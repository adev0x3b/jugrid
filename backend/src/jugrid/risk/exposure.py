"""Which grid cells an asset touches, and what the indicators say there."""

from collections.abc import Sequence

import numpy as np
import xarray as xr
from shapely import STRtree
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry


def _edges(centres: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if centres.size == 1:
        half = np.array([0.125])
    else:
        half = np.abs(np.diff(centres)).min() / 2 * np.ones(1)
    return centres - half, centres + half


class GridSampler:
    """Indicator values on a regular (lat, lon) grid, looked up by geometry.

    A point reads the cell it falls in. A line reads every cell it crosses and keeps the worst
    value of each indicator, because a line is as weak as its most exposed span.
    """

    def __init__(self, grid: xr.Dataset, variables: Sequence[str]) -> None:
        self.variables = list(variables)
        lats, lons = grid["lat"].values, grid["lon"].values
        lat_lo, lat_hi = _edges(lats)
        lon_lo, lon_hi = _edges(lons)
        self._cells: list[tuple[int, int]] = []
        boxes = []
        for i in range(lats.size):
            for j in range(lons.size):
                self._cells.append((i, j))
                boxes.append(box(lon_lo[j], lat_lo[i], lon_hi[j], lat_hi[i]))
        self._tree = STRtree(boxes)
        self._values = {
            name: grid[name].transpose("lat", "lon").values.astype("float64")
            for name in self.variables
        }

    def sample(self, geometry: BaseGeometry) -> dict[str, float | None]:
        hits = self._tree.query(geometry, predicate="intersects")
        result: dict[str, float | None] = {}
        for name in self.variables:
            values = [self._values[name][self._cells[k]] for k in hits]
            finite = [v for v in values if np.isfinite(v)]
            result[name] = round(float(max(finite)), 3) if finite else None
        return result
