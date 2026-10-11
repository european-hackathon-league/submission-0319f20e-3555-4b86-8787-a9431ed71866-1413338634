"""Pure deterministic fixtures, labelled simulated; no model or network dependencies."""

import math

import pytest

from server.sentiment import LEXICON_FINGERPRINT, LEXICON_VERSION, lexicon_fingerprint, lexicon_score
from server.signals import weekly_momentum


def test_lexicon_change_requires_version_update():
    assert LEXICON_VERSION == "lexicon-v1"
    assert lexicon_fingerprint() == LEXICON_FINGERPRINT == "3316541d578d44edb66995e04475de9718ed8bf3eadc092292e8c1bd78c748a4"


@pytest.mark.parametrize(("text", "label"), [
    ("The seats are comfortable.", "positive"), ("The seats are not comfortable.", "negative"),
    ("The seats are not terrible.", "positive"), ("The seats are comfortable. The seats are terrible.", "mixed"),
    ("The car has four doors.", "neutral"), ("座椅非常舒适。", "positive"), ("座椅不舒适。", "negative"),
])
def test_negation_mixed_and_small_chinese_lexicon(text, label):
    score = lexicon_score(text)
    assert score["label"] == label
    assert -1 <= score["polarity"] <= 1 and math.isfinite(score["polarity"])
    for aspect in score["aspects"]:
        start, end = aspect["span"]
        assert 0 <= start < end <= len(text) and text[start:end].strip()


def test_intensifiers_and_contrast():
    ordinary = lexicon_score("The seats are comfortable.")
    intense = lexicon_score("The seats are very comfortable.")
    assert intense["polarity"] > ordinary["polarity"] > 0
    contrast = lexicon_score("The seats are comfortable but the ride is terrible.")
    assert contrast["topic"] == "driving-experience" and contrast["polarity"] < 0
    assert contrast["aspects"][1]["weight"] > contrast["aspects"][0]["weight"]
    assert lexicon_score("The seats are comfortable but the ride is terrible.", "comfort")["polarity"] > 0


def test_truncation_is_explicit_and_deterministic():
    text = "The seats are comfortable. " * 300
    one = lexicon_score(text)
    assert one == lexicon_score(text)
    assert one["details"]["truncated"] and one["details"]["analysed_chars"] == 4000


def test_weighted_momentum_calendar_gaps_and_eight_week_window():
    points = [{"week_start": "2026-01-05", "n": 1, "mean_polarity": 0.5},
              {"week_start": "2026-01-12", "n": 10, "mean_polarity": 0.0},
              {"week_start": "2026-01-26", "n": 1, "mean_polarity": -0.5}]
    # Weighted least squares for x=(0,1,3), y=(.5,0,-.5), weights=(1,10,1).
    assert weekly_momentum(points) == pytest.approx(-0.3050847458)
    assert weekly_momentum([{"week_start": "2025-01-06", "n": 1000, "mean_polarity": 1.0}, *points]) == weekly_momentum(points)
    assert weekly_momentum([]) is None
    assert weekly_momentum(points[:1]) is None


def test_momentum_accepts_iso_week_labels_and_orders_points():
    by_date = [{"week_start": "2026-01-05", "n": 2, "mean_polarity": 0.2},
               {"week_start": "2025-12-29", "n": 3, "mean_polarity": 0.6}]
    by_label = [{"iso_week": "2026-W02", "n": 2, "mean_polarity": 0.2},
                {"iso_week": "2026-W01", "n": 3, "mean_polarity": 0.6}]
    assert weekly_momentum(by_date) == weekly_momentum(by_label) == pytest.approx(-0.4)
    assert weekly_momentum([{"week_start": "2026-01-05", "n": 0, "mean_polarity": 0.0}, by_date[1]]) is None


def test_summary_recent_window_matches_momentum_window():
    from server.signals import _recent

    points = [{"week_start": "2025-10-06", "n": 50, "mean_polarity": 0.9, "negative_share": 0.0},
              {"week_start": "2026-01-05", "n": 1, "mean_polarity": -0.5, "negative_share": 1.0},
              {"week_start": "2026-01-12", "n": 3, "mean_polarity": 0.5, "negative_share": 0.0}]
    recent = _recent(points)
    assert recent["momentum_weeks"] == 2 and recent["window_start"] == "2026-01-05"
    assert recent["recent_n"] == 4 and recent["recent_low_n"]
    assert recent["recent_mean_polarity"] == pytest.approx(0.25) and recent["recent_negative_share"] == pytest.approx(0.25)
    assert _recent([])["recent_mean_polarity"] is None
