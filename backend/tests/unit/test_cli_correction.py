import json
from pathlib import Path

import pytest

from jugrid.cli import load_correction
from jugrid.config import Settings


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    card = {
        "version": "test-1",
        "climate_model": "EC-Earth3",
        "bbox": [6.62, 44.06, 9.22, 46.47],
        "variables": {},
    }
    (tmp_path / "card.json").write_text(json.dumps(card))
    return tmp_path


def test_the_model_applies_to_the_region_it_was_trained_for(model_dir: Path) -> None:
    correction = load_correction(Settings(), model_dir)
    assert correction is not None
    assert correction.version == "test-1"


def test_another_region_gets_the_raw_projections(
    model_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(region_bbox="10,44,11,45")
    assert load_correction(settings, model_dir) is None
    assert "trained for another region" in caplog.text


def test_another_climate_model_gets_the_raw_projections(model_dir: Path) -> None:
    assert load_correction(Settings(climate_model="MPI-ESM1-2-HR"), model_dir) is None


def test_the_correction_can_be_turned_off(model_dir: Path) -> None:
    assert load_correction(Settings(bias_correction=False), model_dir) is None


def test_no_model_shipped_means_raw_projections(tmp_path: Path) -> None:
    assert load_correction(Settings(), tmp_path) is None
