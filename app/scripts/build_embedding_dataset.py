"""Build small local prefix partitions from an installed FastText model."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from src.embeddings import partition_name, write_partition


def words_from(path: Path) -> list[str]:
    return [line.strip().casefold() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create two-letter local embedding partitions.")
    parser.add_argument("--fasttext-bin", type=Path, required=True)
    parser.add_argument("--words", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/embeddings"))
    args = parser.parse_args()

    if not args.fasttext_bin.is_file():
        parser.error(f"FastText model not found: {args.fasttext_bin}")
    if not args.words.is_file():
        parser.error(f"Word list not found: {args.words}")
    import fasttext

    model = fasttext.load_model(str(args.fasttext_bin))
    partitions: dict[str, dict[str, np.ndarray]] = {}
    in_vocab_count = 0
    for word in words_from(args.words):
        if model.get_word_id(word) >= 0:
            in_vocab_count += 1
        partitions.setdefault(partition_name(word), {})[word] = model.get_word_vector(word)

    total = 0
    for prefix, entries in sorted(partitions.items()):
        write_partition(args.output / f"{prefix}.bin", entries)
        total += len(entries)
        print(f"Wrote {prefix}.bin ({len(entries)} vectors)")

    print(f"\nTotal vectors written: {total}")
    print(f"In fastText's explicit vocab: {in_vocab_count} ({100*in_vocab_count/total:.1f}%)")
    print(f"Subword-synthesized (not in explicit vocab): {total - in_vocab_count} ({100*(total-in_vocab_count)/total:.1f}%)")

if __name__ == "__main__":
    main()