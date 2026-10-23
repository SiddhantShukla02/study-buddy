"""Tests for notes.py (flashcards from notes). No network: Bedrock is replaced by a fake."""
import json

import notes


def fake_reply(text):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": "end_turn"}


def test_rule_based_extracts_definitions_and_colon_lines():
    text = "Osmosis is the movement of water across a membrane. Mitosis: cell division\nRemember to sleep early"
    cards = notes.rule_based(text, 10)
    fronts = {c["front"]: c["back"] for c in cards}
    assert fronts["What is Osmosis?"] == "the movement of water across a membrane"
    assert fronts["What is Mitosis?"] == "cell division"


def test_rule_based_respects_limit_and_dedupes():
    text = "Alpha is one. Alpha is one. Beta is two. Gamma is three."
    assert len(notes.rule_based(text, 2)) == 2
    assert len({c["front"] for c in notes.rule_based(text, 10)}) == 3


def test_rule_based_ignores_text_with_no_definitions():
    assert notes.rule_based("Remember to sleep early and drink water", 5) == []


def test_parse_json_cards_tolerates_fences_and_junk():
    raw = 'Sure!\n```json\n[{"front": "Q1?", "back": "A1."}, {"front": "", "back": "x"}, 5]\n```'
    assert notes.parse_json_cards(raw, 5) == [{"front": "Q1?", "back": "A1"}]
    assert notes.parse_json_cards("no json here", 5) == []
    assert notes.parse_json_cards("[not json]", 5) == []


def test_generate_uses_bedrock_reply_when_valid():
    body = json.dumps([{"front": "What is ATP?", "back": "energy currency"}])
    cards, source = notes.generate("ATP is energy", "biology", 5, converse=lambda *a: fake_reply(body))
    assert source == "bedrock" and cards == [{"front": "What is ATP?", "back": "energy currency"}]


def test_generate_falls_back_when_bedrock_errors_or_returns_garbage():
    def boom(*a):
        raise RuntimeError("AccessDenied")

    cards, source = notes.generate("Osmosis is water movement", "bio", 5, converse=boom)
    assert source == "rules" and cards[0]["front"] == "What is Osmosis?"
    cards, source = notes.generate("Osmosis is water movement", "bio", 5, converse=lambda *a: fake_reply("sorry"))
    assert source == "rules"


def test_generate_clamps_max_cards():
    text = ". ".join(f"Term{i} is thing{i}" for i in range(30))
    cards, _ = notes.generate(text, "x", 999, converse=None)
    assert 1 <= len(cards) <= 12
