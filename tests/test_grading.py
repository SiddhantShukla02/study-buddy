"""Unit tests for grading.py. No dependencies beyond the standard library."""
from grading import grade, norm


def check(cases, expected):
    for given, correct in cases:
        assert grade(given, correct) is expected, f"grade({given!r}, {correct!r}) should be {expected}"


def test_norm_strips_punctuation_and_case():
    assert norm("  It's  56!! ") == "its 56"
    assert norm("3.5.") == "3.5"
    assert norm("-4") == "-4"
    assert norm("") == ""
    assert norm("!!!") == ""


def test_exact_and_spacing_matches():
    check([("56", "56"), ("DNA", "dna"), ("2 x", "2x"), ("2X", "2x"), ("Mitochondria.", "mitochondria")], True)


def test_whole_word_inside_a_sentence():
    check([
        ("it's 56", "56"),
        ("I think the answer is 1947", "1947"),
        ("jawaharlal nehru", "nehru"),
        ("The mughals built it", "mughal"),
    ], True)


def test_numbers_never_match_loosely():
    check([("156", "56"), ("55", "56"), ("1948", "1947"), ("560", "56"), ("5", "56")], False)


def test_short_answers_must_be_exact():
    check([("rna", "dna"), ("dn", "dna"), ("dnaa", "dna")], False)


def test_single_word_typos_are_forgiven():
    check([("mitochondrion", "mitochondria"), ("photosynthesys", "photosynthesis"), ("mughals", "mughal")], True)


def test_clearly_wrong_single_words_fail():
    check([("banana", "mitochondria"), ("ribosome", "mitochondria"), ("", "mitochondria"), ("   ", "56")], False)


def test_multi_word_answers_need_most_words():
    check([
        ("it is cell division", "cell division"),
        ("division of the cell", "cell division"),  # both words present, order ignored
        ("powerhouse cell", "the powerhouse of the cell"),
    ], True)
    check([("division", "cell division"), ("banana split", "cell division")], False)


def test_empty_correct_answer_never_matches():
    check([("anything", ""), ("", "")], False)


def test_filler_words_are_ignored_but_content_words_still_count():
    check([("mitochondrion", "the mitochondria"), ("powerhouse cell", "the powerhouse of the cell")], True)
    check([("the", "the mitochondria"), ("the cell", "the powerhouse of the cell")], False)
