"""River flood depth from the Copernicus/JRC global flood hazard maps (GloFAS v2).

The maps are 10x10 degree GeoTIFF tiles of water depth in metres, about 90 m a pixel, one set
per return period. A pixel with no value is dry land in that flood.
"""

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import rasterio
from shapely.geometry import LineString, box, shape
from shapely.geometry.base import BaseGeometry

from jugrid.geo import BBox, length_km

SAMPLE_STEP_DEG = 0.0008  # about one pixel


class FloodSourceError(RuntimeError):
    """The tile index or a tile could not be fetched."""


def tiles_for(index: dict[str, Any], bbox: BBox) -> list[str]:
    """File stems (``ID114_N50_W0``) of the tiles that overlap the box."""
    area = box(bbox.west, bbox.south, bbox.east, bbox.north)
    return [
        f"ID{feature['properties']['id']}_{feature['properties']['name']}"
        for feature in index["features"]
        if shape(feature["geometry"]).intersects(area)
    ]


def tile_url(base_url: str, return_period: int, stem: str) -> str:
    return f"{base_url}/RP{return_period}/{stem}_RP{return_period}_depth.tif"


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    partial = dest.with_suffix(dest.suffix + ".part")
    try:
        with client.stream("GET", url, timeout=600) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
    except httpx.HTTPError as error:
        partial.unlink(missing_ok=True)
        raise FloodSourceError(f"could not fetch {url}: {error}") from error
    partial.replace(dest)


def fetch_tiles(
    client: httpx.Client, base_url: str, return_period: int, bbox: BBox, cache_dir: Path
) -> list[Path]:
    """The region's depth tiles, downloaded once into ``cache_dir``."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "flood_tile_extents.geojson"
    if not index_path.exists():
        _download(client, f"{base_url}/tile_extents.geojson", index_path)
    stems = tiles_for(json.loads(index_path.read_text()), bbox)
    paths = []
    for stem in stems:
        path = cache_dir / f"{stem}_RP{return_period}_depth.tif"
        if not path.exists():
            _download(client, tile_url(base_url, return_period, stem), path)
        paths.append(path)
    return paths


class FloodSampler:
    """Water depth at points and along lines, read from local depth tiles."""

    def __init__(self, tiles: Sequence[Path]) -> None:
        self._datasets = [rasterio.open(path) for path in tiles]

    def close(self) -> None:
        for dataset in self._datasets:
            dataset.close()

    def __enter__(self) -> FloodSampler:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def depths(self, points: Iterable[tuple[float, float]]) -> list[float | None]:
        """Depth in metres at each (lon, lat); 0 on dry land, None outside every tile."""
        out: list[float | None] = []
        for lon, lat in points:
            out.append(self._depth(lon, lat))
        return out

    def _depth(self, lon: float, lat: float) -> float | None:
        for dataset in self._datasets:
            left, bottom, right, top = dataset.bounds
            if left <= lon < right and bottom < lat <= top:
                (value,) = next(dataset.sample([(lon, lat)], indexes=1))
                nodata = dataset.nodata
                if (nodata is not None and value == nodata) or not np.isfinite(value):
                    return 0.0
                return max(0.0, float(value))
        return None

    def exposure(self, geometry: BaseGeometry) -> tuple[float | None, float]:
        """The deepest water an asset meets and, for lines, the kilometres that run under it."""
        if geometry.geom_type == "Point":
            return self._depth(geometry.x, geometry.y), 0.0  # type: ignore[attr-defined]
        line = (
            geometry
            if isinstance(geometry, LineString)
            else LineString(
                [c for part in geometry.geoms for c in part.coords]  # type: ignore[attr-defined]
            )
        )
        steps = max(2, int(line.length / SAMPLE_STEP_DEG) + 1)
        points = [line.interpolate(i / (steps - 1), normalized=True) for i in range(steps)]
        values = self.depths((p.x, p.y) for p in points)
        known = [v for v in values if v is not None]
        if not known:
            return None, 0.0
        wet_share = sum(1 for v in known if v > 0) / len(values)
        return max(known), round(length_km(line) * wet_share, 3)
