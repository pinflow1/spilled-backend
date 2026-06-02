"""
Embedding generator using sentence-transformers.
Runs locally — no API calls, completely free.
Model: all-MiniLM-L6-v2 (~80MB, fast, good quality)
"""
import numpy as np
from typing import Optional
from loguru import logger

# Lazy load to avoid slow startup
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info("Loading sentence-transformers model (first run may take 30s)...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Model loaded successfully")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts.
    Returns numpy array of shape (n_texts, 384).
    """
    if not texts:
        return np.array([])

    model = get_model()
    try:
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,  # cosine similarity ready
        )
        return embeddings
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return np.zeros((len(texts), 384))


def embed_post(post: dict) -> np.ndarray:
    """
    Embed a single post using title + selftext.
    Title is weighted more heavily by repetition.
    """
    title = post.get("title", "")
    body = post.get("selftext", "") or ""

    # Weight title 3x by repeating it
    combined = f"{title} {title} {title} {body[:300]}".strip()
    return embed_texts([combined])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalized vectors."""
    if a.shape != b.shape:
        return 0.0
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def batch_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """
    Compute full pairwise cosine similarity matrix.
    Fast via matrix multiplication since vectors are normalized.
    """
    if embeddings.size == 0:
        return np.array([])
    return np.dot(embeddings, embeddings.T)
