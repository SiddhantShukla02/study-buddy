"""Calls the StudyBuddy MCP server over Streamable HTTP, like an Alexa+ client would.

Usage:  python server.py   (in one terminal)
        python demo_client.py [http://localhost:8000/mcp]

Each run uses a fresh X-User-Id, so it always starts from a clean slate, and a second
user at the end shows that learners never see each other's data.
"""
import asyncio
import json
import sys
import uuid

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ANSWERS = {"derivative": "2x", "7 times 8": "56", "square root": "12"}
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"


def show(label, result):
    text = result.content[0].text if result.content else ""
    print(f"\n> {label}\n{text}")


async def main():
    user_a = f"demo-{uuid.uuid4().hex[:8]}"
    user_b = f"demo-{uuid.uuid4().hex[:8]}"

    async with streamablehttp_client(URL, headers={"X-User-Id": user_a}) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Connected as {user_a}. Protocol version: {init.protocolVersion}")
            tools = await session.list_tools()
            print("Tools:", ", ".join(t.name for t in tools.tools))

            show("add_flashcard('What is mitosis?', 'cell division')", await session.call_tool(
                "add_flashcard", {"front": "What is mitosis?", "back": "cell division", "subject": "biology"}))

            q = await session.call_tool("quiz_me", {"subject": "math"})
            show("quiz_me(subject='math')", q)
            data = json.loads(q.content[0].text)
            show("check_answer(wrong answer 'banana')", await session.call_tool(
                "check_answer", {"question_id": data["question_id"], "answer": "banana"}))

            # The missed card is prioritised, so the same question comes straight back.
            q2 = await session.call_tool("quiz_me", {"subject": "math"})
            show("quiz_me(subject='math') again: the missed card returns first", q2)
            data2 = json.loads(q2.content[0].text)
            guess = next(a for k, a in ANSWERS.items() if k in data2["question"].lower())
            show(f"check_answer(answer={guess!r})", await session.call_tool(
                "check_answer", {"question_id": data2["question_id"], "answer": guess}))
            show("plan_revision('biology', days=3)", await session.call_tool(
                "plan_revision", {"subject": "biology", "days": 3}))
            show("list_study_tasks()", await session.call_tool("list_study_tasks", {}))
            show("study_summary()", await session.call_tool("study_summary", {}))

    async with streamablehttp_client(URL, headers={"X-User-Id": user_b}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"\nNow connected as a different learner ({user_b}).")
            show("list_study_tasks() as the second learner (should be empty)", await session.call_tool(
                "list_study_tasks", {}))


asyncio.run(main())
