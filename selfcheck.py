"""End-to-end check against a RUNNING server. Prints PASS/FAIL per check and exits non-zero on failure.

Usage:  python server.py                       (terminal 1)
        python selfcheck.py [http://localhost:8000]   (terminal 2)

It talks real MCP over Streamable HTTP, then exercises the simulator endpoint with two sessions.
Use it before recording your demo and again against your deployed URL.
"""
import asyncio
import json
import sys
import urllib.request
import uuid

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
FAILS = []


def check(label, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(label)


def http(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def data_of(res):
    return res.structuredContent or json.loads(res.content[0].text)


async def main():
    health = http("/api/health")
    print(f"Server: tools={health['tools']} agent={health['agent']} model={health['model']} require_auth={health['require_auth']}")
    check("health endpoint says 10 tools", health["tools"] == 10, health)

    user_a, user_b = f"check-{uuid.uuid4().hex[:8]}", f"check-{uuid.uuid4().hex[:8]}"
    async with streamablehttp_client(BASE + "/mcp", headers={"X-User-Id": user_a, "X-Timezone": "Asia/Kolkata"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print(f"Negotiated MCP protocol version: {init.protocolVersion}")
            check("protocol version is 2025-11-25 or newer", init.protocolVersion >= "2025-11-25", init.protocolVersion)
            tools = (await s.list_tools()).tools
            check("10 tools listed", len(tools) == 10, [t.name for t in tools])
            check("tools have titles and annotations", all(t.title and t.annotations for t in tools))

            q = data_of(await s.call_tool("quiz_me", {"subject": "math"}))
            check("quiz_me returns a question and speech", "question_id" in q and q["speech"], q)
            miss = data_of(await s.call_tool("check_answer", {"question_id": q["question_id"], "answer": "banana"}))
            check("wrong answer is marked wrong", miss["correct"] is False, miss)
            again = data_of(await s.call_tool("quiz_me", {"subject": "math"}))
            check("missed card comes straight back", again["question_id"] == q["question_id"], again)
            spoken = data_of(await s.call_tool("check_answer", {"question_id": "0", "answer": "x"}))
            check("bad question id gives an error, not a crash", "error" in spoken, spoken)

            gen = data_of(await s.call_tool("generate_flashcards_from_notes",
                                            {"notes": "Osmosis is the movement of water across a membrane.", "subject": "biology"}))
            check(f"flashcards from notes (source={gen.get('source')})", gen.get("added", 0) >= 1, gen)
            tz = data_of(await s.call_tool("set_timezone", {"timezone": "Asia/Kolkata"}))
            check("set_timezone works", tz.get("timezone") == "Asia/Kolkata", tz)
            plan = data_of(await s.call_tool("plan_revision", {"subject": "biology", "days": 3}))
            tasks = data_of(await s.call_tool("list_study_tasks", {}))
            check("plan saved as 3 tasks", len(plan["plan"]) == 3 and tasks["count"] == 3, tasks)

    async with streamablehttp_client(BASE + "/mcp", headers={"X-User-Id": user_b}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            other = data_of(await s.call_tool("list_study_tasks", {}))
            check("a second learner sees none of the first learner's tasks", other["count"] == 0, other)

    # Simulator endpoint, two independent browser sessions.
    s1, s2 = f"sim{uuid.uuid4().hex[:6]}", f"sim{uuid.uuid4().hex[:6]}"
    a = http("/api/utter", {"text": "quiz me on math", "session": s1, "tz": "Asia/Kolkata"})
    print(f"Simulator mode: {a.get('mode')}" + (f"  note: {a['note']}" if a.get("note") else ""))
    check("simulator quiz goes through MCP", any(c["tool"] == "quiz_me" for c in a["calls"]), a)
    b = http("/api/utter", {"text": "how am I doing", "session": s2})
    check("a second simulator session is independent", any(c["tool"] == "study_summary" for c in b["calls"]), b)

    print("\n" + ("ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} CHECK(S) FAILED: " + "; ".join(FAILS)))
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
