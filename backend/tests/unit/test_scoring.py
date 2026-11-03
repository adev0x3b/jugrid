import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jugrid.risk.hazards import HAZARDS, VULNERABILITY, AssetKind, Hazard, Level
from jugrid.risk.scoring import asset_score, hazard_score, level, overall_score


class TestHazardScore:
    def test_is_linear_between_the_low_and_high_marks(self) -> None:
        # Heat scores 0 at 0 hot days and 1 at 20.
        assert hazard_score(Hazard.HEAT, 0) == 0
        assert hazard_score(Hazard.HEAT, 5) == pytest.approx(0.25)
        assert hazard_score(Hazard.HEAT, 20) == 1

    def test_is_clipped(self) -> None:
        assert hazard_score(Hazard.HEAVY_RAIN, 10) == 0
        assert hazard_score(Hazard.HEAVY_RAIN, 500) == 1

    @pytest.mark.parametrize("value", [None, math.nan])
    def test_unknown_values_have_no_score(self, value: float | None) -> None:
        assert hazard_score(Hazard.WIND, value) is None

    @given(st.sampled_from(list(Hazard)), st.floats(-1e6, 1e6), st.floats(-1e6, 1e6))
    def test_is_monotonic(self, hazard: Hazard, a: float, b: float) -> None:
        low, high = sorted((a, b))
        assert hazard_score(hazard, low) <= hazard_score(hazard, high)  # type: ignore[operator]


class TestAssetScore:
    def test_weights_the_hazard_score_by_the_kinds_vulnerability(self) -> None:
        # A substation (flood weight 1.0) and a line (0.3) on the same 0.75 m of water.
        assert asset_score(AssetKind.SUBSTATION, Hazard.FLOOD, 0.75) == pytest.approx(0.5)
        assert asset_score(AssetKind.LINE, Hazard.FLOOD, 0.75) == pytest.approx(0.15)

    def test_wind_does_not_reach_underground_cables(self) -> None:
        assert asset_score(AssetKind.CABLE, Hazard.WIND, 40) == 0

    def test_every_kind_has_a_weight_for_every_hazard(self) -> None:
        for kind in AssetKind:
            assert set(VULNERABILITY[kind]) == set(Hazard)
            assert all(0 <= w <= 1 for w in VULNERABILITY[kind].values())


class TestOverall:
    def test_is_the_worst_hazard(self) -> None:
        assert overall_score({Hazard.HEAT: 0.2, Hazard.WIND: 0.6, Hazard.FLOOD: None}) == 0.6

    def test_without_any_score_is_unknown(self) -> None:
        assert overall_score({Hazard.HEAT: None}) is None


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, Level.LOW),
        (0.2499, Level.LOW),
        (0.25, Level.MEDIUM),
        (0.5, Level.HIGH),
        (0.75, Level.VERY_HIGH),
        (1.0, Level.VERY_HIGH),
        (None, None),
    ],
)
def test_levels(score: float | None, expected: Level | None) -> None:
    assert level(score) == expected


def test_every_hazard_has_a_spec_with_a_rising_scale() -> None:
    assert set(HAZARDS) == set(Hazard)
    assert all(spec.high > spec.low for spec in HAZARDS.values())
