"""Policy-driven English-word validation, independent from embeddings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol
import re


_WORD_FORM = re.compile(r"^(?:[a-z]+|'[a-z]+)(?:['-]+[a-z]+)*'?$")


@dataclass(frozen=True)
class LexiconEntry:
    """A word and source-supplied labels."""

    word: str
    labels: frozenset[str] = field(default_factory=frozenset)


class EnglishLexicon(Protocol):
    def entry_for(self, normalized_word: str) -> LexiconEntry | None: ...


class FileLexicon:
    """Loads a replaceable UTF-8 tab-separated lexicon.

    Lines are ``word`` or ``word<TAB>comma,separated,labels``. A source-import
    job can replace this file without affecting the validator or game service.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries = self._load_entries()

    def _load_entries(self) -> dict[str, LexiconEntry]:
        if not self.path.is_file():
            raise FileNotFoundError(f"Lexicon not found: {self.path}")
        entries: dict[str, LexiconEntry] = {}
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t", maxsplit=1)
            word = normalize_word(fields[0])
            labels = (
                frozenset(label.strip() for label in fields[1].split(",") if label.strip())
                if len(fields) == 2
                else frozenset()
            )
            if not _WORD_FORM.fullmatch(word):
                raise ValueError(f"Invalid lexicon form {fields[0]!r} in {self.path}")
            entries[word] = LexiconEntry(word, labels)
        return entries

    def entry_for(self, normalized_word: str) -> LexiconEntry | None:
        return self._entries.get(normalized_word)


@dataclass(frozen=True)
class ValidationPolicy:
    """Duo-Semantle's deliberately explicit inclusion rules."""

    allow_proper_nouns: bool = False
    allow_abbreviations: bool = False
    allow_offensive_terms: bool = False
    allow_archaic_words: bool = True
    spelling: str = "both"

    def __post_init__(self) -> None:
        if self.spelling not in {"both", "american", "british"}:
            raise ValueError("spelling must be 'both', 'american', or 'british'")


def normalize_word(word: str) -> str:
    """Normalize presentation, not morphology; the lexicon remains authoritative."""
    return word.strip().replace("â€™", "'").casefold()


class WordValidator:
    """Expose the stable ``is_valid_english`` boundary used by the game."""

    def __init__(self, lexicon: EnglishLexicon | str | Path, policy: ValidationPolicy | None = None) -> None:
        self.lexicon = FileLexicon(lexicon) if isinstance(lexicon, (str, Path)) else lexicon
        self.policy = policy or ValidationPolicy()

    @staticmethod
    def normalize(guess: str) -> str:
        return normalize_word(guess)

    def is_valid_english(self, guess: str) -> bool:
        word = normalize_word(guess)
        if not _WORD_FORM.fullmatch(word):
            return False
        entry = self.lexicon.entry_for(word)
        return entry is not None and self._allowed(entry)

    def is_valid(self, guess: str) -> bool:
        """Compatibility alias while callers migrate to the clearer contract."""
        return self.is_valid_english(guess)

    def _allowed(self, entry: LexiconEntry) -> bool:
        labels = entry.labels
        if "proper_noun" in labels and not self.policy.allow_proper_nouns:
            return False
        if "abbreviation" in labels and not self.policy.allow_abbreviations:
            return False
        if "offensive" in labels and not self.policy.allow_offensive_terms:
            return False
        if "archaic" in labels and not self.policy.allow_archaic_words:
            return False
        if self.policy.spelling == "american" and "british" in labels and "american" not in labels:
            return False
        if self.policy.spelling == "british" and "american" in labels and "british" not in labels:
            return False
        return True


class InMemoryLexicon:
    """Small test adapter; production imports should use ``FileLexicon``."""

    def __init__(self, entries: Iterable[LexiconEntry]) -> None:
        self._entries = {normalize_word(entry.word): entry for entry in entries}

    def entry_for(self, normalized_word: str) -> LexiconEntry | None:
        return self._entries.get(normalized_word)
