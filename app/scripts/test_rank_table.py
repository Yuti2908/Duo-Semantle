"""Test: compute full-vocabulary rank table for a target word, and time it."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

EMBEDDINGS_DIR = Path("data/embeddings")
TARGET_WORD = "coral"
TOP_N = 1000


def load_all_partitions() -> tuple[list[str], np.ndarray]:
    all_words = []
    all_vectors = []
    for path in sorted(EMBEDDINGS_DIR.glob("*.bin")):
        with path.open("rb") as f:
            archive = np.load(f, allow_pickle=False)
            words = archive["words"]
            vectors = archive["vectors"]
        all_words.extend(str(w) for w in words)
        all_vectors.append(vectors.astype(np.float32, copy=False))
    return all_words, np.vstack(all_vectors)


def main() -> None:
    print("Loading all embedding partitions...")
    t0 = time.perf_counter()
    words, matrix = load_all_partitions()
    t1 = time.perf_counter()
    print(f"Loaded {len(words)} words, matrix shape {matrix.shape}, in {t1 - t0:.2f}s")

    if TARGET_WORD not in words:
        print(f"'{TARGET_WORD}' not found in vocabulary!")
        return

    target_idx = words.index(TARGET_WORD)
    target_vec = matrix[target_idx]

    print(f"\nComputing similarity of '{TARGET_WORD}' against all {len(words)} words...")
    t2 = time.perf_counter()

    norms = np.linalg.norm(matrix, axis=1)
    target_norm = np.linalg.norm(target_vec)
    dots = matrix @ target_vec
    similarities = dots / (norms * target_norm)

    t3 = time.perf_counter()
    print(f"Computed all similarities in {t3 - t2:.2f}s")

    ranked_indices = np.argsort(-similarities)[:TOP_N]
    top_words = [(words[i], round(float(similarities[i]), 4)) for i in ranked_indices]

    t4 = time.perf_counter()
    print(f"Sorted and sliced top {TOP_N} in {t4 - t3:.2f}s")

    print(f"\nTotal time: {t4 - t0:.2f}s")
    print(f"\nTop 10 closest words to '{TARGET_WORD}':")
    for word, sim in top_words[:10]:
        print(f"  {word:20} {sim}")

    print(f"\nRank 990-1000 (edge of the table):")
    for word, sim in top_words[990:1000]:
        print(f"  {word:20} {sim}")


if __name__ == "__main__":
    main()
