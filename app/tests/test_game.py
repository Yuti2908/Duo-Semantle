from datetime import date

import numpy as np

from src.game import DailyTargetRepository, DuoSemantleGame
from src.validator import InMemoryLexicon, LexiconEntry, ValidationPolicy, WordValidator


class FakeEmbeddings:
    def __init__(self, vectors):
        self.vectors = {word: np.asarray(vector, dtype=np.float64) for word, vector in vectors.items()}

    def vector_for(self, word):
        return self.vectors.get(word)


def test_invalid_word_is_not_scored():
    game = DuoSemantleGame(
        WordValidator(InMemoryLexicon([LexiconEntry("apple"), LexiconEntry("banana")])),
        FakeEmbeddings({"apple": [1, 0], "banana": [0, 1]}),
        DailyTargetRepository({date(2026, 8, 14): "banana"}),
    )

    result = game.guess("notaword", date(2026, 8, 14))

    assert result.valid is False
    assert result.score is None
    assert result.reason == "invalid English word"


def test_score_is_deterministic():
    game = DuoSemantleGame(
        WordValidator(InMemoryLexicon([LexiconEntry("apple"), LexiconEntry("banana")])),
        FakeEmbeddings({"apple": [1, 0], "banana": [0, 1]}),
        DailyTargetRepository({date(2026, 8, 14): "apple"}),
    )

    first = game.guess(" BANANA ", date(2026, 8, 14))
    second = game.guess("banana", date(2026, 8, 14))

    assert first == second
    assert first.score == 500


def test_lexical_policy_handles_the_phase_two_examples():
    validator = WordValidator(
        InMemoryLexicon(
            [
                LexiconEntry("hello"),
                LexiconEntry("elephant"),
                LexiconEntry("floccinaucinihilipilification"),
                LexiconEntry("can't"),
                LexiconEntry("mother-in-law"),
                LexiconEntry("qwerty"),
                LexiconEntry("nasa", frozenset({"abbreviation"})),
            ]
        )
    )

    assert validator.is_valid_english("hello")
    assert validator.is_valid_english("elephant")
    assert validator.is_valid_english("floccinaucinihilipilification")
    assert validator.is_valid_english("can't")
    assert validator.is_valid_english("mother-in-law")
    assert validator.is_valid_english("qwerty")
    assert not validator.is_valid_english("NASA")
    assert not validator.is_valid_english("asdfgh")


def test_policy_can_change_without_replacing_the_lexicon():
    lexicon = InMemoryLexicon([LexiconEntry("nasa", frozenset({"abbreviation"}))])

    assert not WordValidator(lexicon).is_valid_english("NASA")
    assert WordValidator(lexicon, ValidationPolicy(allow_abbreviations=True)).is_valid_english("NASA")


def test_started_game_scores_against_its_explicit_target():
    game = DuoSemantleGame(
        WordValidator(InMemoryLexicon([LexiconEntry("ocean"), LexiconEntry("sea")])),
        FakeEmbeddings({"ocean": [1, 0], "sea": [1, 0]}),
        DailyTargetRepository({}),
    )
    game.start("ocean")

    result = game.guess("sea")

    assert result.valid
    assert result.score == 1000
