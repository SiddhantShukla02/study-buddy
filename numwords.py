"""Spoken numbers to digits: "fifty six" -> "56", "nineteen forty seven" -> "1947".

Speech-to-text often returns number words instead of digits, which would make a correct spoken
answer fail against a stored "56". Standard library only. Anything it cannot parse safely
(for example "five six") is left untouched.
"""
import re

UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000}
ZERO = {"zero": 0}
ALL = {**UNITS, **TEENS, **TENS, **SCALES, **ZERO}


def _kind(w: str) -> str:
    if w in UNITS:
        return "unit"
    if w in TEENS:
        return "teen"
    if w in TENS:
        return "tens"
    if w in SCALES:
        return "scale"
    return "zero"


def _under_100(run: list[str]) -> int | None:
    if len(run) == 1 and run[0] in {**UNITS, **TEENS, **TENS}:
        return ALL[run[0]]
    if len(run) == 2 and run[0] in TENS and run[1] in UNITS:
        return TENS[run[0]] + UNITS[run[1]]
    return None


def parse_run(run: list[str]) -> int | None:
    """Value of a run of number words, or None if it is not a well-formed number."""
    if run == ["zero"]:
        return 0
    if "zero" in run or not run:
        return None
    # Year style: "nineteen forty seven", "twenty twenty six", "nineteen oh five".
    if not any(w in SCALES for w in run) and len(run) >= 2 and run[0] in {**TEENS, **TENS}:
        first = ALL[run[0]]
        if run[1] == "oh" and len(run) == 3 and run[2] in UNITS:
            return first * 100 + UNITS[run[2]]
        if run[1] in {**TENS, **TEENS}:
            second = _under_100(run[1:])
            if second is not None:
                return first * 100 + second
    if "oh" in run:  # "oh" only means zero inside a year like "nineteen oh five"
        return None
    total = current = 0
    last = None
    for w in run:
        k = _kind(w)
        if k == "unit" and last not in (None, "tens", "scale"):
            return None
        if k in ("teen", "tens") and last not in (None, "scale"):
            return None
        if k == "scale" and last is None:
            return None
        if k == "scale":
            if w == "hundred":
                current *= 100
            else:
                total += current * 1000
                current = 0
        else:
            current += ALL[w]
        last = k
    return total + current


def numberize(text: str) -> str:
    """Replace runs of spoken number words with digits."""
    text = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", text)
    words = text.split()
    clean = [w.lower().strip(".,!?;:") for w in words]
    out: list[str] = []
    i = 0
    while i < len(words):
        if clean[i] not in ALL:
            out.append(words[i])
            i += 1
            continue
        j = i
        run: list[str] = []
        while j < len(words):
            w = clean[j]
            nxt = clean[j + 1] if j + 1 < len(words) else ""
            if w in ALL:
                run.append(w)
            elif w == "and" and run and run[-1] in SCALES and nxt in ALL:
                pass  # "one hundred and five"
            elif w == "oh" and run and run[-1] in {**TEENS, **TENS} and nxt in UNITS:
                run.append(w)
            else:
                break
            j += 1
        value = parse_run(run)
        lone_one = run == ["one"] and len(words) > 1  # "no one knows" must stay as words
        if value is None or lone_one:
            out.extend(words[i:j])
        else:
            out.append(str(value))
        i = j
    return " ".join(out)
