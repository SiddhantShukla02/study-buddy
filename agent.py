"""LLM agent loop: the part that stands in for Alexa+'s own reasoning in the simulator.

The model (Claude on Amazon Bedrock) is shown the MCP server's tool list, decides which tools to
call, and we execute every call over real MCP Streamable HTTP. This module has no dependency on the
MCP SDK or boto3 at import time: callers pass in `converse` and `call_tool`, so the whole loop can be
tested offline with fakes (see tests/test_agent.py).
"""
import asyncio

import llm

MAX_STEPS = 6
MAX_TURNS = 6  # whole conversation turns kept per session

SYSTEM = (
    "You are StudyBuddy, a voice study partner running on Alexa+. Replies are spoken aloud, so use "
    "one to three short plain sentences: no markdown, no lists, no emojis. Use the tools for "
    "anything involving the learner's cards, tasks, plans or progress; never invent their data. "
    "To quiz: call quiz_me and read the question aloud; never reveal the answer first. Remember the "
    "question_id. When the learner then answers, call check_answer with that question_id and their "
    "words, and tell them if they were right (say the correct answer if wrong). If the learner "
    "pastes notes or asks for flashcards from text, call generate_flashcards_from_notes. If they "
    "mention where they live, call set_timezone with an IANA name. Use each tool result's 'speech' "
    "field as the basis for what you say. If a tool returns an error, explain it simply."
)


def to_bedrock_tools(mcp_tools) -> list[dict]:
    """MCP tool list -> Bedrock Converse toolConfig.tools."""
    return [
        {"toolSpec": {"name": t.name, "description": (t.description or t.name)[:1000],
                      "inputSchema": {"json": t.inputSchema}}}
        for t in mcp_tools
    ]


async def run_turn(text: str, tools: list, call_tool, history: list, converse=None, max_steps: int = MAX_STEPS):
    """Run one user utterance. Returns (spoken_reply, trace).

    history: list of past turns (each a list of Bedrock messages), mutated in place.
    call_tool: async (name, args) -> dict.
    """
    converse = converse or llm.converse
    user_msg = {"role": "user", "content": [{"text": text}]}
    turn = [user_msg]
    trace: list[dict] = []
    say = ""
    for _ in range(max_steps):
        messages = [m for past in history for m in past] + turn
        resp = await asyncio.to_thread(converse, messages, SYSTEM, tools)
        out = resp["output"]["message"]
        turn.append(out)
        if resp.get("stopReason") != "tool_use":
            say = llm.text_of(resp)
            break
        results = []
        for block in out["content"]:
            if "toolUse" not in block:
                continue
            tu = block["toolUse"]
            try:
                data, status = await call_tool(tu["name"], tu.get("input") or {}), "success"
            except Exception as exc:  # tool failures go back to the model, not to the user as a crash
                data, status = {"error": str(exc)}, "error"
            trace.append({"tool": tu["name"], "args": tu.get("input") or {}, "result": data})
            results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": data}], "status": status}})
        turn.append({"role": "user", "content": results})
    else:
        say = "Sorry, that took too many steps. Could you try again?"
        turn.append({"role": "assistant", "content": [{"text": say}]})  # keep roles alternating
    say = say or "Sorry, I didn't catch that."
    if turn[-1]["role"] == "assistant" and not any("text" in b for b in turn[-1]["content"]):
        turn[-1]["content"].append({"text": say})
    history.append(turn)
    del history[:-MAX_TURNS]
    return say, trace
