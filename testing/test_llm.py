"""
Tests for LLM generator and thread builder.
Uses mocks to avoid real API calls.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ── LLM GENERATOR ─────────────────────────────────────────────────────────
def _make_narrative(score=75, hours_old=2):
    now = datetime.now(timezone.utc)
    return {
        "id": "test-narrative-123",
        "headline": "Test headline",
        "summary": None,
        "narrative_score": score,
        "total_engagement": 2000,
        "subreddit_spread": 4,
        "post_count": 8,
        "participating_subs": ["technology", "artificial", "programming"],
        "first_seen": (now - timedelta(hours=hours_old)).isoformat(),
        "ai_generated_at": None,
        "creator_angles": None,
        "hooks": None,
        "viral_explanation": None,
    }


def _make_posts(n=5):
    return [
        {
            "reddit_id": f"post_{i}",
            "title": f"Test post title {i} about the story",
            "selftext": f"Body text for post {i}",
            "subreddit": "technology",
            "score": 200 - i * 10,
            "num_comments": 50,
            "engagement": 300 - i * 10,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(n)
    ]


def test_daily_limit_enforced():
    from llm.generator import _check_daily_limit, _increment_daily_calls, _daily_calls, MAX_DAILY_CALLS
    # Reset counter
    _daily_calls["count"] = 0
    _daily_calls["date"] = datetime.now(timezone.utc).date().isoformat()

    # Fill up to limit
    for _ in range(MAX_DAILY_CALLS):
        assert _check_daily_limit() is True
        _increment_daily_calls()

    # Should now be at limit
    assert _check_daily_limit() is False

    # Reset for other tests
    _daily_calls["count"] = 0


def test_local_fallback_returns_valid_structure():
    from llm.generator import _local_fallback
    narrative = _make_narrative()
    posts = _make_posts()
    result = _local_fallback(narrative, posts)

    assert "headline" in result
    assert "summary" in result
    assert "status_label" in result
    assert "creator_angles" in result
    assert "hooks" in result
    assert result["status_label"] in ["EARLY SIGNAL", "SPICY", "BOILING"]
    assert "youtube" in result["creator_angles"]
    assert "tiktok" in result["creator_angles"]


def test_local_fallback_status_label_for_high_score():
    from llm.generator import _local_fallback
    narrative = _make_narrative(score=90)
    result = _local_fallback(narrative, _make_posts())
    assert result["status_label"] == "BOILING"


def test_local_fallback_status_label_for_medium_score():
    from llm.generator import _local_fallback
    narrative = _make_narrative(score=72)
    result = _local_fallback(narrative, _make_posts())
    assert result["status_label"] == "SPICY"


def test_local_fallback_status_label_for_low_score():
    from llm.generator import _local_fallback
    narrative = _make_narrative(score=50)
    result = _local_fallback(narrative, _make_posts())
    assert result["status_label"] == "EARLY SIGNAL"


def test_generate_uses_cache_when_fresh():
    from llm.generator import generate_narrative_content
    now = datetime.now(timezone.utc).isoformat()
    narrative = _make_narrative()
    narrative["ai_generated_at"] = now  # just generated
    narrative["summary"] = "Cached summary"
    narrative["creator_angles"] = {"youtube": "test angle"}
    narrative["hooks"] = {"curiosity": "test hook"}

    with patch("llm.generator.get_db") as mock_db:
        result = generate_narrative_content(narrative, _make_posts())
        # Should return cached content without calling DB update
        assert result is not None
        assert result["summary"] == "Cached summary"


def test_generate_falls_back_to_local_when_no_keys():
    from llm.generator import generate_narrative_content
    narrative = _make_narrative()

    with patch("llm.generator.config") as mock_config:
        mock_config.GROQ_API_KEY = None
        mock_config.GEMINI_API_KEY = None
        with patch("llm.generator.get_db") as mock_db:
            mock_db.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            with patch("llm.generator._daily_calls", {"count": 0, "date": datetime.now(timezone.utc).date().isoformat()}):
                result = generate_narrative_content(narrative, _make_posts())
                assert result is not None
                assert "headline" in result


# ── THREAD BUILDER ────────────────────────────────────────────────────────
def test_build_thread_creates_posts():
    from llm.thread_builder import build_thread

    posts = _make_posts(6)
    ai_content = {
        "why_spreading": ["Key insight about the story"],
    }

    with patch("llm.thread_builder.get_db") as mock_db:
        mock_table = MagicMock()
        mock_db.return_value.table.return_value = mock_table
        # Simulate no existing thread
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_table.insert.return_value.execute.return_value = MagicMock()

        result = build_thread("test-narrative-id", posts, ai_content)
        assert result is True
        # Verify insert was called
        mock_table.insert.assert_called_once()


def test_build_thread_skips_if_exists():
    from llm.thread_builder import build_thread

    with patch("llm.thread_builder.get_db") as mock_db:
        mock_table = MagicMock()
        mock_db.return_value.table.return_value = mock_table
        # Simulate existing thread
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "existing"}]
        # Mock the update chain for _update_developing_flag
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [{"id": "last-post"}]
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = build_thread("test-narrative-id", _make_posts(), {})
        assert result is True
        # Should not call insert
        mock_table.insert.assert_not_called()


def test_build_thread_returns_false_for_empty_posts():
    from llm.thread_builder import build_thread

    with patch("llm.thread_builder.get_db") as mock_db:
        mock_table = MagicMock()
        mock_db.return_value.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        result = build_thread("test-narrative-id", [], {})
        assert result is False


def test_format_time_ago():
    from llm.thread_builder import _format_time_ago

    # Recent
    recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    assert "30m" in _format_time_ago(recent) or "m ago" in _format_time_ago(recent)

    # Hours ago
    hours = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert "3h" in _format_time_ago(hours)

    # Invalid
    assert _format_time_ago("") == "recently"
    assert _format_time_ago(None) == "recently"
