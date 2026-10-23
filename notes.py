"""Turn a learner's pasted notes into flashcards.

generate() tries Amazon Bedrock first (see llm.py). If Bedrock is not configured, or the call or
its output is unusable, it falls back to a deterministic rule-based extractor, so the tool always
works. The result says which path produced the cards ("bedrock" or "rules").
"""
import json
import re

import llm

MAX_NOTES_CHARS = 6000
CARD_PROMPT = (
    "You turn study notes into flashcards for a voice assistant. Reply with ONLY a JSON array of "
    "objects like {\"front\": \"...\", \"back\": \"...\"}. Rules: at most {n} cards; each front is a "
    "clear question that makes sense when read aloud; each back is a SHORT answer of 1 to 6 words "
    "that a student could say aloud; use only facts stated in the notes; no markdown, no commentary."
)


def _clean(cards, limit: int) -> list[dict]:
    out, seen = [], set()
    for c in cards if isinstance(cards, list) else []:
        if not isinstance(c, dict):
            continue
        front, back = str(c.get("front", "")).strip(), str(c.get("back", "")).strip().rstrip(".")
        key = front.lower()
        if front and back and key not in seen and len(front) <= 300 and len(back) <= 300:
            seen.add(key)
            out.append({"front": front, "back": back})
    return out[:limit]


def parse_json_cards(text: str, limit: int) -> list[dict]:
    """Pull the JSON array out of a model reply, tolerating code fences or stray prose."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        return _clean(json.loads(text[start : end + 1]), limit)
    except ValueError:
        return []


_DEF = re.compile(
    r"^(?P<t>[^:.;]{2,60}?)\s+(?P<v>is called|is known as|refers to|means|are|is)\s+(?P<d>.{2,120})$",
    re.IGNORECASE,
)
_COLON = re.compile(r"^(?P<t>[^:]{2,60}):\s*(?P<d>.{2,120})$")


def rule_based(notes: str, limit: int) -> list[dict]:
    """Extract 'X is Y' and 'X: Y' statements. Crude but predictable and offline."""
    cards = []
    for line in re.split(r"[\n\r]+|(?<=[.!?])\s+", notes):
        line = line.strip(" -*\u2022\t").rstrip(".!?")
        if not line:
            continue
        m = _COLON.match(line)
        if m:
            cards.append({"front": f"What is {m['t'].strip()}?", "back": m["d"].strip()})
            continue
        m = _DEF.match(line)
        if m:
            verb = "are" if m["v"].lower() == "are" else "is"
            cards.append({"front": f"What {verb} {m['t'].strip()}?", "back": m["d"].strip()})
    return _clean(cards, limit)


def generate(notes: str, subject: str = "general", max_cards: int = 8, converse=None) -> tuple[list[dict], str]:
    """Return (cards, source) where source is 'bedrock' or 'rules'."""
    notes = notes.strip()[:MAX_NOTES_CHARS]
    limit = max(1, min(int(max_cards), 12))
    if llm.enabled() or converse is not None:
        try:
            call = converse or llm.converse
            reply = call(
                [{"role": "user", "content": [{"text": f"Subject: {subject}\n\nNotes:\n{notes}"}]}],
                CARD_PROMPT.replace("{n}", str(limit)),
                None,
                1200,
                0.2,
            )
            cards = parse_json_cards(llm.text_of(reply), limit)
            if cards:
                return cards, "bedrock"
        except Exception:
            pass  # fall through to the offline extractor
    return rule_based(notes, limit), "rules"
