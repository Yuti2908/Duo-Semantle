import numpy as np


def cosine_similarity(a, b):
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return None
    return float(np.dot(a, b) / denom)


def semantle_score(similarity):
    bounded = min(1.0, max(-1.0, similarity))
    return round(bounded * 100, 2)
