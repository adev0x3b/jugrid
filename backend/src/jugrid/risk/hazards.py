"""The hazards JuGrid scores, the scenarios it compares and the asset kinds it knows.

Every number a person reads on the map comes from these tables, so they live in one place
and the methodology document quotes them.
"""

from dataclasses import dataclass
from enum import StrEnum


class Hazard(StrEnum):
    HEAT = "heat"
    HEAVY_RAIN = "heavy_rain"
    WIND = "wind"
    WET_SNOW = "wet_snow"
    FLOOD = "flood"


class AssetKind(StrEnum):
    LINE = "line"
    MINOR_LINE = "minor_line"
    CABLE = "cable"
    SUBSTATION = "substation"
    PLANT = "plant"


class Level(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True, slots=True)
class Scenario:
    key: str
    label: str
    experiment: str  # NEX-GDDP-CMIP6 experiment: historical, ssp245, ssp585
    start_year: int
    end_year: int


@dataclass(frozen=True, slots=True)
class HazardSpec:
    hazard: Hazard
    label: str
    indicator: str
    unit: str
    # The indicator value that scores 0 and the one that scores 1; linear in between.
    low: float
    high: float
    climate: bool  # False: the hazard has no projection and reads the same in every scenario


HAZARDS: dict[Hazard, HazardSpec] = {
    spec.hazard: spec
    for spec in (
        HazardSpec(Hazard.HEAT, "Extreme heat", "Days a year above 35 °C", "days/yr", 0, 20, True),
        HazardSpec(Hazard.HEAVY_RAIN, "Heavy rain", "Wettest day of the year", "mm", 40, 120, True),
        HazardSpec(Hazard.WIND, "Wind", "Windiest day of the year", "m/s", 5, 12, True),
        HazardSpec(
            Hazard.WET_SNOW, "Wet snow", "Days a year of wet snow on lines", "days/yr", 1, 12, True
        ),
        HazardSpec(
            Hazard.FLOOD, "River flood", "Water depth, 1-in-100-year flood", "m", 0, 1.5, False
        ),
    )
}

# How much each hazard hurts each kind of asset, from 0 (not at all) to 1 (directly).
# Overhead lines sag in heat and break under wind and wet-snow sleeves; underground cables
# fear water and heat, not wind; substations and plants fear water most.
VULNERABILITY: dict[AssetKind, dict[Hazard, float]] = {
    AssetKind.LINE: {
        Hazard.HEAT: 0.7,
        Hazard.HEAVY_RAIN: 0.3,
        Hazard.WIND: 1.0,
        Hazard.WET_SNOW: 1.0,
        Hazard.FLOOD: 0.3,
    },
    AssetKind.MINOR_LINE: {
        Hazard.HEAT: 0.6,
        Hazard.HEAVY_RAIN: 0.4,
        Hazard.WIND: 1.0,
        Hazard.WET_SNOW: 1.0,
        Hazard.FLOOD: 0.4,
    },
    AssetKind.CABLE: {
        Hazard.HEAT: 0.5,
        Hazard.HEAVY_RAIN: 0.5,
        Hazard.WIND: 0.0,
        Hazard.WET_SNOW: 0.0,
        Hazard.FLOOD: 0.7,
    },
    AssetKind.SUBSTATION: {
        Hazard.HEAT: 0.7,
        Hazard.HEAVY_RAIN: 0.6,
        Hazard.WIND: 0.3,
        Hazard.WET_SNOW: 0.4,
        Hazard.FLOOD: 1.0,
    },
    AssetKind.PLANT: {
        Hazard.HEAT: 0.6,
        Hazard.HEAVY_RAIN: 0.5,
        Hazard.WIND: 0.5,
        Hazard.WET_SNOW: 0.4,
        Hazard.FLOOD: 0.9,
    },
}

# Score bands: a score below the first bound is low, and so on.
LEVEL_BOUNDS: tuple[tuple[float, Level], ...] = (
    (0.25, Level.LOW),
    (0.5, Level.MEDIUM),
    (0.75, Level.HIGH),
)


class ScenarioKey(StrEnum):
    BASELINE = "baseline"
    SSP245_2050 = "ssp245_2050"
    SSP585_2050 = "ssp585_2050"


class RiskView(StrEnum):
    """What the map colours by: one hazard, or the worst of them."""

    OVERALL = "overall"
    HEAT = "heat"
    HEAVY_RAIN = "heavy_rain"
    WIND = "wind"
    WET_SNOW = "wet_snow"
    FLOOD = "flood"
