import re

WORD_FORM = re.compile(r"^(?:[a-z]+|'[a-z]+)(?:['-]+[a-z]+)*'?$")


def is_valid_word(word, word_set):
    normalized = word.strip().casefold()
    if not WORD_FORM.fullmatch(normalized):
        return False
    return normalized in word_set
