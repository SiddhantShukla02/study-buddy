"""Spoken wording for tool results. Every MCP tool adds a `speech` field so any client, including
Alexa+, can voice a sensible reply without reformatting JSON. Pure functions, standard library only."""


def _days(n: int) -> str:
    return "today" if n == 0 else f"in {n} day{'s' if n != 1 else ''}"


def quiz(r: dict) -> str:
    return f"Here's one on {r['subject']}. {r['question']}" if "question" in r else r["message"]


def answer(r: dict) -> str:
    if r["correct"]:
        return f"Correct! I'll ask this one again {_days(r['next_review_in_days'])}."
    return f"Not quite. The answer was {r['right_answer']}. I'll bring it back so you can lock it in."


def summary(r: dict) -> str:
    if not r["answered"]:
        return f"You haven't answered anything yet. You have {r['cards_due']} cards ready. Say quiz me."
    s = (f"You've answered {r['answered']} questions with {round(r['accuracy'] * 100)}% right, "
         f"a {r['streak_days']}-day streak, and {r['cards_due']} cards due.")
    if r["weakest_subjects"]:
        s += " Focus on " + " and ".join(r["weakest_subjects"]) + "."
    return s


def tasks(r: dict) -> str:
    items = r["tasks"]
    if not items:
        return "Nothing open. You're clear."
    return f"You have {len(items)} open: " + "; ".join(f"{x['id']}. {x['title']}" for x in items[:5])


def plan(r: dict) -> str:
    return f"Done. I planned {len(r['plan'])} days of {r['subject']} revision and added them to your list."


def generated(r: dict) -> str:
    if not r["added"]:
        return "I couldn't find any facts to turn into flashcards. Try sentences like 'Osmosis is the movement of water.'"
    return f"I made {r['added']} flashcard{'s' if r['added'] != 1 else ''} from your notes. Say quiz me to practise."
