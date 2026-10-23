"""StudyBuddy: an MCP server (Streamable HTTP) plus a simulated Alexa+ chat page.

Run:  python server.py        -> MCP endpoint http://localhost:8000/mcp
                              -> Simulator    http://localhost:8000/

Environment variables (all optional):
  PORT           port to listen on (default 8000)
  STUDYBUDDY_DB  SQLite file path (default studybuddy.db; use ":memory:" for throwaway data)

The tools here are thin wrappers. The study logic lives in store.py and grading.py.
"""
import hashlib
import json
import os
import re
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import store

DB = store.connect(os.environ.get("STUDYBUDDY_DB", "studybuddy.db"))
PAGE = (Path(__file__).parent / "simulator.html").read_text(encoding="utf-8")

mcp = FastMCP(
    "StudyBuddy",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    stateless_http=True,
    json_response=True,
    # Relax DNS-rebinding checks so a tunnel (ngrok, cloudflared) can reach it.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def uid(ctx: Context) -> str:
    """Identify the caller from its Authorization or X-User-Id header.

    The raw value is hashed so secrets are never stored. Calls with no HTTP request
    (the in-process simulator) or no header share the 'default' user.
    """
    try:
        headers = ctx.request_context.request.headers
        token = headers.get("authorization") or headers.get("x-user-id") or "default"
    except Exception:
        token = "default"
    return hashlib.sha256(token.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- tools
@mcp.tool()
def add_study_task(title: str, ctx: Context, subject: str = "general", due_in_days: int = 1) -> dict:
    """Add a study task, e.g. 'revise chapter 4' for biology due in 2 days."""
    return store.add_task(DB, uid(ctx), title, subject, due_in_days)


@mcp.tool()
def list_study_tasks(ctx: Context, include_done: bool = False) -> list[dict]:
    """List study tasks, soonest due first."""
    return store.list_tasks(DB, uid(ctx), include_done)


@mcp.tool()
def complete_study_task(task_id: int, ctx: Context) -> dict:
    """Mark a study task as done."""
    return store.complete_task(DB, uid(ctx), task_id)


@mcp.tool()
def add_flashcard(front: str, back: str, ctx: Context, subject: str = "general") -> dict:
    """Save a flashcard from the learner's own notes, e.g. front='What is mitosis?', back='cell division'."""
    return store.add_card(DB, uid(ctx), front, back, subject)


@mcp.tool()
def quiz_me(ctx: Context, subject: str = "") -> dict:
    """Ask one quiz question. Cards that are due or often missed come first. Subject is optional."""
    return store.next_question(DB, uid(ctx), subject)


@mcp.tool()
def check_answer(question_id: str, answer: str, ctx: Context) -> dict:
    """Check the learner's answer to a quiz question and schedule its next review."""
    return store.check_answer(DB, uid(ctx), question_id, answer)


@mcp.tool()
def plan_revision(subject: str, ctx: Context, days: int = 3, minutes_per_day: int = 45) -> dict:
    """Build a day-by-day revision plan and save each day as a task."""
    return store.plan_revision(DB, uid(ctx), subject, days, minutes_per_day)


@mcp.tool()
def study_summary(ctx: Context) -> dict:
    """Show study progress: streak, accuracy, cards due and weakest subjects."""
    return store.summary(DB, uid(ctx))


# ---------------------------------------------------------------- simulator
LAST_QID = {"id": None}  # the simulator is single-user, so one pending question is enough
NOT_COMMANDS = ("quiz", "plan", "add", "list", "done", "remember", "progress", "summary", "streak", "how am i")


async def route_utterance(text: str) -> dict:
    """Tiny intent router standing in for Alexa+'s LLM: maps speech to MCP tool calls."""
    t = text.lower().strip()
    calls = []

    async def call(name, args):
        res = await mcp.call_tool(name, args)
        if isinstance(res, tuple):  # (content, structured) for list-returning tools
            data = res[1].get("result", res[1])
        else:  # list of TextContent holding JSON for dict-returning tools
            data = json.loads(res[0].text)
        calls.append({"tool": name, "args": args, "result": data})
        return data

    n = re.search(r"(\d+)", t)
    subj = next((s for s in store.BUILTIN_CARDS if s in t), None)
    remember = re.match(r"^remember (?:that )?(.+?) (?:is|are|means) (.+)$", text.strip(), re.IGNORECASE)

    if LAST_QID["id"] and not any(k in t for k in NOT_COMMANDS):
        r = await call("check_answer", {"question_id": LAST_QID["id"], "answer": text})
        LAST_QID["id"] = None
        if r.get("error"):
            say = r["error"]
        elif r["correct"]:
            say = f"Correct! I'll ask this one again in {r['next_review_in_days']} day(s). Say quiz me for another."
        else:
            say = f"Not quite. The answer was {r['right_answer']}. I'll bring it back so you can lock it in."
    elif remember:
        thing, meaning = remember.group(1).strip(), remember.group(2).strip()
        r = await call("add_flashcard", {"front": f"What is {thing}?", "back": meaning, "subject": subj or "general"})
        say = r.get("error") or f"Saved a flashcard: {thing}. Say quiz me to practise it."
    elif "quiz" in t:
        r = await call("quiz_me", {"subject": subj or ""})
        LAST_QID["id"] = r.get("question_id")
        say = r.get("question") or r.get("message") or r.get("error")
    elif any(k in t for k in ("progress", "summary", "streak", "how am i")):
        r = await call("study_summary", {})
        if not r["answered"]:
            say = f"You haven't answered anything yet. You have {r['cards_due']} cards ready. Say quiz me."
        else:
            say = (
                f"You've answered {r['answered']} questions with {round(r['accuracy'] * 100)}% right, "
                f"a {r['streak_days']}-day streak, and {r['cards_due']} cards due."
            )
            if r["weakest_subjects"]:
                say += " Focus on " + " and ".join(r["weakest_subjects"]) + "."
    elif "plan" in t or "revise" in t and "for" in t:
        s = subj or "biology"
        r = await call("plan_revision", {"subject": s, "days": int(n.group(1)) if n else 3})
        say = f"Done. I planned {len(r['plan'])} days of {s} revision and added them to your list."
    elif t.startswith(("add", "remind")):
        title = re.sub(r"^(add|remind me to)( a)?( study)?( task)?( to)?", "", t).strip() or t
        r = await call("add_study_task", {"title": title, "subject": subj or "general"})
        say = r.get("error") or f"Added: {r['title']}, due {r['due']}."
    elif "done" in t or "finished" in t or "complete" in t:
        if not n:
            say = "Which task number did you finish?"
        else:
            r = await call("complete_study_task", {"task_id": int(n.group(1))})
            say = r.get("error") or f"Nice work. Marked task {r['id']} as done."
    elif any(k in t for k in ("list", "tasks", "plate", "what do i")):
        r = await call("list_study_tasks", {})
        say = (
            "You have " + str(len(r)) + " open: " + "; ".join(f"{x['id']}. {x['title']}" for x in r[:5])
            if r else "Nothing open. You're clear."
        )
    else:
        say = (
            "Try: quiz me on math, plan 4 days for biology, add a task to read chapter 5, "
            "remember that mitosis is cell division, or how am I doing."
        )
    return {"say": say, "calls": calls}


@mcp.custom_route("/api/utter", methods=["POST"])
async def utter(request: Request):
    body = await request.json()
    return JSONResponse(await route_utterance(body.get("text", "")))


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request):
    return HTMLResponse(PAGE)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
