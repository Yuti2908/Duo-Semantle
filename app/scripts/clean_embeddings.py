"""Rebuild embedding partitions, dropping any zero-norm (unusable) vectors."""

from pathlib import Path
import numpy as np

from src.embeddings import write_partition

SOURCE_DIR = Path("data/embeddings")
OUTPUT_DIR = Path("data/embeddings_clean")

total_before = 0
total_after = 0

for path in sorted(SOURCE_DIR.glob("*.bin")):
    with path.open("rb") as f:
        archive = np.load(f, allow_pickle=False)
        words = archive["words"]
        vectors = archive["vectors"]

    norms = np.linalg.norm(vectors, axis=1)
    keep_mask = norms > 0

    total_before += len(words)
    total_after += int(keep_mask.sum())

    if keep_mask.sum() == 0:
        continue

    entries = {str(w): vectors[i] for i, w in enumerate(words) if keep_mask[i]}
    write_partition(OUTPUT_DIR / path.name, entries)

print(f"Before: {total_before} words")
print(f"After:  {total_after} words")
print(f"Dropped: {total_before - total_after} zero-vector words")
