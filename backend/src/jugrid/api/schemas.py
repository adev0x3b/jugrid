"""What the API answers, as the web app reads it."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ScenarioOut(BaseModel):
    key: str
    label: str
    start_year: int
    end_year: int


class HazardOut(BaseModel):
    key: str
    label: str
    indicator: str
    unit: str
    low: float
    high: float
    projected: bool


class SourceOut(BaseModel):
    name: str
    url: str
    license: str


class RunOut(BaseModel):
    step: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    detail: str | None


class HeldOutYearsOut(BaseModel):
    raw: float
    empirical: float
    model: float


class HeldOutCellsOut(BaseModel):
    raw: float
    model: float


class VariableScoreOut(BaseModel):
    transform: str
    unit: str
    held_out_years: HeldOutYearsOut
    held_out_cells: HeldOutCellsOut


class IndicatorScoreOut(BaseModel):
    observed_mean: float
    raw_mean: float
    model_mean: float
    raw_error: float
    model_error: float


class CorrectionOut(BaseModel):
    """The model card of the bias correction the scores use."""

    version: str
    method: str
    climate_model: str
    reference: str
    trained_on: tuple[int, int]
    held_out_from: int
    variables: dict[str, VariableScoreOut]
    indicators: dict[str, IndicatorScoreOut]


class Meta(BaseModel):
    region: str
    bbox: tuple[float, float, float, float]
    climate_model: str
    scenarios: list[ScenarioOut]
    hazards: list[HazardOut]
    kinds: list[str]
    vulnerability: dict[str, dict[str, float]]
    sources: list[SourceOut]
    runs: list[RunOut]
    correction: CorrectionOut | None


class RiskOut(BaseModel):
    scenario: str
    hazard: str
    value: float | None
    score: float | None
    level: str | None
    flooded_km: float | None


class AssetOut(BaseModel):
    id: int
    osm_type: str
    osm_id: int
    osm_url: str
    kind: str
    name: str | None
    operator: str | None
    voltage_kv: float | None
    length_km: float
    lon: float
    lat: float
    geometry: dict[str, Any]
    tags: dict[str, str]
    risks: list[RiskOut]


class KindSummary(BaseModel):
    kind: str
    count: int
    length_km: float
    levels: dict[str, int]


class RankedAsset(BaseModel):
    id: int
    kind: str
    name: str | None
    operator: str | None
    voltage_kv: float | None
    length_km: float
    value: float | None
    score: float
    level: str
    baseline_score: float | None
    change: float | None
