# Submission text (copy into Devpost)

**Track:** Alexa+ (self-hosted MCP server)
**Pre-existing work:** None. Everything was built during the submission window.

## What it does
StudyBuddy turns a voice assistant into a study partner. A student can say "quiz me on math",
answer out loud and get graded, ask for "a 4-day plan for biology", add tasks like "read chapter 5",
and ask what's left on their list. Revision plans are saved automatically as dated tasks.

## How it works
StudyBuddy is an MCP server written in Python with the official MCP SDK. It exposes six tools
(quiz_me, check_answer, plan_revision, add_study_task, list_study_tasks, complete_study_task) over
Streamable HTTP at `/mcp`, negotiating protocol version 2025-11-25. An MCP client such as Alexa+
discovers the tools and calls them from natural language. The repo also includes a browser
simulator of an Alexa+ chat that shows each tool call live, and `demo_client.py`, a script that
exercises the server over real MCP HTTP.

## Product feedback (edit with your own experience)
**MCP Python SDK** (used to build the server and client)
- Used for: server, tool definitions, Streamable HTTP transport, test client.
- Worked well: decorator-based tools were quick to write; the server negotiated 2025-11-25 immediately.
- Needs work: v2 renamed `FastMCP`, so a plain install broke the common example code; `call_tool` returns
  different shapes depending on the tool.
- Onboarding: fast once the version was pinned.
- Build again: yes.
