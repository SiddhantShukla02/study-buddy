# Submission text (copy into Devpost)

**Track:** Alexa+ (self-hosted MCP server)
**Pre-existing work:** None. Everything was built during the submission window.

## What it does
StudyBuddy turns a voice assistant into a study partner that remembers what you get wrong. A student
can say "quiz me on math", answer out loud and get graded, and any question they miss comes straight
back until it sticks, then returns days later on a spaced-repetition schedule. They can say "remember
that mitosis is cell division" to turn their own notes into flashcards, ask for "a 4-day plan for
biology", add tasks like "read chapter 5", and ask "how am I doing" to hear their streak, accuracy and
weakest subjects. Every learner's cards, tasks and history are kept separate.

## How it works
StudyBuddy is an MCP server written in Python with the official MCP SDK. It exposes eight tools
(quiz_me, check_answer, add_flashcard, study_summary, plan_revision, add_study_task, list_study_tasks,
complete_study_task) over Streamable HTTP at `/mcp`, negotiating protocol version 2025-11-25. An MCP
client such as Alexa+ discovers the tools and calls them from natural language. Study logic lives in
plain-Python modules backed by SQLite: a Leitner-box scheduler, a grader that tolerates typos and
filler words but never accepts near-miss numbers, and per-learner isolation keyed on the request
header. The repo also includes a browser simulator of an Alexa+ chat that shows each tool call live,
`demo_client.py`, a script that exercises the server over real MCP HTTP (including a second learner
to prove isolation), and an automated test suite.

## Product feedback (edit with your own experience)
**MCP Python SDK** (used to build the server and client)
- Used for: server, tool definitions, Streamable HTTP transport, test client.
- Worked well: decorator-based tools were quick to write; the server negotiated 2025-11-25 immediately.
- Needs work: v2 renamed `FastMCP`, so a plain install broke the common example code; `call_tool` returns
  different shapes depending on the tool.
- Onboarding: fast once the version was pinned.
- Build again: yes.
