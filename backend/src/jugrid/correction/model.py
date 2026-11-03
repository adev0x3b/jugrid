"""The trained bias-correction model, as the ingest runs it: ONNX files and a model card.

``python -m jugrid.correction.train`` writes them to ``model/`` next to this file, and they ship
with the package, so a model change is a reviewed commit like any other.
"""

import json
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
import xarray as xr

from jugrid.correction import quantiles
from jugrid.geo import BBox

MODEL_DIR = Path(__file__).parent / "model"
_BBOX_TOLERANCE = 0.01


class BiasCorrection:
    def __init__(self, directory: Path, card: dict[str, Any]) -> None:
        self.directory, self.card = directory, card
        self._sessions: dict[str, ort.InferenceSession] = {}

    @classmethod
    def load(cls, directory: Path = MODEL_DIR) -> BiasCorrection | None:
        card = directory / "card.json"
        if not card.exists():
            return None
        return cls(directory, json.loads(card.read_text()))

    @property
    def version(self) -> str:
        return str(self.card["version"])

    @property
    def variables(self) -> list[str]:
        return list(self.card["variables"])

    def covers(self, bbox: BBox, climate_model: str) -> bool:
        """Trained for this region and climate model: the corrections are learnt per place."""
        trained = self.card["bbox"]
        here = [bbox.west, bbox.south, bbox.east, bbox.north]
        same_box = all(abs(a - b) <= _BBOX_TOLERANCE for a, b in zip(trained, here, strict=True))
        return same_box and self.card["climate_model"] == climate_model

    def _session(self, variable: str) -> ort.InferenceSession:
        if variable not in self._sessions:
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            self._sessions[variable] = ort.InferenceSession(
                str(self.directory / f"{variable}.onnx"),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        return self._sessions[variable]

    def predict(self, variable: str, x: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        session = self._session(variable)
        out = session.run(None, {session.get_inputs()[0].name: x})[0]
        return np.asarray(out, dtype=np.float32).ravel()

    def correct(self, data: xr.DataArray, variable: str) -> xr.DataArray:
        return quantiles.correct(data, partial(self.predict, variable), variable)
