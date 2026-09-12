"""Embedding stores and a FastText fallback provider."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    def vector_for(self, word: str) -> np.ndarray | None: ...


class NpzEmbeddingStore:
    """Read-only local vectors saved as a deterministic NumPy ``.npz`` file.

    The file contains ``words`` (a string array) and ``vectors`` (a 2-D float
    array with matching row order). It is easy to build locally today and move
    to S3/EFS or a vector service later without changing callers.
    """

    def __init__(self, path: str | Path) -> None:
        archive = np.load(Path(path), allow_pickle=False)
        words = archive["words"]
        vectors = archive["vectors"]
        if vectors.ndim != 2 or len(words) != len(vectors):
            raise ValueError("Embedding archive must contain aligned words and 2-D vectors.")
        self._vectors = {str(word): vectors[i].astype(np.float64, copy=False) for i, word in enumerate(words)}

    def vector_for(self, word: str) -> np.ndarray | None:
        return self._vectors.get(word)

    def get(self, word: str) -> np.ndarray | None:
        return self.vector_for(word)


def partition_name(word: str) -> str:
    """Return a stable two-letter file partition for a normalized word."""
    letters = "".join(character for character in word.casefold() if "a" <= character <= "z")
    return letters[:2] if len(letters) >= 2 else "__"


class PrefixEmbeddingStore:
    """Lazy lookup from local two-letter partition files such as ``el.bin``."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._partitions: dict[str, dict[str, np.ndarray]] = {}

    def _load_partition(self, name: str) -> dict[str, np.ndarray]:
        if name in self._partitions:
            return self._partitions[name]
        path = self.directory / f"{name}.bin"
        if not path.is_file():
            self._partitions[name] = {}
            return self._partitions[name]
        with path.open("rb") as stream:
            archive = np.load(stream, allow_pickle=False)
            words, vectors = archive["words"], archive["vectors"]
        if vectors.ndim != 2 or len(words) != len(vectors):
            raise ValueError(f"Invalid embedding partition: {path}")
        self._partitions[name] = {
            str(word): vectors[index].astype(np.float64, copy=False)
            for index, word in enumerate(words)
        }
        return self._partitions[name]

    def vector_for(self, word: str) -> np.ndarray | None:
        return self._load_partition(partition_name(word)).get(word)

    def get(self, word: str) -> np.ndarray | None:
        return self.vector_for(word)


def write_partition(path: str | Path, entries: dict[str, np.ndarray]) -> None:
    """Write a deterministic, compressed NumPy archive using a ``.bin`` name."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    words = sorted(entries)
    vectors = np.stack([np.asarray(entries[word], dtype=np.float32) for word in words])
    with destination.open("wb") as stream:
        np.savez_compressed(stream, words=np.asarray(words), vectors=vectors)


class FastTextFallback:
    """Generates a vector for a valid word absent from the common-vector store."""

    def __init__(self, model_path: str | Path) -> None:
        try:
            import fasttext
        except ImportError as error:  # pragma: no cover - environment dependent
            raise RuntimeError("Install fasttext-wheel to use FastTextFallback.") from error
        self._model = fasttext.load_model(str(model_path))

    def vector_for(self, word: str) -> np.ndarray:
        # FastText subword vectors work for out-of-vocabulary spellings too;
        # validation happens before this method is called.
        return np.asarray(self._model.get_word_vector(word), dtype=np.float64)


class FallbackEmbeddingProvider:
    """Looks up common vectors first and generates only missing vectors."""

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def vector_for(self, word: str) -> np.ndarray | None:
        vector = self.primary.vector_for(word)
        return vector if vector is not None else self.fallback.vector_for(word)
