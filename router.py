"""Keyword intent router: the offline fallback for the simulator when no LLM is configured.

It maps simple phrases to MCP tool calls. State (the pending quiz question) is kept per session,
so two people using the simulator at once never answer each other's questions.
`call` is any async function (tool_name, args) -> dict, so the same router works in-process (tests)
or over real MCP HTTP (the live simulator).

Commands are matched as WHOLE WORDS, never substrings: "photoplankton" is an answer, not "plan".
"""
import re

import store

# Words that mark an utterance as a command while a quiz question is pending.
COMMAND_WORDS = {"quiz", "plan", "add", "list", "tasks", "done", "remember", "progress", "summary", "streak",
                 "flashcards", "timezone", "remind"}
COMMAND_STARTS = {"quiz", "plan", "add", "remind", "list", "remember", "make", "create", "generate", "how",
                  "what's", "whats", "show", "mark"}
HELP = ("Try: quiz me on math, plan 4 days for biology, add a task to read chapter 5, "
        "remember that mitosis is cell division, make flashcards from: Osmosis is the movement of water "
        "across a membrane, or how am I doing.")
STATE: dict[str, dict] = {}


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t)


def is_command(t: str) -> bool:
    """True if the utterance is a command rather than an answer to the pending question."""
    w = _words(t)
    return bool(w) and (w[0] in COMMAND_STARTS or bool(COMMAND_WORDS & set(w)) or "how am i" in t)


async def route(text: str, call, session: str = "default") -> str:
    """Return what the assistant says. Tool calls go through `call`."""
    st = STATE.setdefault(session, {"qid": None})
    t = text.lower().strip()
    w = set(_words(t))
    n = re.search(r"(\d+)", t)
    subj = next((s for s in store.BUILTIN_CARDS if s in w), None)
    remember = re.match(r"^remember (?:that )?(.+?) (?:is|are|means) (.+)$", text.strip(), re.IGNORECASE)
    notes = re.match(r"^(?:make|create|generate)\s+(?:some\s+)?(?:flashcards|cards)(?:\s+(?:from|about|for))?\s*:?\s*(.+)$",
                     text.strip(), re.IGNORECASE | re.DOTALL)

    if st["qid"] and not is_command(t):
        r = await call("check_answer", {"question_id": st["qid"], "answer": text})
        st["qid"] = None
        return r["speech"]
    if notes:
        r = await call("generate_flashcards_from_notes", {"notes": notes.group(1), "subject": subj or "general"})
        return r["speech"]
    if remember:
        thing, meaning = remember.group(1).strip(), remember.group(2).strip()
        r = await call("add_flashcard", {"front": f"What is {thing}?", "back": meaning, "subject": subj or "general"})
        return r["speech"]
    if w & {"quiz", "quizzes"}:
        r = await call("quiz_me", {"subject": subj or ""})
        st["qid"] = r.get("question_id")
        return r["speech"]
    if w & {"progress", "summary", "streak"} or "how am i" in t:
        return (await call("study_summary", {}))["speech"]
    if w & {"plan", "plans"} or ("revise" in w and "for" in w):
        r = await call("plan_revision", {"subject": subj or "biology", "days": int(n.group(1)) if n else 3})
        return r["speech"]
    if t.startswith(("add", "remind")):
        title = re.sub(r"^(add|remind me to)( a)?( study)?( task)?( to)?", "", t).strip() or t
        return (await call("add_study_task", {"title": title, "subject": subj or "general"}))["speech"]
    if w & {"done", "finished", "complete", "completed"}:
        if not n:
            return "Which task number did you finish?"
        return (await call("complete_study_task", {"task_id": int(n.group(1))}))["speech"]
    if w & {"list", "tasks", "plate"} or "what do i" in t:
        return (await call("list_study_tasks", {}))["speech"]
    return HELP
