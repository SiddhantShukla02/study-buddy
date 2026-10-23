"""Unit tests for numwords.py (spoken numbers to digits). Standard library only."""
from numwords import numberize


def test_basic_and_compound_numbers():
    assert numberize("twelve") == "12"
    assert numberize("fifty six") == "56"
    assert numberize("forty-seven") == "47"
    assert numberize("one hundred and five") == "105"
    assert numberize("one thousand nine hundred forty seven") == "1947"
    assert numberize("zero") == "0"


def test_spoken_years():
    assert numberize("nineteen forty seven") == "1947"
    assert numberize("twenty twenty six") == "2026"
    assert numberize("nineteen oh five") == "1905"


def test_numbers_inside_sentences():
    assert numberize("seven times eight is fifty six") == "7 times 8 is 56"
    assert numberize("it is twelve.") == "it is 12"


def test_ambiguous_or_malformed_runs_are_left_alone():
    assert numberize("five six") == "five six"
    assert numberize("no one knows") == "no one knows"
    assert numberize("banana split") == "banana split"
    assert numberize("one") == "1"


def test_stray_oh_never_crashes():
    assert numberize("twenty oh") == "20 oh"
    assert numberize("oh") == "oh"
    assert numberize("nineteen oh five oh") == "1905 oh"
