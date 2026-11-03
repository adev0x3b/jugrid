"""Small geometry helpers that need no projection library."""

import itertools
import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (self.west < self.east and self.south < self.north):
            raise ValueError(f"not a bounding box: {self}")

    @classmethod
    def parse(cls, text: str) -> BBox:
        """``west,south,east,north`` in degrees."""
        parts = [float(p) for p in text.split(",")]
        if len(parts) != 4:
            raise ValueError("a bounding box is west,south,east,north")
        return cls(*parts)

    def grow(self, degrees: float) -> BBox:
        return BBox(
            self.west - degrees, self.south - degrees, self.east + degrees, self.north + degrees
        )


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def length_km(geom: BaseGeometry) -> float:
    """Great-circle length of a line in kilometres (0 for points and polygons)."""
    if isinstance(geom, LineString):
        return math.fsum(
            haversine_km(x1, y1, x2, y2) for (x1, y1), (x2, y2) in itertools.pairwise(geom.coords)
        )
    if isinstance(geom, MultiLineString):
        return math.fsum(length_km(part) for part in geom.geoms)
    return 0.0
