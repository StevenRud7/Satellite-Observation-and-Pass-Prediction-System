from datetime import datetime, timedelta, timezone

from app.core.ranking import rank_opportunities
from app.schemas.pass_event import PassEvent
from app.schemas.ranking import RankedOpportunity
from app.schemas.visibility import (
    ConfidenceLevel,
    MethodVisibility,
    ObservationMethod,
    VisibilityClassification,
)

REFERENCE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_opportunity(
    norad_id: int, score: int, max_elevation_deg: float = 60.0
) -> RankedOpportunity:
    pass_event = PassEvent(
        rise_time=REFERENCE,
        peak_time=REFERENCE + timedelta(seconds=150),
        set_time=REFERENCE + timedelta(seconds=300),
        rise_azimuth_deg=0.0,
        peak_azimuth_deg=90.0,
        set_azimuth_deg=180.0,
        max_elevation_deg=max_elevation_deg,
        duration_seconds=300.0,
        rise_range_km=1500.0,
        max_range_km=1000.0,
        set_range_km=1500.0,
        min_elevation_threshold_deg=10.0,
    )
    visibility = MethodVisibility(
        method=ObservationMethod.NAKED_EYE,
        score=score,
        classification=VisibilityClassification.POSSIBLE,
        confidence=ConfidenceLevel.MEDIUM,
        factors=[],
        limitations=[],
    )
    return RankedOpportunity(
        norad_id=norad_id,
        satellite_name=f"SAT-{norad_id}",
        pass_event=pass_event,
        visibility=visibility,
    )


def test_ranked_opportunities_are_sorted_descending_by_score() -> None:
    opportunities = [
        _make_opportunity(1, score=40),
        _make_opportunity(2, score=90),
        _make_opportunity(3, score=65),
    ]

    ranked = rank_opportunities(opportunities)

    assert [o.norad_id for o in ranked] == [2, 3, 1]


def test_min_score_filters_out_low_scoring_opportunities() -> None:
    opportunities = [_make_opportunity(1, score=20), _make_opportunity(2, score=80)]

    ranked = rank_opportunities(opportunities, min_score=50)

    assert [o.norad_id for o in ranked] == [2]


def test_min_elevation_filter() -> None:
    opportunities = [
        _make_opportunity(1, score=50, max_elevation_deg=15.0),
        _make_opportunity(2, score=50, max_elevation_deg=45.0),
    ]

    ranked = rank_opportunities(opportunities, min_elevation_deg=30.0)

    assert [o.norad_id for o in ranked] == [2]


def test_max_elevation_filter() -> None:
    opportunities = [
        _make_opportunity(1, score=50, max_elevation_deg=15.0),
        _make_opportunity(2, score=50, max_elevation_deg=45.0),
    ]

    ranked = rank_opportunities(opportunities, max_elevation_deg=30.0)

    assert [o.norad_id for o in ranked] == [1]


def test_limit_truncates_results() -> None:
    opportunities = [_make_opportunity(i, score=i) for i in range(1, 6)]

    ranked = rank_opportunities(opportunities, limit=2)

    assert len(ranked) == 2
    assert [o.norad_id for o in ranked] == [5, 4]


def test_empty_input_returns_empty_list() -> None:
    assert rank_opportunities([]) == []


def test_no_filters_returns_all_sorted() -> None:
    opportunities = [_make_opportunity(1, score=10), _make_opportunity(2, score=20)]

    ranked = rank_opportunities(opportunities)

    assert len(ranked) == 2
