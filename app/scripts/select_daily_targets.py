"""Select two dissimilar daily targets, avoiding repeats from the last N days."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from src.embeddings import PrefixEmbeddingStore
from src.similarity import cosine_similarity

POOL_PATH = Path("data/dictionary/target_pool.txt")
HISTORY_PATH = Path("data/dictionary/target_history.json")
EMBEDDINGS_DIR = Path("data/embeddings")

REPEAT_WINDOW_DAYS = 30
DISSIMILARITY_THRESHOLD = 0.15
CANDIDATE_SAMPLE_SIZE = 200


def load_pool() -> list[str]:
    return [line.strip() for line in POOL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def save_history(history: list[dict]) -> None:
    HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")


def recently_used_words(history: list[dict], as_of: date) -> set[str]:
    cutoff = as_of - timedelta(days=REPEAT_WINDOW_DAYS)
    used = set()
    for entry in history:
        entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        if entry_date >= cutoff:
            used.add(entry["target_a"])
            used.add(entry["target_b"])
    return used


def select_targets(pool: list[str], embeddings: PrefixEmbeddingStore, excluded: set[str]) -> tuple[str, str]:
    eligible = [w for w in pool if w not in excluded]
    if len(eligible) < 2:
        raise RuntimeError("Not enough eligible words left in the pool.")

    random.shuffle(eligible)

    target_a = None
    vec_a = None
    for word in eligible:
        vec = embeddings.vector_for(word)
        if vec is not None:
            target_a = word
            vec_a = vec
            break
    if target_a is None:
        raise RuntimeError("No eligible word in the pool has an embedding.")

    candidates = [w for w in eligible if w != target_a]
    random.shuffle(candidates)
    candidates = candidates[:CANDIDATE_SAMPLE_SIZE]

    scored = []
    for word in candidates:
        vec_b = embeddings.vector_for(word)
        if vec_b is None:
            continue
        sim = cosine_similarity(vec_a, vec_b)
        scored.append((word, sim))

    below_threshold = [w for w, sim in scored if sim < DISSIMILARITY_THRESHOLD]
    if below_threshold:
        target_b = random.choice(below_threshold)
    else:
        scored.sort(key=lambda pair: pair[1])
        target_b = scored[0][0]
        print(f"Warning: no candidate below threshold {DISSIMILARITY_THRESHOLD}; using lowest available.")

    return target_a, target_b


def main() -> None:
    pool = load_pool()
    embeddings = PrefixEmbeddingStore(EMBEDDINGS_DIR)
    history = load_history()

    today = date.today()
    excluded = recently_used_words(history, today)
    print(f"Excluding {len(excluded)} recently used words (last {REPEAT_WINDOW_DAYS} days)")

    target_a, target_b = select_targets(pool, embeddings, excluded)

    vec_a = embeddings.vector_for(target_a)
    vec_b = embeddings.vector_for(target_b)
    similarity = cosine_similarity(vec_a, vec_b)

    print(f"\nToday's targets: '{target_a}' and '{target_b}'")
    print(f"Similarity between them: {similarity:.4f}")

    history.append({
        "date": today.isoformat(),
        "target_a": target_a,
        "target_b": target_b,
        "similarity": round(similarity, 4),
    })
    save_history(history)
    print(f"Saved to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
