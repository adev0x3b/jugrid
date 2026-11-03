"""Quantile delta mapping: the arithmetic the bias-correction model is built on.

A climate model's day is not a real day, so its values cannot be paired with observations day
by day; their distributions can. For each cell and month, the model's q-th quantile over a
historical period is set against the observed q-th quantile, and the difference (a ratio for
rain and wind) is the correction at q. A projected day is then corrected by the delta at its own
quantile within its own period, which keeps the change the model projects (Cannon et al. 2015,
quantile delta mapping) instead of capping the future at the historical extremes.

``delta_cube`` and ``apply_cube`` do this per cell, from the empirical quantiles; the trained
model learns the same deltas from the quantile, the season and the place, so it is smooth across
cells and months and also corrects a cell it never saw.
"""

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import xarray as xr

Array = npt.NDArray[np.float64]

# Dense in the tails, where heat waves, cold snaps and the wettest days are.
QUANTILES = np.concatenate([[0.001, 0.005], np.arange(1, 100) / 100, [0.995, 0.999]])
MULTIPLICATIVE = {"pr", "sfcWind"}
# Added before taking a ratio, so a dry day does not divide by zero.
_EPS = {"pr": 0.1, "sfcWind": 0.1}
_MAX_LOG_RATIO = 3.0
# Degrees: two cell centres closer than this are the same cell.
GRID_TOLERANCE = 0.01


def delta(model: npt.ArrayLike, observed: npt.ArrayLike, variable: str) -> Array:
    """What turns ``model`` into ``observed``: a difference, or a log ratio for rain and wind."""
    m, o = np.asarray(model, dtype=float), np.asarray(observed, dtype=float)
    if variable in MULTIPLICATIVE:
        eps = _EPS[variable]
        ratio = np.log((np.maximum(o, 0) + eps) / (np.maximum(m, 0) + eps))
        return np.asarray(np.clip(ratio, -_MAX_LOG_RATIO, _MAX_LOG_RATIO), dtype=float)
    return np.asarray(o - m, dtype=float)


def apply_delta(values: npt.ArrayLike, d: npt.ArrayLike, variable: str) -> Array:
    v, d_ = np.asarray(values, dtype=float), np.asarray(d, dtype=float)
    if variable in MULTIPLICATIVE:
        eps = _EPS[variable]
        d_ = np.clip(d_, -_MAX_LOG_RATIO, _MAX_LOG_RATIO)
        return np.asarray(np.maximum((np.maximum(v, 0) + eps) * np.exp(d_) - eps, 0), dtype=float)
    return np.asarray(v + d_, dtype=float)


def ranks(data: xr.DataArray) -> xr.DataArray:
    """Each day's quantile within its cell and calendar month over the period, in (0, 1)."""
    values = data.transpose("time", "lat", "lon").values.astype(float)
    months = data["time"].dt.month.values
    out = np.full(values.shape, np.nan)
    for month in np.unique(months):
        rows = np.flatnonzero(months == month)
        block = values[rows]
        missing = np.isnan(block)
        order = np.argsort(np.where(missing, np.inf, block), axis=0, kind="stable")
        rank = np.argsort(order, axis=0, kind="stable") + 1.0
        count = (~missing).sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            q = (rank - 0.5) / count
        out[rows] = np.where(missing, np.nan, q)
    return xr.DataArray(
        out, dims=("time", "lat", "lon"), coords=data.transpose("time", "lat", "lon").coords
    )


def season(months: npt.ArrayLike) -> Array:
    """The month as a point on a circle, so December sits next to January."""
    angle = 2 * np.pi * (np.asarray(months, dtype=float) - 0.5) / 12
    return np.stack([np.sin(angle), np.cos(angle)], axis=-1)


def _rows(q: Array, months: Array, lat: Array, lon: Array) -> npt.NDArray[np.float32]:
    s = season(months)
    return np.column_stack([q, s[:, 0], s[:, 1], lat, lon]).astype(np.float32)


FEATURES = ("quantile", "season_sin", "season_cos", "lat", "lon")


def features(q: xr.DataArray) -> npt.NDArray[np.float32]:
    """One row per (day, cell), in the cube's order: the model's inputs."""
    q = q.transpose("time", "lat", "lon")
    t, la, lo = np.meshgrid(
        np.arange(q.sizes["time"]), q["lat"].values, q["lon"].values, indexing="ij"
    )
    months = q["time"].dt.month.values[t.ravel()]
    return _rows(q.values.ravel(), months, la.ravel(), lo.ravel())


def _monthly_quantiles(data: xr.DataArray) -> xr.DataArray:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "All-NaN slice", RuntimeWarning)  # cells with no data
        return (
            data.groupby("time.month")
            # Hazen's plotting position, the same as ``ranks``: a day's own quantile returns it.
            .quantile(QUANTILES, dim="time", skipna=True, method="hazen")
            .transpose("month", "quantile", "lat", "lon")
        )


def _matches(observed: xr.DataArray, model: xr.DataArray, axis: str) -> bool:
    gaps = np.abs(observed[axis].values[None, :] - model[axis].values[:, None]).min(axis=1)
    return bool((gaps <= GRID_TOLERANCE).all())


def on_grid(observed: xr.DataArray, model: xr.DataArray) -> xr.DataArray:
    """The observations at the model's cells: the same cells when both grids agree, otherwise
    interpolated (E-OBS wind sits on a grid shifted 0.1 degrees from its temperature and rain)."""
    if _matches(observed, model, "lat") and _matches(observed, model, "lon"):
        return observed.reindex(
            lat=model["lat"], lon=model["lon"], method="nearest", tolerance=GRID_TOLERANCE
        )
    return observed.interp(lat=model["lat"], lon=model["lon"], method="linear")


def delta_cube(model: xr.DataArray, observed: xr.DataArray, variable: str) -> xr.DataArray:
    """The empirical correction per (month, quantile, lat, lon)."""
    mq = _monthly_quantiles(model)
    oq = _monthly_quantiles(on_grid(observed, model))
    return xr.DataArray(delta(mq.values, oq.values, variable), dims=mq.dims, coords=mq.coords)


@dataclass(frozen=True)
class Table:
    """One row per (month, quantile, cell) of a historical period."""

    x: npt.NDArray[np.float32]  # features
    y: Array  # the delta that turns the model's quantile into the observed one
    cell: npt.NDArray[np.int64]
    model: Array  # the model's quantile value
    observed: Array  # the observed quantile value


def training_table(model: xr.DataArray, observed: xr.DataArray, variable: str) -> Table:
    mq = _monthly_quantiles(model)
    oq = _monthly_quantiles(on_grid(observed, model))
    m, q, la, lo = np.meshgrid(
        mq["month"].values,
        mq["quantile"].values,
        mq["lat"].values,
        mq["lon"].values,
        indexing="ij",
    )
    n_lon = mq.sizes["lon"]
    li, lj = np.meshgrid(np.arange(mq.sizes["lat"]), np.arange(n_lon), indexing="ij")
    cell = np.broadcast_to(li * n_lon + lj, m.shape).ravel()
    model_q, observed_q = mq.values.ravel(), oq.values.ravel()
    keep = ~(np.isnan(model_q) | np.isnan(observed_q))
    x = _rows(q.ravel(), m.ravel(), la.ravel(), lo.ravel())
    return Table(
        x=x[keep],
        y=delta(model_q[keep], observed_q[keep], variable),
        cell=cell[keep].astype(np.int64),
        model=model_q[keep],
        observed=observed_q[keep],
    )


def apply_cube(data: xr.DataArray, cube: xr.DataArray, variable: str) -> xr.DataArray:
    """Correct daily data with an empirical ``delta_cube``, cell by cell."""
    data = data.transpose("time", "lat", "lon")
    q = ranks(data).values
    months = data["time"].dt.month.values
    d = np.full(q.shape, np.nan)
    for i in range(data.sizes["lat"]):
        for j in range(data.sizes["lon"]):
            for month in np.unique(months):
                rows = months == month
                curve = cube.sel(month=month).values[:, i, j]
                if np.isnan(curve).any():
                    continue
                d[rows, i, j] = np.interp(q[rows, i, j], QUANTILES, curve)
    corrected = apply_delta(data.values, d, variable)
    corrected = np.where(np.isnan(d), data.values, corrected)
    return data.copy(data=corrected.astype(data.dtype))


Predict = Callable[[npt.NDArray[np.float32]], npt.ArrayLike]


def correct(data: xr.DataArray, predict: Predict, variable: str) -> xr.DataArray:
    """Correct daily data with a model that predicts the delta from ``features``."""
    data = data.transpose("time", "lat", "lon")
    x = features(ranks(data))
    valid = ~np.isnan(x).any(axis=1)
    flat = data.values.astype(float).ravel()
    out = flat.copy()
    if valid.any():
        out[valid] = apply_delta(flat[valid], np.asarray(predict(x[valid])).ravel(), variable)
    return data.copy(data=out.reshape(data.shape).astype(data.dtype))
