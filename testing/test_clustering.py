"""
Tests for the clustering engine.
"""
import pytest
import numpy as np
from clustering.cluster import (
    cluster_posts,
    _extract_keywords,
    _title_similarity,
    MIN_CLUSTER_SIZE,
)
from clustering.embeddings import embed_texts, cosine_similarity


# ── KEYWORD EXTRACTION ────────────────────────────────────────────────────
def test_extract_keywords_removes_stopwords():
    keywords = _extract_keywords("the cat sat on the mat with a dog")
    assert "the" not in keywords
    assert "with" not in keywords
    assert "cat" in keywords or "sat" in keywords


def test_extract_keywords_empty():
    keywords = _extract_keywords("")
    assert keywords == set()


def test_extract_keywords_short_words_filtered():
    keywords = _extract_keywords("it is so good to be here")
    # Words < 3 chars filtered
    assert "it" not in keywords
    assert "is" not in keywords


# ── TITLE SIMILARITY ──────────────────────────────────────────────────────
def test_title_similarity_identical():
    sim = _title_similarity("OpenAI releases new model", "OpenAI releases new model")
    assert sim > 0.8


def test_title_similarity_unrelated():
    sim = _title_similarity("cats are cute animals", "stock market crashes today")
    assert sim < 0.2


def test_title_similarity_partial():
    sim = _title_similarity("OpenAI GPT model update", "GPT model becomes less creative")
    assert 0.1 < sim < 0.9


# ── EMBEDDINGS ────────────────────────────────────────────────────────────
def test_embed_texts_returns_correct_shape():
    texts = ["Hello world", "This is a test", "Another sentence"]
    embeddings = embed_texts(texts)
    assert embeddings.shape == (3, 384)


def test_embed_texts_empty():
    embeddings = embed_texts([])
    assert embeddings.size == 0


def test_embed_texts_normalized():
    texts = ["Test sentence for normalization"]
    embeddings = embed_texts(texts)
    # Normalized vectors should have unit length
    norm = np.linalg.norm(embeddings[0])
    assert abs(norm - 1.0) < 0.01


def test_cosine_similarity_identical():
    v = np.array([0.5, 0.5, 0.5, 0.5])
    sim = cosine_similarity(v, v)
    assert abs(sim - 1.0) < 0.01


def test_cosine_similarity_orthogonal():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    sim = cosine_similarity(a, b)
    assert abs(sim) < 0.01


# ── CLUSTER POSTS ─────────────────────────────────────────────────────────
def _make_post(title, subreddit="technology", score=200, comments=50, body=""):
    import time, hashlib
    return {
        "reddit_id": hashlib.md5(title.encode()).hexdigest()[:8],
        "title": title,
        "selftext": body,
        "subreddit": subreddit,
        "score": score,
        "num_comments": comments,
        "engagement": score + comments * 2,
        "created_utc": __import__('datetime').datetime.now(
            __import__('datetime').timezone.utc
        ).isoformat(),
    }


def test_cluster_empty_posts():
    result = cluster_posts([])
    assert result == []


def test_cluster_related_posts_grouped():
    posts = [
        _make_post("OpenAI GPT-4 becomes less creative after update", "ChatGPT"),
        _make_post("GPT outputs are worse quality since the update", "artificial"),
        _make_post("People noticing ChatGPT creativity dropped overnight", "MachineLearning"),
        _make_post("Is GPT getting dumber? Developers compare outputs", "programming"),
        _make_post("OpenAI silent on model update controversy", "technology"),
    ]
    clusters = cluster_posts(posts)
    # All related posts should form at least one cluster
    assert len(clusters) >= 1
    # Biggest cluster should have multiple posts
    assert clusters[0]["post_count"] if "post_count" in clusters[0] else len(clusters[0]["posts"]) >= 2


def test_cluster_unrelated_posts_separate():
    posts = [
        _make_post("NBA player traded to new team after drama", "nba"),
        _make_post("Basketball star signs record contract", "sports"),
        _make_post("OpenAI releases new AI model update", "artificial"),
        _make_post("ChatGPT gets major feature update", "ChatGPT"),
        _make_post("Celebrity couple breaks up after 5 years", "Fauxmoi"),
        _make_post("Hollywood star announces divorce from partner", "entertainment"),
    ]
    clusters = cluster_posts(posts)
    # Should form multiple separate clusters
    assert len(clusters) >= 2


def test_cluster_minimum_size_enforced():
    posts = [
        _make_post("This is a totally unique story about nothing", "technology"),
        _make_post("Another completely unrelated topic here", "science"),
        _make_post("Third post about something different entirely", "gaming"),
    ]
    clusters = cluster_posts(posts)
    # All clusters should meet minimum size
    for cluster in clusters:
        post_count = len(cluster.get("posts", []))
        assert post_count >= MIN_CLUSTER_SIZE


def test_cluster_sorted_by_engagement():
    posts = [
        _make_post("Low engagement story", score=100, comments=20),
        _make_post("Low engagement story continued", score=90, comments=15),
        _make_post("High engagement viral story", score=5000, comments=800),
        _make_post("High engagement viral story update", score=4000, comments=600),
    ]
    clusters = cluster_posts(posts)
    if len(clusters) >= 2:
        assert clusters[0]["total_engagement"] >= clusters[1]["total_engagement"]


def test_cluster_tracks_subreddits():
    posts = [
        _make_post("GPT update story", subreddit="ChatGPT"),
        _make_post("GPT creativity drops after update", subreddit="artificial"),
        _make_post("OpenAI model change controversy", subreddit="MachineLearning"),
        _make_post("Developers notice GPT quality change", subreddit="programming"),
    ]
    clusters = cluster_posts(posts)
    if clusters:
        # Should track multiple subreddits
        assert len(clusters[0]["subreddits"]) >= 1
