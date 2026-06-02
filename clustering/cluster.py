"""
Narrative clustering — groups related posts into stories.

Strategy: Greedy clustering with semantic + title similarity.
A post joins an existing cluster if similarity > threshold.
Otherwise it seeds a new cluster.

This is intentionally simple and fast. No sklearn required for
basic operation, though we use it for the similarity matrix.
"""
import re
from typing import Optional
import numpy as np
from loguru import logger
from clustering.embeddings import embed_texts, batch_similarity_matrix, cosine_similarity


# Similarity thresholds
SEMANTIC_THRESHOLD = 0.52      # cosine similarity for joining a cluster
TITLE_BOOST = 0.08             # boost if titles share keywords
MIN_CLUSTER_SIZE = 2           # minimum posts to form a narrative
SUBREDDIT_DIVERSITY_BONUS = 0.04  # per unique subreddit beyond first


def _extract_keywords(text: str, top_n: int = 8) -> set[str]:
    """Extract meaningful keywords from text."""
    # Remove common stop words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "this", "that",
        "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "what", "which", "who", "how", "when", "where", "why",
    }
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    keywords = [w for w in words if w not in stop_words]
    # Return most frequent
    from collections import Counter
    return set(w for w, _ in Counter(keywords).most_common(top_n))


def _title_similarity(title_a: str, title_b: str) -> float:
    """Jaccard similarity between keyword sets of two titles."""
    kw_a = _extract_keywords(title_a)
    kw_b = _extract_keywords(title_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union)


def _compute_cluster_similarity(
    post_embedding: np.ndarray,
    post_title: str,
    cluster: dict,
) -> float:
    """
    Compute similarity between a post and an existing cluster.
    Uses centroid embedding + title keyword overlap.
    """
    centroid = cluster["centroid"]
    sem_sim = cosine_similarity(post_embedding, centroid)

    # Title keyword boost
    cluster_titles = " ".join(p["title"] for p in cluster["posts"][:3])
    title_sim = _title_similarity(post_title, cluster_titles)
    boost = title_sim * TITLE_BOOST

    # Subreddit diversity bonus — reward cross-community spread
    subreddits = cluster["subreddits"]
    if len(subreddits) > 1:
        boost += (len(subreddits) - 1) * SUBREDDIT_DIVERSITY_BONUS

    return sem_sim + boost


def _update_centroid(cluster: dict, new_embedding: np.ndarray):
    """Update cluster centroid with running average."""
    n = len(cluster["posts"])
    old_centroid = cluster["centroid"]
    # Running mean
    new_centroid = (old_centroid * (n - 1) + new_embedding) / n
    # Re-normalize
    norm = np.linalg.norm(new_centroid)
    if norm > 0:
        new_centroid = new_centroid / norm
    cluster["centroid"] = new_centroid


def cluster_posts(posts: list[dict]) -> list[dict]:
    """
    Greedy clustering of posts into narrative clusters.

    Args:
        posts: list of post dicts with title, selftext, subreddit fields

    Returns:
        list of cluster dicts:
        {
            posts: [...],
            subreddits: set,
            centroid: np.ndarray,
            total_engagement: int,
            representative_title: str,
        }
    """
    if not posts:
        return []

    logger.info(f"Clustering {len(posts)} posts...")

    # Generate embeddings for all posts at once (batch is faster)
    texts = [
        f"{p.get('title', '')} {p.get('title', '')} {p.get('title', '')} {(p.get('selftext', '') or '')[:200]}"
        for p in posts
    ]
    embeddings = embed_texts(texts)

    if embeddings.size == 0:
        logger.error("Failed to generate embeddings")
        return []

    clusters = []

    for i, post in enumerate(posts):
        post_embedding = embeddings[i]
        post_title = post.get("title", "")
        best_cluster = None
        best_score = SEMANTIC_THRESHOLD  # minimum to join

        # Find best matching cluster
        for cluster in clusters:
            score = _compute_cluster_similarity(post_embedding, post_title, cluster)
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is not None:
            # Join existing cluster
            best_cluster["posts"].append(post)
            best_cluster["subreddits"].add(post.get("subreddit", ""))
            best_cluster["total_engagement"] += post.get("engagement", 0)
            _update_centroid(best_cluster, post_embedding)
        else:
            # Seed new cluster
            clusters.append({
                "posts": [post],
                "subreddits": {post.get("subreddit", "")},
                "centroid": post_embedding.copy(),
                "total_engagement": post.get("engagement", 0),
                "representative_title": post_title,
            })

    # Filter to minimum cluster size
    valid_clusters = [c for c in clusters if len(c["posts"]) >= MIN_CLUSTER_SIZE]
    singleton_count = len(clusters) - len(valid_clusters)

    logger.info(
        f"Clustering complete: {len(valid_clusters)} narratives, "
        f"{singleton_count} singletons discarded"
    )

    # Sort by total engagement descending
    valid_clusters.sort(key=lambda c: c["total_engagement"], reverse=True)

    # Pick best representative title (highest engagement post)
    for cluster in valid_clusters:
        cluster["posts"].sort(key=lambda p: p.get("engagement", 0), reverse=True)
        cluster["representative_title"] = cluster["posts"][0]["title"]
        cluster["subreddits"] = list(cluster["subreddits"])

    return valid_clusters
