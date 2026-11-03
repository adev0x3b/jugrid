"""Small synthetic datasets shaped like the real sources."""

import numpy as np
import pandas as pd
import xarray as xr

LATS = np.array([44.875, 45.125, 45.375])
LONS = np.array([7.375, 7.625, 7.875])


def daily_cube(value: float | np.ndarray, year: int, name: str) -> xr.DataArray:
    """One year of a variable on a 3x3 grid around Turin, already in JuGrid's units."""
    time = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    data = np.broadcast_to(np.asarray(value, dtype="float32"), (len(time), 3, 3)).copy()
    return xr.DataArray(
        data,
        dims=("time", "lat", "lon"),
        coords={"time": time, "lat": LATS, "lon": LONS},
        name=name,
    )


def global_file(variable: str, year: int, kelvin: float = 300.0) -> xr.Dataset:
    """A NEX-GDDP-like global file: 0.25 degree cells, longitudes 0-360, noon timestamps."""
    lats = np.arange(-59.875, 90, 2.0)  # coarse, but placed like the real grid
    lons = np.arange(0.125, 360, 0.25)
    time = pd.date_range(f"{year}-01-01 12:00", periods=5, freq="D")
    values = np.full(
        (5, len(lats), len(lons)), kelvin if variable.startswith("tas") else 1e-4, dtype="float32"
    )
    return xr.Dataset(
        {variable: (("time", "lat", "lon"), values)},
        coords={"time": time, "lat": lats, "lon": lons},
    )
