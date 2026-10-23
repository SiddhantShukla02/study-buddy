"""StudyBuddy: an MCP server (Streamable HTTP) for Alexa+ plus an agentic Alexa+ simulator.

Run:  python server.py        -> MCP endpoint http://localhost:8000/mcp
                              -> Simulator    http://localhost:8000/
                              -> Health       http://localhost:8000/api/health

Environment variables (all optional):
  PORT                     port to listen on (default 8000)
  STUDYBUDDY_DB            SQLite file path (default studybuddy.db; ":memory:" for throwaway data)
  STUDYBUDDY_REQUIRE_AUTH  "1" -> /mcp rejects requests with no Authorization or X-User-Id header
  STUDYBUDDY_ALLOWED_HOSTS comma-separated public hostnames; turns DNS-rebinding protection ON
  STUDYBUDDY_DEFAULT_TZ    IANA timezone for learners who never set one (default UTC)
  STUDYBUDDY_SELF_URL      where the simulator reaches this server's /mcp (default http://127.0.0.1:$PORT/mcp)
  BEDROCK_MODEL_ID, AWS_REGION, AWS_BEARER_TOKEN_BEDROCK   enable the Amazon Bedrock agent + AI flashcards (see llm.py)

Any of these can live in a git-ignored `.env` file next to this script (see .env.example).

The tools here are thin wrappers. Study logic lives in store.py and grading.py.
"""
import asyncio
import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import envfile

envfile.load_env()  # read .env BEFORE anything below looks at environment variables

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import agent
import llm
import notes as notes_mod
import router
import speech
import store

PORT = int(os.environ.get("PORT", "8000"))
REQUIRE_AUTH = os.environ.get("STUDYBUDDY_REQUIRE_AUTH", "") == "1"
DEFAULT_TZ = os.environ.get("STUDYBUDDY_DEFAULT_TZ", "UTC")
SELF_URL = os.environ.get("STUDYBUDDY_SELF_URL", f"http://127.0.0.1:{PORT}/mcp")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("STUDYBUDDY_ALLOWED_HOSTS", "").split(",") if h.strip()]

DB = store.connect(os.environ.get("STUDYBUDDY_DB", "studybuddy.db"))
PAGE = (Path(__file__).parent / "simulator.html").read_text(encoding="utf-8")

mcp = FastMCP(
    "StudyBuddy",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
    # Off by default so a tunnel (ngrok, cloudflared) works; set STUDYBUDDY_ALLOWED_HOSTS in production.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(ALLOWED_HOSTS),
        allowed_hosts=ALLOWED_HOSTS + ["127.0.0.1:*", "localhost:*"],
        allowed_origins=[f"https://{h}" for h in ALLOWED_HOSTS] + ["http://127.0.0.1:*", "http://localhost:*"],
    ),
)


# ---------------------------------------------------------------- identity & time
def _headers(ctx: Context):
    try:
        return ctx.request_context.request.headers
    except Exception:  # no HTTP request (in-process call)
        return {}


def uid(ctx: Context) -> str:
    """Identify the caller from its Authorization or X-User-Id header (hashed, never stored raw)."""
    token = _headers(ctx).get("authorization") or _headers(ctx).get("x-user-id") or "default"
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def today_for(ctx: Context, user: str):
    """The learner's local date. An X-Timezone header (the simulator sends one) is remembered."""
    tz = _headers(ctx).get("x-timezone")
    if tz and store.valid_tz(tz):
        if store.get_tz(DB, user) != tz:
            store.set_tz(DB, user, tz)
    else:
        tz = store.get_tz(DB, user) or DEFAULT_TZ
    return store.local_today(tz)


def _ok(result: dict, say) -> dict:
    """Attach a `speech` field: what a voice assistant should say about this result."""
    result["speech"] = result["error"] if "error" in result else say(result)
    return result


READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


# ---------------------------------------------------------------- tools
@mcp.tool(title="Add study task", annotations=WRITE)
def add_study_task(title: str, ctx: Context, subject: str = "general", due_in_days: int = 1) -> dict:
    """Add a study task, e.g. 'revise chapter 4' for biology due in 2 days."""
    u = uid(ctx)
    r = store.add_task(DB, u, title, subject, due_in_days, today_for(ctx, u))
    return _ok(r, lambda r: f"Added: {r['title']}, due {r['due']}.")


@mcp.tool(title="List study tasks", annotations=READ)
def list_study_tasks(ctx: Context, include_done: bool = False) -> dict:
    """List the learner's open study tasks, soonest due first. Returns {tasks, count, speech}."""
    items = store.list_tasks(DB, uid(ctx), include_done)
    return _ok({"tasks": items, "count": len(items)}, speech.tasks)


@mcp.tool(title="Complete study task", annotations=WRITE)
def complete_study_task(task_id: int, ctx: Context) -> dict:
    """Mark a study task as done, by its task number."""
    r = store.complete_task(DB, uid(ctx), task_id)
    return _ok(r, lambda r: f"Nice work. Marked task {r['id']} as done.")


@mcp.tool(title="Save a flashcard", annotations=WRITE)
def add_flashcard(front: str, back: str, ctx: Context, subject: str = "general") -> dict:
    """Save one flashcard from the learner's own notes, e.g. front='What is mitosis?', back='cell division'."""
    u = uid(ctx)
    r = store.add_card(DB, u, front, back, subject, today_for(ctx, u))
    return _ok(r, lambda r: "Saved a flashcard. Say quiz me to practise it.")


@mcp.tool(title="Quiz me", annotations=WRITE)
def quiz_me(ctx: Context, subject: str = "") -> dict:
    """Ask ONE quiz question and read r.speech aloud. Do not reveal the answer. Keep question_id and pass it
    to check_answer with the learner's reply. Often-missed and due cards come first. Subject is optional."""
    u = uid(ctx)
    return _ok(store.next_question(DB, u, subject, today_for(ctx, u)), speech.quiz)


@mcp.tool(title="Check answer", annotations=WRITE)
def check_answer(question_id: str, answer: str, ctx: Context) -> dict:
    """Grade the learner's spoken answer to a quiz question (tolerates typos, plurals, spoken numbers) and
    schedule the next review. A miss comes straight back; a correct answer returns days later."""
    u = uid(ctx)
    return _ok(store.check_answer(DB, u, question_id, answer, today_for(ctx, u)), speech.answer)


@mcp.tool(title="Plan revision", annotations=WRITE)
def plan_revision(subject: str, ctx: Context, days: int = 3, minutes_per_day: int = 45) -> dict:
    """Build a day-by-day revision plan (1 to 14 days) and save each day as a study task."""
    u = uid(ctx)
    return _ok(store.plan_revision(DB, u, subject, days, minutes_per_day, today_for(ctx, u)), speech.plan)


@mcp.tool(title="Study summary", annotations=READ)
def study_summary(ctx: Context) -> dict:
    """Show study progress: streak, accuracy, cards due and weakest subjects."""
    u = uid(ctx)
    return _ok(store.summary(DB, u, today_for(ctx, u)), speech.summary)


@mcp.tool(title="Set timezone", annotations=WRITE)
def set_timezone(timezone: str, ctx: Context) -> dict:
    """Remember the learner's IANA timezone (e.g. 'Asia/Kolkata') so streaks and due dates follow their midnight."""
    return _ok(store.set_tz(DB, uid(ctx), timezone), lambda r: f"Got it. I'll use {r['timezone']} for your streaks.")


@mcp.tool(title="Flashcards from notes", annotations=WRITE)
async def generate_flashcards_from_notes(notes: str, ctx: Context, subject: str = "general", max_cards: int = 8) -> dict:
    """Turn pasted study notes into flashcards and save them. Uses Amazon Bedrock when configured, otherwise a
    rule-based extractor. The result's `source` says which one ('bedrock' or 'rules')."""
    u = uid(ctx)
    if not notes.strip():
        return _ok({"error": "Give me some notes to turn into flashcards."}, str)
    cards, source = await asyncio.to_thread(notes_mod.generate, notes, subject, max_cards)
    today, added = today_for(ctx, u), []
    for c in cards:
        if "error" in store.add_card(DB, u, c["front"], c["back"], subject, today):
            break
        added.append(c)
    return _ok({"added": len(added), "source": source, "cards": added}, speech.generated)


# ---------------------------------------------------------------- simulator
HISTORY: dict[str, list] = {}  # per-session LLM conversation history


def _normalize(res) -> dict:
    """Any MCP call result (client CallToolResult, or in-process tuple/list) -> a plain dict."""
    if hasattr(res, "content"):  # client-side CallToolResult
        if getattr(res, "isError", False):
            text = res.content[0].text if res.content else "tool error"
            raise RuntimeError(text)
        data = res.structuredContent if getattr(res, "structuredContent", None) else json.loads(res.content[0].text)
    elif isinstance(res, dict):  # some SDK versions return the structured dict directly
        data = res
    elif isinstance(res, tuple):  # (content, structured)
        data = res[1]
    else:  # list of TextContent
        data = json.loads(res[0].text)
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], dict):
        data = data["result"]
    data.setdefault("speech", data.get("error", "Done."))
    return data


async def route_utterance(text: str, session: str = "default") -> dict:
    """In-process keyword routing (used by tests and as a last resort)."""
    calls = []

    async def call(name, args):
        data = _normalize(await mcp.call_tool(name, args))
        calls.append({"tool": name, "args": args, "result": data})
        return data

    return {"say": await router.route(text, call, session), "calls": calls}


@asynccontextmanager
async def mcp_session(user: str, tz: str | None):
    """A real MCP client session to this server over Streamable HTTP."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"X-User-Id": user}
    if tz:
        headers["X-Timezone"] = tz
    async with streamablehttp_client(SELF_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def handle_utterance(text: str, session: str, tz: str | None) -> dict:
    user, note = f"sim-{session}", None
    try:
        async with mcp_session(user, tz) as s:
            async def raw_call(name, args):
                return _normalize(await s.call_tool(name, args))

            if llm.enabled():
                try:
                    tools = agent.to_bedrock_tools((await s.list_tools()).tools)
                    say, trace = await agent.run_turn(text, tools, raw_call, HISTORY.setdefault(session, []))
                    return {"say": say, "calls": trace, "mode": "agent"}
                except Exception as exc:
                    note = f"LLM unavailable ({type(exc).__name__}: {str(exc)[:160]}). Using keyword mode."
            calls = []

            async def traced(name, args):
                data = await raw_call(name, args)
                calls.append({"tool": name, "args": args, "result": data})
                return data

            say = await router.route(text, traced, session)
            return {"say": say, "calls": calls, "mode": "keyword", "note": note}
    except Exception as exc:
        return {"say": "Sorry, I couldn't reach the study server.", "calls": [], "mode": "error",
                "note": f"{type(exc).__name__}: {str(exc)[:200]}"}


@mcp.custom_route("/api/utter", methods=["POST"])
async def utter(request: Request):
    body = await request.json()
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("session") or "anon"))[:64] or "anon"
    tz = body.get("tz") if store.valid_tz(body.get("tz")) else None
    return JSONResponse(await handle_utterance(str(body.get("text", ""))[:2000], session, tz))


@mcp.custom_route("/api/health", methods=["GET"])
async def health(request: Request):
    return JSONResponse({
        "ok": True,
        "tools": len(await mcp.list_tools()),
        "agent": "bedrock" if llm.enabled() else "keyword",
        "model": llm.model_id() or None,
        "region": llm.region() if llm.enabled() else None,
        "require_auth": REQUIRE_AUTH,
    })


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request):
    return HTMLResponse(PAGE)


class AuthGate:
    """Optional: with STUDYBUDDY_REQUIRE_AUTH=1, /mcp needs an Authorization or X-User-Id header."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if REQUIRE_AUTH and scope["type"] == "http" and scope["path"].startswith("/mcp"):
            names = {k.decode().lower() for k, _ in scope["headers"]}
            if "authorization" not in names and "x-user-id" not in names:
                resp = JSONResponse({"error": "unauthorized", "detail": "Send Authorization: Bearer <token> or X-User-Id."},
                                    status_code=401, headers={"WWW-Authenticate": 'Bearer realm="studybuddy"'})
                return await resp(scope, receive, send)
        await self.app(scope, receive, send)


def build_app():
    app = mcp.streamable_http_app()
    app.add_middleware(AuthGate)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=PORT)
