"""Game service: validate a guess then score it against a daily target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from .embeddings import EmbeddingProvider
from .similarity import cosine_similarity, semantle_score
from .validator import WordValidator


@dataclass(frozen=True)
class GuessResult:
    word: str
    valid: bool
    score: float | None = None
    similarity: float | None = None
    reason: str | None = None


class DailyTargetRepository:
    """In-memory target seam; replace with an AWS-backed repository later."""

    def __init__(self, targets: Mapping[date, str]) -> None:
        self._targets = {day: word.casefold() for day, word in targets.items()}

    def target_for(self, day: date) -> str:
        try:
            return self._targets[day]
        except KeyError as error:
            raise LookupError(f"No target configured for {day.isoformat()}.") from error


class DuoSemantleGame:
    def __init__(
        self,
        validator: WordValidator,
        embeddings: EmbeddingProvider,
        targets: DailyTargetRepository,
    ) -> None:
        self.validator = validator
        self.embeddings = embeddings
        self.targets = targets
        self._active_target: str | None = None

    def start(self, target: str) -> None:
        """Start a local session with an explicit target (useful before scheduling)."""
        normalized = self.validator.normalize(target)
        if not self.validator.is_valid_english(normalized):
            raise ValueError(f"Target is not an accepted English word: {target!r}")
        self._active_target = normalized

    def guess(self, raw_guess: str, day: date | None = None) -> GuessResult:
        word = self.validator.normalize(raw_guess)
        if not self.validator.is_valid(word):
            return GuessResult(word=word, valid=False, reason="invalid English word")

        if self._active_target is not None:
            target = self._active_target
        elif day is not None:
            target = self.targets.target_for(day)
        else:
            raise ValueError("Pass a day or call start(target=...) before guessing.")
        guess_vector = self.embeddings.vector_for(word)
        target_vector = self.embeddings.vector_for(target)
        if guess_vector is None or target_vector is None:
            return GuessResult(word=word, valid=False, reason="embedding unavailable")

        similarity = cosine_similarity(guess_vector, target_vector)
        return GuessResult(
            word=word,
            valid=True,
            score=semantle_score(similarity),
            similarity=similarity,
        )
