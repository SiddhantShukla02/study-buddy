"""Calls the StudyBuddy MCP server over Streamable HTTP, like an Alexa+ client would.

Usage:  python server.py   (in one terminal)
        python demo_client.py [http://localhost:8000/mcp]
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ANSWERS = {"derivative": "2x", "7 times 8": "56", "square root": "12"}
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"


def show(label, result):
    text = result.content[0].text if result.content else ""
    print(f"\n> {label}\n{text}")


async def main():
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Connected. Protocol version: {init.protocolVersion}")
            tools = await session.list_tools()
            print("Tools:", ", ".join(t.name for t in tools.tools))

            q = await session.call_tool("quiz_me", {"subject": "math"})
            show("quiz_me(subject='math')", q)
            data = json.loads(q.content[0].text)
            guess = next(a for k, a in ANSWERS.items() if k in data["question"].lower())
            show(f"check_answer(answer={guess!r})", await session.call_tool(
                "check_answer", {"question_id": data["question_id"], "answer": guess}))
            show("plan_revision('biology', days=3)", await session.call_tool(
                "plan_revision", {"subject": "biology", "days": 3}))
            show("list_study_tasks()", await session.call_tool("list_study_tasks", {}))


asyncio.run(main())
