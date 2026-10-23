"""Tests for agent.py with a scripted fake model and a fake tool runner. No network, no MCP SDK."""
import asyncio
from types import SimpleNamespace

import agent


def tool_use(name, args, tid="t1"):
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": args}}]}},
            "stopReason": "tool_use"}


def final(text):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": "end_turn"}


def scripted(replies, seen=None):
    it = iter(replies)

    def converse(messages, system, tools):
        if seen is not None:
            seen.append([m["role"] for m in messages])
        return next(it)

    return converse


def test_to_bedrock_tools_shape():
    t = SimpleNamespace(name="quiz_me", description="Ask a question", inputSchema={"type": "object", "properties": {}})
    spec = agent.to_bedrock_tools([t])[0]["toolSpec"]
    assert spec["name"] == "quiz_me" and spec["inputSchema"]["json"]["type"] == "object"


def test_turn_calls_a_tool_then_answers():
    calls = []

    async def call_tool(name, args):
        calls.append((name, args))
        return {"question_id": "7", "question": "What is 7 times 8?", "speech": "Here's one."}

    history = []
    say, trace = asyncio.run(agent.run_turn("quiz me", [], call_tool, history,
                                            converse=scripted([tool_use("quiz_me", {"subject": "math"}), final("What is 7 times 8?")])))
    assert say == "What is 7 times 8?"
    assert calls == [("quiz_me", {"subject": "math"})]
    assert trace[0]["tool"] == "quiz_me" and trace[0]["result"]["question_id"] == "7"
    assert len(history) == 1 and history[0][0]["role"] == "user"


def test_history_carries_tool_results_into_the_next_turn_with_alternating_roles():
    async def call_tool(name, args):
        return {"question_id": "7", "speech": "ok"}

    history, seen = [], []
    asyncio.run(agent.run_turn("quiz me", [], call_tool, history,
                               converse=scripted([tool_use("quiz_me", {}), final("Q?")], seen)))
    asyncio.run(agent.run_turn("fifty six", [], call_tool, history, converse=scripted([final("Correct")], seen)))
    last = seen[-1]
    assert last == ["user", "assistant", "user", "assistant", "user"]  # previous turn kept whole, then the new user message
    assert all(a != b for a, b in zip(last, last[1:]))


def test_tool_exceptions_are_returned_to_the_model_not_raised():
    async def call_tool(name, args):
        raise RuntimeError("boom")

    say, trace = asyncio.run(agent.run_turn("x", [], call_tool, [],
                                            converse=scripted([tool_use("quiz_me", {}), final("Sorry, something broke.")])))
    assert say == "Sorry, something broke." and trace[0]["result"] == {"error": "boom"}


def test_runaway_tool_loops_stop_and_keep_roles_valid():
    async def call_tool(name, args):
        return {"speech": "again"}

    history = []
    say, _ = asyncio.run(agent.run_turn("x", [], call_tool, history,
                                        converse=scripted([tool_use("quiz_me", {})] * 10), max_steps=3))
    assert "too many steps" in say
    assert history[0][-1]["role"] == "assistant"


def test_history_is_trimmed():
    async def call_tool(name, args):
        return {}

    history = []
    for i in range(agent.MAX_TURNS + 3):
        asyncio.run(agent.run_turn(f"msg {i}", [], call_tool, history, converse=scripted([final("ok")])))
    assert len(history) == agent.MAX_TURNS
