"""
Tests for the Reddit collector.
Run with: python -m pytest tests/ -v
"""
import pytest
from unittest.mock import patch, MagicMock
from collector.reddit import RedditCollector


@pytest.fixture
def collector():
    return RedditCollector()


def test_valid_post_passes_filter(collector):
    import time
    post = {
        "score": 100,
        "num_comments": 50,
        "created_utc": time.time() - 3600,  # 1 hour ago
        "over_18": False,
        "subreddit": "technology",
        "title": "Major tech company announces layoffs",
        "is_video": False,
    }
    assert collector._is_valid_post(post) is True


def test_low_engagement_post_filtered(collector):
    import time
    post = {
        "score": 10,
        "num_comments": 5,
        "created_utc": time.time() - 3600,
        "over_18": False,
        "subreddit": "technology",
        "title": "Some post",
    }
    assert collector._is_valid_post(post) is False


def test_nsfw_post_filtered(collector):
    import time
    post = {
        "score": 500,
        "num_comments": 100,
        "created_utc": time.time() - 3600,
        "over_18": True,
        "subreddit": "technology",
        "title": "Some post",
    }
    assert collector._is_valid_post(post) is False


def test_old_post_filtered(collector):
    import time
    post = {
        "score": 500,
        "num_comments": 100,
        "created_utc": time.time() - (10 * 3600),  # 10 hours ago
        "over_18": False,
        "subreddit": "technology",
        "title": "Some post",
    }
    assert collector._is_valid_post(post) is False


def test_blacklisted_subreddit_filtered(collector):
    import time
    post = {
        "score": 500,
        "num_comments": 100,
        "created_utc": time.time() - 3600,
        "over_18": False,
        "subreddit": "memes",
        "title": "Some post",
    }
    assert collector._is_valid_post(post) is False


def test_blacklisted_keyword_filtered(collector):
    import time
    post = {
        "score": 500,
        "num_comments": 100,
        "created_utc": time.time() - 3600,
        "over_18": False,
        "subreddit": "technology",
        "title": "Daily Thread: What are you working on?",
    }
    assert collector._is_valid_post(post) is False


def test_normalize_post(collector):
    import time
    post = {
        "id": "abc123",
        "title": "Test post title",
        "selftext": "Test body",
        "author": "testuser",
        "subreddit": "technology",
        "score": 200,
        "num_comments": 50,
        "upvote_ratio": 0.95,
        "created_utc": time.time() - 3600,
        "permalink": "/r/technology/comments/abc123/test/",
        "url": "https://example.com",
        "is_self": True,
        "link_flair_text": "News",
        "is_video": False,
        "over_18": False,
    }
    normalized = collector._normalize_post(post)
    assert normalized["id"] == "abc123"
    assert normalized["engagement"] == 200 + (50 * 2)  # score + comments*2
    assert "content_hash" in normalized
    assert len(normalized["content_hash"]) == 32  # md5 hex


def test_collect_all_deduplicates(collector):
    """Ensure collect_all deduplicates by post ID."""
    mock_post = {
        "id": "duplicate_id",
        "title": "Same post",
        "selftext": "",
        "author": "user",
        "subreddit": "technology",
        "score": 200,
        "num_comments": 50,
        "upvote_ratio": 0.9,
        "created_utc": __import__('time').time() - 1800,
        "permalink": "/r/technology/test/",
        "url": "https://example.com",
        "is_self": True,
        "link_flair_text": "",
        "is_video": False,
        "over_18": False,
    }

    with patch.object(collector, 'fetch_subreddit', return_value=[collector._normalize_post(mock_post)]):
        with patch.object(collector, 'fetch_global', return_value=[collector._normalize_post(mock_post)]):
            posts = collector.collect_all()
            ids = [p["id"] for p in posts]
            assert len(ids) == len(set(ids))  # no duplicates
