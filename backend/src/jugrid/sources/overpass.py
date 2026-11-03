"""Power assets from OpenStreetMap through the Overpass API."""

import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from jugrid.risk.hazards import AssetKind

POINT_KINDS = {"substation": AssetKind.SUBSTATION, "plant": AssetKind.PLANT}
LINE_KINDS = {
    "line": AssetKind.LINE,
    "minor_line": AssetKind.MINOR_LINE,
    "cable": AssetKind.CABLE,
}


class OverpassError(RuntimeError):
    """Overpass answered with an error, timed out or sent something that is not its JSON."""


@dataclass(frozen=True, slots=True)
class Asset:
    osm_type: str
    osm_id: int
    kind: AssetKind
    geometry: BaseGeometry
    name: str | None = None
    operator: str | None = None
    voltage_kv: float | None = None
    tags: Mapping[str, str] = field(default_factory=dict)


def query(iso_region: str, timeout_s: int = 300) -> str:
    """Overpass QL for every substation, plant, line and cable inside an ISO 3166-2 region."""
    if not re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{1,3}", iso_region):
        raise ValueError(f"not an ISO 3166-2 code: {iso_region!r}")
    return (
        f"[out:json][timeout:{timeout_s}];"
        f'area["ISO3166-2"="{iso_region}"]->.region;'
        '(nwr["power"~"^(substation|plant)$"](area.region);'
        'way["power"~"^(line|minor_line|cable)$"](area.region););'
        "out tags geom;"
    )


def parse_voltage_kv(raw: str | None) -> float | None:
    """The highest voltage in an OSM ``voltage`` tag (volts, ``;``-separated), in kV."""
    if not raw:
        return None
    volts = []
    for part in raw.split(";"):
        try:
            value = float(part.strip())
        except ValueError:
            continue
        if math.isfinite(value) and value > 0:  # "nan", "inf" and "-1" are tagging mistakes
            volts.append(value)
    return max(volts) / 1000 if volts else None


def _coords(element: Mapping[str, Any]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in element.get("geometry") or [] if p]


def _geometry(element: Mapping[str, Any], kind: AssetKind) -> BaseGeometry | None:
    kind_of_element = element["type"]
    if kind_of_element == "node":
        return Point(element["lon"], element["lat"])
    if kind in LINE_KINDS.values():
        coords = _coords(element)
        return LineString(coords) if len(coords) >= 2 else None
    if kind_of_element == "way":
        coords = _coords(element)
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return Polygon(coords).centroid
        return LineString(coords).centroid if len(coords) >= 2 else None
    bounds = element.get("bounds")
    if bounds:  # relations: the middle of their bounding box is close enough for a site
        return Point(
            (bounds["minlon"] + bounds["maxlon"]) / 2, (bounds["minlat"] + bounds["maxlat"]) / 2
        )
    return None


def parse(payload: Mapping[str, Any]) -> Iterator[Asset]:
    """Assets from an Overpass JSON answer; elements without usable geometry are skipped."""
    if "elements" not in payload:
        raise OverpassError("the answer has no elements")
    for element in payload["elements"]:
        tags: dict[str, str] = element.get("tags") or {}
        power = tags.get("power", "")
        kind = POINT_KINDS.get(power) or LINE_KINDS.get(power)
        if kind is None:
            continue
        if kind in LINE_KINDS.values() and element["type"] != "way":
            continue
        geometry = _geometry(element, kind)
        if geometry is None or geometry.is_empty:
            continue
        yield Asset(
            osm_type=element["type"],
            osm_id=int(element["id"]),
            kind=kind,
            geometry=geometry,
            name=tags.get("name"),
            operator=tags.get("operator"),
            voltage_kv=parse_voltage_kv(tags.get("voltage")),
            tags=tags,
        )


def fetch(client: httpx.Client, url: str, iso_region: str) -> list[Asset]:
    """Ask Overpass for the region's assets. One request, one deadline, one exception type."""
    try:
        response = client.post(url, data={"data": query(iso_region)}, timeout=360)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise OverpassError(f"Overpass request failed: {error}") from error
    remark = payload.get("remark") or ""
    if "error" in remark.lower():  # Overpass reports timeouts as a 200 with a remark
        raise OverpassError(f"Overpass gave up: {remark}")
    return list(parse(payload))
