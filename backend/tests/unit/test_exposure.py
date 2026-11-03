from pathlib import Path

import numpy as np
import pytest
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from shapely.geometry import LineString, MultiLineString, Point

from jugrid.geo import BBox
from jugrid.risk.exposure import GridSampler
from jugrid.sources.jrcflood import FloodSampler, FloodSourceError, tile_url, tiles_for
from tests.factories import LATS, LONS


@pytest.fixture
def grid() -> xr.Dataset:
    # hot_days rises west to east: 0, 10, 20 along longitude.
    hot = np.tile(np.array([0.0, 10.0, 20.0]), (3, 1))
    hot[2, 2] = np.nan
    return xr.Dataset({"hot_days": (("lat", "lon"), hot)}, coords={"lat": LATS, "lon": LONS})


class TestGridSampler:
    def test_a_point_reads_its_cell(self, grid: xr.Dataset) -> None:
        sampler = GridSampler(grid, ["hot_days"])
        assert sampler.sample(Point(7.4, 45.1)) == {"hot_days": 0.0}
        assert sampler.sample(Point(7.63, 45.1)) == {"hot_days": 10.0}

    def test_a_line_keeps_its_worst_cell(self, grid: xr.Dataset) -> None:
        sampler = GridSampler(grid, ["hot_days"])
        assert sampler.sample(LineString([(7.3, 45.0), (7.9, 45.0)])) == {"hot_days": 20.0}

    def test_missing_cells_are_skipped_and_outside_is_unknown(self, grid: xr.Dataset) -> None:
        sampler = GridSampler(grid, ["hot_days"])
        assert sampler.sample(Point(7.9, 45.4)) == {"hot_days": None}  # the NaN cell
        assert sampler.sample(Point(12.0, 41.9)) == {"hot_days": None}


def write_tile(path: Path, depth: np.ndarray, west: float, north: float, step: float) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=depth.shape[1],
        height=depth.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        nodata=-9999.0,
        transform=from_origin(west, north, step, step),
    ) as dst:
        dst.write(depth.astype("float32"), 1)


@pytest.fixture
def tile(tmp_path: Path) -> Path:
    # A 1x1 degree tile over 7-8 E, 45-46 N, 100 pixels a side; water 2 m deep in its
    # south-west quarter and dry (no data) elsewhere.
    depth = np.full((100, 100), -9999.0)
    depth[50:, :50] = 2.0
    path = tmp_path / "tile.tif"
    write_tile(path, depth, 7.0, 46.0, 0.01)
    return path


class TestFloodSampler:
    def test_points_read_depth_dry_land_is_zero_and_outside_unknown(self, tile: Path) -> None:
        with FloodSampler([tile]) as sampler:
            assert sampler.depths([(7.2, 45.2), (7.8, 45.8), (9.5, 45.5)]) == [2.0, 0.0, None]

    def test_a_line_reports_its_deepest_water_and_wet_kilometres(self, tile: Path) -> None:
        # 0.8 degrees of longitude along 45.25 N, half of it in the water.
        line = LineString([(7.1, 45.25), (7.9, 45.25)])
        with FloodSampler([tile]) as sampler:
            depth, wet_km = sampler.exposure(line)
        assert depth == 2.0
        assert wet_km == pytest.approx(63.0 * 0.5, rel=0.05)

    def test_a_multi_line_is_measured_part_by_part(self, tile: Path) -> None:
        # Two dry spans in the north; joined end to start they would cut through the water.
        line = MultiLineString(
            [[(7.6, 45.9), (7.9, 45.9)], [(7.1, 45.1), (7.1, 45.0)]]  # the second in the water
        )
        with FloodSampler([tile]) as sampler:
            depth, wet_km = sampler.exposure(line)
        assert depth == 2.0
        assert wet_km == pytest.approx(11.1, rel=0.05)  # the second part only

    def test_a_point_has_no_wet_kilometres(self, tile: Path) -> None:
        with FloodSampler([tile]) as sampler:
            assert sampler.exposure(Point(7.2, 45.2)) == (2.0, 0.0)


def test_tiles_overlapping_the_region_are_picked_by_id_and_name() -> None:
    index = {
        "features": [
            {
                "properties": {"id": 114, "name": "N50_W0"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 40], [10, 40], [10, 50], [0, 50], [0, 40]]],
                },
            },
            {
                "properties": {"id": 115, "name": "N50_E10"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[10, 40], [20, 40], [20, 50], [10, 50], [10, 40]]],
                },
            },
        ]
    }
    assert tiles_for(index, BBox(6.62, 44.06, 9.22, 46.47)) == ["ID114_N50_W0"]
    assert tile_url("https://jrc", 100, "ID114_N50_W0") == (
        "https://jrc/RP100/ID114_N50_W0_RP100_depth.tif"
    )


@pytest.mark.parametrize("name", ["../../etc/N50_W0", "N50_W0/../../x", "N50 W0"])
def test_tile_names_that_are_not_tile_names_are_refused(name: str) -> None:
    index = {
        "features": [
            {
                "properties": {"id": 114, "name": name},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 40], [10, 40], [10, 50], [0, 50], [0, 40]]],
                },
            }
        ]
    }
    with pytest.raises(FloodSourceError, match="unexpected tile name"):
        tiles_for(index, BBox(6.62, 44.06, 9.22, 46.47))
