"""Answer grading. Pure functions, standard library only.

grade(given, correct) decides whether a spoken or typed answer matches the stored one.
Spoken numbers are converted first ("fifty six" -> 56, "nineteen forty seven" -> 1947).
Rules, in order:
  1. Same text after normalising case and punctuation (spaces ignored: "2 x" == "2x").
  2. The correct answer appears as a whole-word run inside a longer reply
     ("it's 56" matches "56", but "156" does not).
  3. Multi-word answers: at least 70% of the expected content words must be present
     (filler words such as "the" and "of" are ignored; plurals are folded).
  4. Single-word text answers of 5+ letters tolerate a small typo ("mughals", "mitochondrion").
     Numbers and very short answers ("dna", "56") must match exactly.
"""
import difflib
import re

from numwords import numberize

FUZZY_CUTOFF = 0.8
WORD_OVERLAP_CUTOFF = 0.7
MIN_FUZZY_LENGTH = 5
STOPWORDS = {"a", "an", "the", "of", "is", "are", "to", "in", "and", "it", "its", "that", "which"}


def norm(text: str) -> str:
    """Lower-case, drop apostrophes and punctuation, keep digits, '.', '-' and '/' inside tokens."""
    text = text.lower().replace("'", "")
    tokens = [t.strip(".,/") for t in re.findall(r"[a-z0-9.,\-/]+", text)]
    return " ".join(t for t in tokens if any(ch.isalnum() for ch in t))


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _is_number(word: str) -> bool:
    return word.replace(".", "", 1).replace("-", "", 1).replace("/", "", 1).isdigit()


def stem(word: str) -> str:
    """Crude plural folding so "cells" matches "cell" (speech-to-text pluralises freely)."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def grade(given: str, correct: str) -> bool:
    g, c = norm(numberize(given)).split(), norm(numberize(correct)).split()
    if not g or not c:
        return False
    if "".join(g) == "".join(c):
        return True
    if _contains(g, c):
        return True
    content = [w for w in c if w not in STOPWORDS] or c
    if len(content) >= 2:
        present = set(g) | {stem(w) for w in g}
        hits = sum(1 for w in content if w in present or stem(w) in present)
        return hits / len(content) >= WORD_OVERLAP_CUTOFF
    word = content[0]
    if _is_number(word) or len(word) < MIN_FUZZY_LENGTH:
        return False
    return any(difflib.SequenceMatcher(None, w, word).ratio() >= FUZZY_CUTOFF for w in g)
