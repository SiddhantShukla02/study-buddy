"""Tests for the MCP wiring in server.py: tool registration, per-user identity and the simulator.

These need the real `mcp` package (pip install -r requirements-dev.txt). Without it the
whole file is skipped. The HTTP route tests additionally need httpx (installed with mcp).
"""
import asyncio
import json
import os

os.environ["STUDYBUDDY_DB"] = ":memory:"  # must be set before importing server

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

import server  # noqa: E402

EXPECTED_TOOLS = {
    "add_study_task", "list_study_tasks", "complete_study_task", "add_flashcard",
    "quiz_me", "check_answer", "plan_revision", "study_summary",
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


def say(text):
    return asyncio.run(server.route_utterance(text))


def test_all_eight_tools_are_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == EXPECTED_TOOLS


def test_ctx_is_hidden_from_the_tool_input_schema():
    for tool in asyncio.run(server.mcp.list_tools()):
        assert "ctx" not in tool.inputSchema.get("properties", {}), tool.name


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


MATH_ANSWERS = {
    "What is the derivative of x squared?": "2x",
    "What is the value of 7 times 8?": "56",
    "What is the square root of 144?": "12",
}


def reset():
    server.LAST_QID["id"] = None  # the simulator keeps one pending question; start each test clean


def test_simulator_quiz_miss_then_the_same_question_returns():
    reset()
    first = say("quiz me on math")
    assert first["calls"][0]["tool"] == "quiz_me"
    question = first["say"]
    assert question in MATH_ANSWERS
    wrong = say("banana")
    assert wrong["calls"][0]["tool"] == "check_answer"
    assert "Not quite" in wrong["say"]
    again = say("quiz me on math")
    assert again["say"] == question  # the missed card is prioritised
    right = say(MATH_ANSWERS[question])
    assert "Correct" in right["say"]


def test_simulator_remember_creates_a_flashcard_that_can_be_quizzed():
    reset()
    r = say("remember that mitosis is cell division")
    assert r["calls"][0]["tool"] == "add_flashcard"
    assert r["calls"][0]["args"]["front"] == "What is mitosis?"
    assert r["calls"][0]["args"]["back"] == "cell division"


def test_simulator_progress_and_tasks():
    reset()
    assert say("how am I doing")["calls"][0]["tool"] == "study_summary"
    added = say("add a task to read chapter 5")
    assert added["calls"][0]["tool"] == "add_study_task" and "Added" in added["say"]
    assert say("what's on my list")["calls"][0]["tool"] == "list_study_tasks"
    plan = say("plan 2 days for history")
    assert plan["calls"][0]["tool"] == "plan_revision" and "2 days" in plan["say"]


def test_simulator_unknown_input_gives_help():
    reset()
    assert "Try:" in say("blah blah")["say"]


def test_http_routes():
    reset()
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    client = TestClient(server.mcp.streamable_http_app())
    home = client.get("/")
    assert home.status_code == 200 and "StudyBuddy" in home.text
    r = client.post("/api/utter", json={"text": "quiz me on history"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"say", "calls"} and body["calls"][0]["tool"] == "quiz_me"
    json.dumps(body)  # serialisable
