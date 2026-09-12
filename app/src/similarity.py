"""Deterministic semantic-similarity scoring."""

from __future__ import annotations

import numpy as np


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Return stable cosine similarity, rejecting zero vectors."""
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0:
        raise ValueError("Cannot calculate similarity for a zero vector.")
    return float(np.dot(left, right) / denominator)


def semantle_score(similarity: float) -> float:
    """Scale cosine similarity to a percentage-style display value.

    Deliberately not remapped to 0-1000: embedding spaces exhibit a hubness
    bias where most unrelated word pairs still sit meaningfully above 0
    cosine similarity, so a linear [-1, 1] -> [0, 1000] stretch makes
    everything feel artificially "medium." Showing the honest, scaled cosine
    value instead preserves that most guesses are genuinely cold.
    """
    bounded = min(1.0, max(-1.0, similarity))
    return round(bounded * 100, 2)