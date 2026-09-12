"""Reproducible local comparison of FastText and spaCy static word vectors."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Protocol

import numpy as np

from src.similarity import cosine_similarity


SEMANTIC_PAIRS = (
    ("king", "queen"),
    ("dog", "cat"),
    ("doctor", "hospital"),
    ("car", "automobile"),
    ("dog", "refrigerator"),
)
RARE_WORDS = ("floccinaucinihilipilification", "sesquipedalian", "perspicacious")
OOV_PROBE = "unfloccinaucinihilipilification"


class VectorModel(Protocol):
    name: str

    def vector_for(self, word: str) -> np.ndarray | None: ...


class FastTextModel:
    name = "fasttext"

    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(
                f"FastText model not found: {model_path}. Expected a downloaded, uncompressed .bin model."
            )
        import fasttext

        try:
            self._model = fasttext.load_model(str(model_path))
        except (OSError, ValueError) as error:
            raise RuntimeError(
                f"Unable to read {model_path} as a FastText .bin model. "
                "A .vec, .zip, .gz, or partial download will not work."
            ) from error

    def vector_for(self, word: str) -> np.ndarray:
        # FastText produces a subword vector even when the string was absent
        # from its vocabulary. The validator remains responsible for legitimacy.
        return np.asarray(self._model.get_word_vector(word), dtype=np.float64)


class SpacyStaticModel:
    """Compact static-vector baseline; unknown strings have no vector."""

    def __init__(self, package: str) -> None:
        import spacy

        self.name = f"spacy:{package}"
        self._vocab = spacy.load(package, disable=["tagger", "parser", "ner", "lemmatizer"]).vocab

    def vector_for(self, word: str) -> np.ndarray | None:
        lexeme = self._vocab[word]
        if not lexeme.has_vector or lexeme.vector_norm == 0:
            return None
        return np.asarray(lexeme.vector, dtype=np.float64)


def median_microseconds(operation, iterations: int) -> float:
    samples = []
    for _ in range(iterations):
        start = perf_counter_ns()
        operation()
        samples.append((perf_counter_ns() - start) / 1_000)
    return round(float(np.median(samples)), 3)


def evaluate(model: VectorModel, iterations: int) -> dict:
    vectors = {word: model.vector_for(word) for pair in SEMANTIC_PAIRS for word in pair}
    semantic_scores = {
        f"{left}~{right}": round(cosine_similarity(vectors[left], vectors[right]), 6)
        for left, right in SEMANTIC_PAIRS
        if vectors[left] is not None and vectors[right] is not None
    }
    known = next(vector for vector in vectors.values() if vector is not None)
    return {
        "semantic_similarity": semantic_scores,
        "rare_word_has_vector": {word: model.vector_for(word) is not None for word in RARE_WORDS},
        "oov_probe_has_vector": model.vector_for(OOV_PROBE) is not None,
        "latency_median_us": {
            "vector_lookup_or_generation": median_microseconds(lambda: model.vector_for("perspicacious"), iterations),
            "cosine_similarity": median_microseconds(lambda: cosine_similarity(known, known), iterations),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasttext-bin", type=Path, required=True, help="Subword FastText .bin model")
    parser.add_argument("--spacy-model", default="en_core_web_md")
    parser.add_argument("--iterations", type=int, default=2_000)
    args = parser.parse_args()

    try:
        models: list[VectorModel] = [FastTextModel(args.fasttext_bin), SpacyStaticModel(args.spacy_model)]
    except (FileNotFoundError, RuntimeError, ModuleNotFoundError) as error:
        parser.error(str(error))
    report = {model.name: evaluate(model, args.iterations) for model in models}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
