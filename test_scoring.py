"""
Tests for the narrative scoring engine.
"""
import pytest
from datetime import datetime, timezone, timedelta
from scoring.scorer import NarrativeScorer
from utils.config import config


@pytest.fixture
def scorer():
    return NarrativeScorer()


def _make_narrative(
    score=0,
    engagement=1000,
    spread=3,
    post_count=5,
    status="emerging",
    hours_old=2,
    hours_inactive=1,
):
    now = datetime.now(timezone.utc)
    first_seen = (now - timedelta(hours=hours_old)).isoformat()
    last_active = (now - timedelta(hours=hours_inactive)).isoformat()
    return {
        "id": "test-narrative-id",
        "narrative_score": score,
        "total_engagement": engagement,
        "subreddit_spread": spread,
        "post_count": post_count,
        "status": status,
        "first_seen": first_seen,
        "last_updated": last_active,
        "last_active": last_active,
    }


# ── COMPONENT SCORES ──────────────────────────────────────────────────────
def test_engagement_score_zero_for_low_engagement(scorer):
    score = scorer._score_engagement(0)
    assert score == 0.0


def test_engagement_score_high_for_viral(scorer):
    score = scorer._score_engagement(50000)
    assert score >= 90.0


def test_subreddit_spread_single(scorer):
    score = scorer._score_subreddit_spread(1)
    assert score == 0.0


def test_subreddit_spread_high(scorer):
    score = scorer._score_subreddit_spread(10)
    assert score >= 90.0


def test_freshness_new_story(scorer):
    score = scorer._score_freshness(
        (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    )
    assert score >= 80.0


def test_freshness_old_story(scorer):
    score = scorer._score_freshness(
        (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    )
    assert score < 30.0


def test_freshness_expired_story(scorer):
    score = scorer._score_freshness(
        (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    )
    assert score == 0.0


# ── COVERAGE GAP ──────────────────────────────────────────────────────────
def test_coverage_gap_high_for_early_stories(scorer):
    narrative = _make_narrative(engagement=800, spread=2)
    score = scorer._score_coverage_gap(narrative)
    assert score >= 70.0


def test_coverage_gap_low_for_mature_stories(scorer):
    narrative = _make_narrative(engagement=50000, spread=15)
    score = scorer._score_coverage_gap(narrative)
    assert score < 30.0


# ── STATUS DETERMINATION ──────────────────────────────────────────────────
def test_status_boiling_for_high_score(scorer):
    narrative = _make_narrative(hours_inactive=0)
    status = scorer.get_status(90.0, narrative)
    assert status == "active"


def test_status_emerging_for_medium_score(scorer):
    narrative = _make_narrative(hours_inactive=0)
    status = scorer.get_status(72.0, narrative)
    assert status == "emerging"


def test_status_cooling_for_low_score(scorer):
    narrative = _make_narrative(hours_inactive=0)
    status = scorer.get_status(40.0, narrative)
    assert status == "cooling"


def test_status_cooling_for_inactive(scorer):
    narrative = _make_narrative(hours_inactive=15)  # inactive > 12h threshold
    status = scorer.get_status(75.0, narrative)
    assert status == "cooling"


# ── FULL SCORE CALCULATION ────────────────────────────────────────────────
def test_calculate_score_returns_all_components(scorer):
    narrative = _make_narrative(engagement=2000, spread=4)
    result = scorer.calculate_score(narrative)

    assert "narrative_score" in result
    assert "opportunity_score" in result
    assert "components" in result
    assert "velocity" in result["components"]
    assert "growth" in result["components"]
    assert "engagement" in result["components"]
    assert "spread" in result["components"]
    assert "freshness" in result["components"]


def test_calculate_score_range(scorer):
    narrative = _make_narrative(engagement=2000, spread=4)
    result = scorer.calculate_score(narrative)
    assert 0 <= result["narrative_score"] <= 100
    assert 0 <= result["opportunity_score"] <= 100


def test_high_engagement_high_spread_scores_well(scorer):
    narrative = _make_narrative(
        engagement=10000,
        spread=8,
        hours_old=1,
        hours_inactive=0,
    )
    result = scorer.calculate_score(narrative)
    assert result["narrative_score"] >= 40.0  # should score reasonably well


def test_normalize_clamps_at_boundaries(scorer):
    assert scorer._normalize(-10, 0, 100) == 0.0
    assert scorer._normalize(200, 0, 100) == 1.0
    assert scorer._normalize(50, 0, 100) == 0.5
