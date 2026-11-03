"""Train the bias-correction model: ``python -m jugrid.correction.train`` (needs the ml group).

Reads the historical projections (scenario ``baseline``) and the E-OBS observations (``observed``)
from the climate store, then for each variable:

1. scores a model trained on the early years against the years it did not see, next to the raw
   projections and to per-cell empirical quantile delta mapping;
2. scores it on cells it did not see (five folds over the cells, all years);
3. trains the final model on every year, checks its ONNX export predicts the same, and writes it.

Every number goes to MLflow and to ``card.json``, which the API serves as the model card.
"""

import argparse
import json
import logging
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import numpy.typing as npt
import xarray as xr
from skl2onnx import convert_sklearn
from skl2onnx.common import tree_ensemble
from skl2onnx.common.data_types import FloatTensorType
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

from jugrid import logs
from jugrid.climate import indicators
from jugrid.climate.store import ClimateStore, open_store
from jugrid.correction import quantiles as qm
from jugrid.correction.model import MODEL_DIR, BiasCorrection
from jugrid.geo import BBox
from jugrid.sources import eobs
from jugrid.sources.nexgddp import VARIABLES

log = logging.getLogger(__name__)

CLIMATE_MODEL = "EC-Earth3"


def regressor(max_iter: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=0,
    )


def _quantile_error(corrected: xr.DataArray, observed: xr.DataArray, variable: str) -> float:
    """Mean absolute gap between corrected and observed quantiles, per cell and month."""
    table = qm.training_table(corrected, observed, variable)
    return float(np.mean(np.abs(table.model - table.observed)))


def held_out_years(
    model: xr.DataArray, observed: xr.DataArray, variable: str, test_from: int, max_iter: int
) -> tuple[dict[str, float], xr.DataArray]:
    early = model.time.dt.year < test_from
    train_model, test_model = model.sel(time=early), model.sel(time=~early)
    train_obs = observed.sel(time=observed.time.dt.year < test_from)
    test_obs = observed.sel(time=observed.time.dt.year >= test_from)
    table = qm.training_table(train_model, train_obs, variable)
    fitted = regressor(max_iter).fit(table.x, table.y)
    corrected = qm.correct(test_model, fitted.predict, variable)
    empirical = qm.apply_cube(test_model, qm.delta_cube(train_model, train_obs, variable), variable)
    scores = {
        "raw": _quantile_error(test_model, test_obs, variable),
        "empirical": _quantile_error(empirical, test_obs, variable),
        "model": _quantile_error(corrected, test_obs, variable),
    }
    return scores, corrected


def held_out_cells(table: qm.Table, variable: str, max_iter: int) -> dict[str, float]:
    folds = min(5, len(np.unique(table.cell)))
    predicted = np.empty_like(table.y)
    for train_rows, test_rows in GroupKFold(n_splits=folds).split(table.x, groups=table.cell):
        fitted = regressor(max_iter).fit(table.x[train_rows], table.y[train_rows])
        predicted[test_rows] = fitted.predict(table.x[test_rows])
    corrected = qm.apply_delta(table.model, predicted, variable)
    return {
        "raw": float(np.mean(np.abs(table.model - table.observed))),
        "model": float(np.mean(np.abs(corrected - table.observed))),
    }


@contextmanager
def _integer_missing_flags() -> Iterator[None]:
    """skl2onnx 1.20 passes a Python bool for ``nodes_missing_value_tracks_true`` on gradient
    boosting trees, which onnx 1.23 refuses in an integer attribute; cast it while converting."""
    original = tree_ensemble.add_node

    def add_node(*args: Any, **kwargs: Any) -> Any:
        flag = kwargs.get("nodes_missing_value_tracks_true")
        if flag is not None:
            kwargs["nodes_missing_value_tracks_true"] = int(flag)
        return original(*args, **kwargs)

    tree_ensemble.add_node = add_node
    try:
        yield
    finally:
        tree_ensemble.add_node = original


def to_onnx(fitted: HistGradientBoostingRegressor, x: npt.NDArray[np.float32]) -> bytes:
    with _integer_missing_flags():
        onx = convert_sklearn(
            fitted, initial_types=[("X", FloatTensorType([None, x.shape[1]]))], target_opset=18
        )
    return bytes(onx.SerializeToString())


class ExportMismatchError(RuntimeError):
    """The ONNX file does not predict what the trained model does."""


def check_export(
    directory: Path,
    variable: str,
    fitted: HistGradientBoostingRegressor,
    x: npt.NDArray[np.float32],
) -> None:
    """The file the ingest will run must predict what the trained model does."""
    sample = x[:: max(1, len(x) // 5000)]
    exported = BiasCorrection(directory, {"variables": {}}).predict(variable, sample)
    gap = float(np.max(np.abs(exported - fitted.predict(sample))))
    if gap > 1e-3:
        raise ExportMismatchError(f"{variable}: ONNX differs from scikit-learn by {gap}")


def indicator_scores(
    model: dict[str, xr.DataArray],
    corrected: dict[str, xr.DataArray],
    observed: dict[str, xr.DataArray],
) -> dict[str, dict[str, float]]:
    """Mean absolute error and mean bias over cells of each indicator, raw and corrected."""

    def all_of(d: dict[str, xr.DataArray]) -> dict[str, xr.DataArray]:
        return {
            "hot_days": indicators.hot_days(d["tasmax"]),
            "wettest_day": indicators.wettest_day(d["pr"]),
            "windiest_day": indicators.windiest_day(d["sfcWind"]),
            "wet_snow_days": indicators.wet_snow_days(d["tas"], d["pr"]),
        }

    grid = model["tasmax"]
    obs = {
        k: v.reindex(lat=grid.lat, lon=grid.lon, method="nearest", tolerance=0.01)
        for k, v in observed.items()
    }
    raw, fixed, truth = all_of(model), all_of(corrected), all_of(obs)
    out: dict[str, dict[str, float]] = {}
    for name in truth:
        out[name] = {
            "observed_mean": float(truth[name].mean()),
            "raw_mean": float(raw[name].mean()),
            "model_mean": float(fixed[name].mean()),
            "raw_error": float(abs(raw[name] - truth[name]).mean()),
            "model_error": float(abs(fixed[name] - truth[name]).mean()),
        }
    return out


def git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jugrid.correction.train", description=__doc__)
    parser.add_argument("--store", default="data/climate.zarr", help="climate store URL")
    parser.add_argument("--out", type=Path, default=MODEL_DIR, help="where the model goes")
    parser.add_argument("--first-year", type=int, default=1995)
    parser.add_argument("--test-from", type=int, default=2010, help="first held-out year")
    parser.add_argument("--last-year", type=int, default=2014)
    parser.add_argument("--bbox", default="6.62,44.06,9.22,46.47", help="west,south,east,north")
    parser.add_argument("--tracking-uri", default=None, help="MLflow tracking URI")
    parser.add_argument("--max-iter", type=int, default=300, help="boosting rounds")
    args = parser.parse_args(argv)
    logs.configure("text")

    store = ClimateStore(open_store(args.store))
    bbox = BBox.parse(args.bbox)
    years = range(args.first_year, args.last_year + 1)
    model = {v: store.read_period("baseline", v, years).load() for v in VARIABLES}
    observed = {v: store.read_period("observed", v, years).load() for v in VARIABLES}

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment("jugrid-bias-correction")
    args.out.mkdir(parents=True, exist_ok=True)
    card: dict[str, Any] = {
        "version": datetime.now(UTC).strftime("%Y-%m-%d") + "-" + git_revision(),
        "method": "Quantile delta mapping learnt by gradient boosting, per cell and month",
        "climate_model": CLIMATE_MODEL,
        "reference": f"E-OBS {eobs.VERSION} ensemble mean",
        "bbox": [bbox.west, bbox.south, bbox.east, bbox.north],
        "trained_on": [args.first_year, args.last_year],
        "held_out_from": args.test_from,
        "features": list(qm.FEATURES),
        "variables": {},
    }
    with mlflow.start_run(run_name=card["version"]):
        mlflow.log_params(
            {
                "climate_model": CLIMATE_MODEL,
                "reference": card["reference"],
                "years": f"{args.first_year}-{args.last_year}",
                "held_out_from": args.test_from,
                "quantiles": len(qm.QUANTILES),
                **{f"hgb_{k}": v for k, v in regressor(args.max_iter).get_params().items()},
            }
        )
        test_years: dict[str, dict[str, xr.DataArray]] = {
            "model": {},
            "corrected": {},
            "observed": {},
        }
        for variable in VARIABLES:
            years_score, corrected = held_out_years(
                model[variable], observed[variable], variable, args.test_from, args.max_iter
            )
            table = qm.training_table(model[variable], observed[variable], variable)
            cells_score = held_out_cells(table, variable, args.max_iter)
            fitted = regressor(args.max_iter).fit(table.x, table.y)
            (args.out / f"{variable}.onnx").write_bytes(to_onnx(fitted, table.x))
            check_export(args.out, variable, fitted, table.x)
            card["variables"][variable] = {
                "transform": "ratio" if variable in qm.MULTIPLICATIVE else "difference",
                "unit": "°C"
                if variable.startswith("tas")
                else ("mm" if variable == "pr" else "m/s"),
                "held_out_years": years_score,
                "held_out_cells": cells_score,
                "rows": int(table.x.shape[0]),
            }
            for split, scores in (("years", years_score), ("cells", cells_score)):
                for method, value in scores.items():
                    mlflow.log_metric(f"{variable}.held_out_{split}.{method}", value)
            late = model[variable].time.dt.year >= args.test_from
            test_years["model"][variable] = model[variable].sel(time=late)
            test_years["corrected"][variable] = corrected
            test_years["observed"][variable] = observed[variable].sel(
                time=observed[variable].time.dt.year >= args.test_from
            )
            log.info("%s: %s %s", variable, years_score, cells_score)

        card["indicators"] = indicator_scores(
            test_years["model"], test_years["corrected"], test_years["observed"]
        )
        for name, scores in card["indicators"].items():
            for key, value in scores.items():
                mlflow.log_metric(f"indicator.{name}.{key}", value)
        (args.out / "card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n")

        mlflow.log_artifacts(str(args.out), artifact_path="model")
    log.info("model %s written to %s", card["version"], args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
