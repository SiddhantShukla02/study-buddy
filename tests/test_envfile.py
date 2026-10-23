"""Tests for envfile.py. Standard library only."""
import os

import envfile


def test_parse_handles_comments_quotes_blanks_and_export():
    text = "# comment\nA=1\n  B = two  \nC=\"quoted value\"\nD='single'\nEMPTY=\nexport E=5\nF=val # trailing\nnoequals\n"
    assert envfile.parse(text) == {"A": "1", "B": "two", "C": "quoted value", "D": "single", "E": "5", "F": "val"}


def test_load_env_sets_missing_vars_but_never_overrides_real_ones(tmp_path, monkeypatch=None):
    p = tmp_path / ".env"
    p.write_text("SB_TEST_NEW=from-file\nSB_TEST_KEEP=from-file\n", encoding="utf-8")
    os.environ.pop("SB_TEST_NEW", None)
    os.environ["SB_TEST_KEEP"] = "from-terminal"
    os.environ.pop("STUDYBUDDY_NO_DOTENV", None)
    try:
        applied = envfile.load_env(p)
        assert applied == ["SB_TEST_NEW"]
        assert os.environ["SB_TEST_NEW"] == "from-file" and os.environ["SB_TEST_KEEP"] == "from-terminal"
    finally:
        os.environ.pop("SB_TEST_NEW", None)
        os.environ.pop("SB_TEST_KEEP", None)


def test_missing_file_and_opt_out_are_harmless(tmp_path):
    assert envfile.load_env(tmp_path / "nope.env") == []
    p = tmp_path / ".env"
    p.write_text("SB_TEST_X=1\n")
    os.environ["STUDYBUDDY_NO_DOTENV"] = "1"
    try:
        assert envfile.load_env(p) == [] and "SB_TEST_X" not in os.environ
    finally:
        os.environ.pop("STUDYBUDDY_NO_DOTENV", None)


def test_windows_encodings_are_read(tmp_path):
    for enc in ("utf-8-sig", "utf-16"):
        p = tmp_path / f"{enc}.env"
        p.write_text("SB_TEST_ENC=ok\n", encoding=enc)
        assert envfile.parse(envfile._read(p)) == {"SB_TEST_ENC": "ok"}
