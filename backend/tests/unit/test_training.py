"""The training run end to end, on a small synthetic store where the model is known to be off."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from jugrid.climate.store import ClimateStore, open_store
from jugrid.correction import train
from jugrid.correction.model import BiasCorrection
from jugrid.geo import BBox
from jugrid.sources.nexgddp import VARIABLES

BBOX = BBox(west=7.0, south=45.0, east=7.5, north=45.5)
YEARS = range(2000, 2004)
LAT, LON = [45.125, 45.375, 45.625], [7.125, 7.375, 7.625]
# Like E-OBS, the observed wind sits on a grid shifted 0.1 degrees east of the others.
WIND_LON = [7.025, 7.275, 7.525, 7.775]
LOC = {"tasmax": 22.0, "tas": 12.0, "pr": 3.0, "sfcWind": 3.0}


def year_of(
    variable: str, year: int, seed: int, biased: bool, lon: list[float] = LON
) -> xr.DataArray:
    rng = np.random.default_rng(seed)
    time = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    shape = (len(time), len(LAT), len(lon))
    if variable in {"pr", "sfcWind"}:
        values = rng.gamma(1.2, LOC[variable], shape) * (0.6 if biased else 1.0)
    else:
        seasonal = 8 * np.sin(2 * np.pi * (time.day_of_year.values - 110) / 365)[:, None, None]
        values = LOC[variable] + seasonal + rng.normal(0, 3, shape) - (2.5 if biased else 0)
    return xr.DataArray(
        values.astype("float32"),
        dims=("time", "lat", "lon"),
        coords={"time": time, "lat": LAT, "lon": lon},
        name=variable,
    )


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("training")
    store = ClimateStore(open_store(str(root / "climate.zarr")))
    for i, variable in enumerate(VARIABLES):
        for year in YEARS:
            store.write_year(
                "baseline", variable, year, year_of(variable, year, i * 100 + year, True)
            )
            lon = WIND_LON if variable == "sfcWind" else LON
            store.write_year(
                "observed", variable, year, year_of(variable, year, i * 7 + year, False, lon)
            )
    out = root / "model"
    train.main(
        [
            "--store",
            str(root / "climate.zarr"),
            "--out",
            str(out),
            "--first-year",
            "2000",
            "--test-from",
            "2003",
            "--last-year",
            "2003",
            "--bbox",
            "7.0,45.0,7.5,45.5",
            "--tracking-uri",
            f"sqlite:///{root / 'mlflow.db'}",
            "--max-iter",
            "60",
        ]
    )
    return out, json.loads((out / "card.json").read_text())


def test_writes_one_onnx_model_per_variable_and_a_card(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    out, card = trained
    assert {p.name for p in out.glob("*.onnx")} == {f"{v}.onnx" for v in VARIABLES}
    assert card["reference"] == "E-OBS v32.0e ensemble mean"
    assert card["trained_on"] == [2000, 2003]
    assert card["bbox"] == [7.0, 45.0, 7.5, 45.5]


def test_the_model_beats_the_raw_projections_on_years_it_did_not_see(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    _, card = trained
    for variable, entry in card["variables"].items():
        held_out = entry["held_out_years"]
        assert held_out["model"] < held_out["raw"], variable


def test_the_model_beats_the_raw_projections_on_cells_it_did_not_see(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    _, card = trained
    for variable, entry in card["variables"].items():
        held_out = entry["held_out_cells"]
        assert held_out["model"] < held_out["raw"], variable


def test_indicators_are_compared_with_what_was_observed(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    _, card = trained
    assert set(card["indicators"]) == {
        "hot_days",
        "wettest_day",
        "windiest_day",
        "wet_snow_days",
    }
    for name, scores in card["indicators"].items():
        assert all(np.isfinite(v) for v in scores.values()), name


def test_the_onnx_model_corrects_like_the_one_trained(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    out, _ = trained
    correction = BiasCorrection.load(out)
    assert correction is not None
    data = year_of("tasmax", 2001, 5, True)
    corrected = correction.correct(data, "tasmax")
    assert corrected.shape == data.shape
    # The synthetic model runs 2.5 degrees cold; the correction warms it by about that.
    assert 1.5 < float((corrected - data).mean()) < 3.5


def test_covers_only_the_region_and_model_it_was_trained_for(
    trained: tuple[Path, dict[str, Any]],
) -> None:
    correction = BiasCorrection.load(trained[0])
    assert correction is not None
    assert correction.covers(BBOX, "EC-Earth3")
    assert not correction.covers(BBox(west=10, south=44, east=11, north=45), "EC-Earth3")
    assert not correction.covers(BBOX, "MPI-ESM1-2-HR")


def test_no_card_means_no_correction(tmp_path: Path) -> None:
    assert BiasCorrection.load(tmp_path) is None


def test_fills_only_the_observed_years_the_store_lacks(tmp_path: Path) -> None:
    store = ClimateStore(open_store(str(tmp_path / "climate.zarr")))
    store.write_year("observed", "tasmax", 2000, year_of("tasmax", 2000, 1, False))
    asked: list[tuple[str, int]] = []

    def read(variable: str, year: int) -> xr.DataArray:
        asked.append((variable, year))
        return year_of(variable, year, 2, False)

    written = train.fill_observed(store, range(2000, 2002), read)
    assert written == len(VARIABLES) * 2 - 1
    assert ("tasmax", 2000) not in asked
    assert store.has_year("observed", "sfcWind", 2001)
