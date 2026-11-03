import numpy as np
import pandas as pd
import pytest
import xarray as xr

from jugrid.geo import BBox
from jugrid.sources import eobs

BBOX = BBox(west=7.0, south=45.0, east=7.5, north=45.5)


def europe(variable: str = "tx") -> xr.Dataset:
    lat = np.arange(44.125, 46.5, 0.25)
    lon = np.arange(6.125, 8.5, 0.25)
    time = pd.date_range("1999-12-30", "2001-01-02", freq="D")
    values = np.random.default_rng(1).normal(20, 5, (len(time), len(lat), len(lon)))
    return xr.Dataset(
        {variable: (("time", "latitude", "longitude"), values.astype("float32"))},
        coords={"time": time, "latitude": lat, "longitude": lon},
    )


class TestCut:
    def test_keeps_one_year_of_the_region_as_lat_lon_in_the_model_variable(self) -> None:
        out = eobs.cut(europe("tx"), "tasmax", 2000, BBOX)
        assert out.name == "tasmax"
        assert out.dims == ("time", "lat", "lon")
        assert out.sizes["time"] == 366
        assert float(out["lat"].min()) >= BBOX.south - 0.375
        assert float(out["lon"].max()) <= BBOX.east + 0.375
        assert out.dtype == np.float32

    def test_reads_the_matching_e_obs_variable(self) -> None:
        assert eobs.OBSERVED["pr"] == "rr"
        out = eobs.cut(europe("rr"), "pr", 2000, BBOX)
        assert out.name == "pr"

    def test_a_region_outside_the_grid_is_an_error(self) -> None:
        with pytest.raises(eobs.ObservationsError):
            eobs.cut(europe(), "tasmax", 2000, BBox(west=20, south=60, east=21, north=61))

    def test_a_year_outside_the_record_is_an_error(self) -> None:
        with pytest.raises(eobs.ObservationsError):
            eobs.cut(europe(), "tasmax", 1990, BBOX)


def test_every_model_variable_has_an_observed_one() -> None:
    assert set(eobs.OBSERVED) == {"tasmax", "tas", "pr", "sfcWind"}


def test_file_paths_name_the_version() -> None:
    assert eobs.path("tasmax", "v32.0e").endswith("/tx_ens_mean_0.25deg_reg_v32.0e.nc")
