"""Tests for the MCP wiring in server.py: tool registration, identity, timezone, auth gate, simulator.

These need the real `mcp` package (pip install -r requirements-dev.txt). Without it the whole file is
skipped. The HTTP route tests additionally need httpx (installed with mcp).
"""
import asyncio
import json
import os

os.environ["STUDYBUDDY_DB"] = ":memory:"  # must be set before importing server
os.environ["STUDYBUDDY_NO_DOTENV"] = "1"  # tests never read a developer's real .env (no accidental Bedrock calls)

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

import server  # noqa: E402
import router  # noqa: E402

EXPECTED_TOOLS = {
    "add_study_task", "list_study_tasks", "complete_study_task", "add_flashcard", "quiz_me",
    "check_answer", "plan_revision", "study_summary", "set_timezone", "generate_flashcards_from_notes",
}


class FakeRequest:
    def __init__(self, headers):
        self.headers = headers


class FakeRequestContext:
    def __init__(self, headers):
        self.request = FakeRequest(headers)


class FakeCtx:
    def __init__(self, headers):
        self.request_context = FakeRequestContext(headers)


def say(text, session="t"):
    return asyncio.run(server.route_utterance(text, session))


def call(name, args):
    return server._normalize(asyncio.run(server.mcp.call_tool(name, args)))


@pytest.fixture(autouse=True)
def clean_router_state():
    router.STATE.clear()
    server.HISTORY.clear()


def test_all_ten_tools_are_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == EXPECTED_TOOLS


def test_ctx_is_hidden_from_the_tool_input_schema():
    for tool in asyncio.run(server.mcp.list_tools()):
        assert "ctx" not in tool.inputSchema.get("properties", {}), tool.name


def test_tools_carry_titles_and_annotations():
    by_name = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert by_name["study_summary"].annotations.readOnlyHint is True
    assert by_name["quiz_me"].annotations.readOnlyHint is False
    assert all(t.title for t in by_name.values())


def test_uid_is_stable_distinct_and_hashed():
    a1 = server.uid(FakeCtx({"x-user-id": "alice"}))
    a2 = server.uid(FakeCtx({"x-user-id": "alice"}))
    b = server.uid(FakeCtx({"x-user-id": "bob"}))
    assert a1 == a2 and a1 != b
    assert "alice" not in a1 and len(a1) == 12


def test_uid_prefers_authorization_and_falls_back_to_default():
    auth = server.uid(FakeCtx({"authorization": "Bearer abc", "x-user-id": "alice"}))
    assert auth == server.uid(FakeCtx({"authorization": "Bearer abc"}))
    assert server.uid(FakeCtx({})) == server.uid(object())  # no header and no request both -> default


def test_timezone_header_is_remembered_and_bad_ones_ignored():
    user = server.uid(FakeCtx({"x-user-id": "tz-user"}))
    server.today_for(FakeCtx({"x-user-id": "tz-user", "x-timezone": "Asia/Kolkata"}), user)
    assert server.store.get_tz(server.DB, user) == "Asia/Kolkata"
    server.today_for(FakeCtx({"x-user-id": "tz-user", "x-timezone": "Not/AZone"}), user)
    assert server.store.get_tz(server.DB, user) == "Asia/Kolkata"


def test_every_tool_result_has_a_speech_field():
    assert call("quiz_me", {"subject": "math"})["speech"]
    assert call("study_summary", {})["speech"]
    listed = call("list_study_tasks", {})
    assert set(listed) >= {"tasks", "count", "speech"}
    assert call("set_timezone", {"timezone": "Asia/Kolkata"})["speech"]
    assert "error" in call("set_timezone", {"timezone": "Mars/Base"})


def test_generate_flashcards_works_without_bedrock():
    r = call("generate_flashcards_from_notes", {"notes": "Osmosis is the movement of water across a membrane.", "subject": "biology"})
    assert r["added"] == 1 and r["source"] in {"rules", "bedrock"}
    assert "error" in call("generate_flashcards_from_notes", {"notes": "   "})


MATH_ANSWERS = {
    "What is the derivative of x squared?": "2x",
    "What is the value of 7 times 8?": "56",
    "What is the square root of 144?": "12",
}


def test_simulator_quiz_miss_then_the_same_question_returns():
    first = say("quiz me on math")
    assert first["calls"][0]["tool"] == "quiz_me"
    question = next(q for q in MATH_ANSWERS if q in first["say"])
    wrong = say("banana")
    assert wrong["calls"][0]["tool"] == "check_answer" and "Not quite" in wrong["say"]
    again = say("quiz me on math")
    assert question in again["say"]  # the missed card is prioritised
    assert "Correct" in say(MATH_ANSWERS[question])["say"]


def test_simulator_sessions_do_not_share_a_pending_question():
    a = say("quiz me on math", "alice")
    assert router.STATE["alice"]["qid"] and "bob" not in router.STATE
    b = say("how am I doing", "bob")
    assert b["calls"][0]["tool"] == "study_summary" and router.STATE["bob"]["qid"] is None


def test_simulator_remember_and_notes_create_flashcards():
    r = say("remember that mitosis is cell division")
    assert r["calls"][0]["tool"] == "add_flashcard" and r["calls"][0]["args"]["back"] == "cell division"
    n = say("make flashcards from: Osmosis is the movement of water across a membrane")
    assert n["calls"][0]["tool"] == "generate_flashcards_from_notes" and "flashcard" in n["say"]


def test_simulator_progress_and_tasks():
    assert say("how am I doing")["calls"][0]["tool"] == "study_summary"
    added = say("add a task to read chapter 5")
    assert added["calls"][0]["tool"] == "add_study_task" and "Added" in added["say"]
    assert say("what's on my list")["calls"][0]["tool"] == "list_study_tasks"
    plan = say("plan 2 days for history")
    assert plan["calls"][0]["tool"] == "plan_revision" and "2 days" in plan["say"]


def test_simulator_unknown_input_gives_help():
    assert "Try:" in say("blah blah")["say"]


def test_http_routes_and_auth_gate(monkeypatch):
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    async def fake_handle(text, session, tz):  # avoid a real network hop to ourselves in unit tests
        return {**(await server.route_utterance(text, session)), "mode": "keyword"}

    monkeypatch.setattr(server, "handle_utterance", fake_handle)
    # `with` starts the app's lifespan, which the MCP session manager needs before it accepts /mcp requests.
    with TestClient(server.build_app(), raise_server_exceptions=False) as client:
        home = client.get("/")
        assert home.status_code == 200 and "StudyBuddy" in home.text
        r = client.post("/api/utter", json={"text": "quiz me on history", "session": "s1"})
        body = r.json()
        assert r.status_code == 200 and body["calls"][0]["tool"] == "quiz_me" and body["mode"] == "keyword"
        health = client.get("/api/health").json()
        assert health["ok"] is True and health["tools"] == 10 and health["agent"] in {"keyword", "bedrock"}

        monkeypatch.setattr(server, "REQUIRE_AUTH", True)
        assert client.get("/mcp").status_code == 401
        assert client.get("/mcp", headers={"X-User-Id": "someone"}).status_code != 401
        assert client.get("/").status_code == 200  # only /mcp is gated
