# StudyBuddy: an MCP server for Alexa+

StudyBuddy lets a voice assistant be a study partner. It quizzes a student with **spaced
repetition**, turns the student's own notes into flashcards, builds revision plans, tracks study
tasks and reports progress. Every learner's data is kept separate.

It is a self-hosted **MCP server** (spec 2025-11-25, Streamable HTTP) built with the official
Python SDK, plus a browser simulator of an Alexa+ conversation.

## Requirements

- Python 3.10 or newer
- Git (to clone the repo)

## Run it

Clone the repo first:

```bash
git clone https://github.com/SiddhantShukla02/study-buddy.git
cd study-buddy
```

Then pick **one** of the two ways to install and run.

### Option A: pip (no extra tools needed)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

### Option B: Poetry

```bash
poetry install --no-root
poetry run python server.py
```

Once the server is running:

- MCP endpoint: `http://localhost:8000/mcp`
- Alexa+ simulator: `http://localhost:8000/` (chat on the left, live MCP tool calls on the right)

### Configuration (all optional)

| Variable | Default | Meaning |
|----------|---------|---------|
| `PORT` | `8000` | Port to listen on |
| `STUDYBUDDY_DB` | `studybuddy.db` | SQLite file. Use `:memory:` for throwaway data |

On hosts with an ephemeral disk, data resets on every redeploy unless `STUDYBUDDY_DB` points at a
persistent volume.

## See the real MCP protocol in action

With the server running, open a second terminal in the same folder (and activate the
virtual environment again if you used Option A):

```bash
python demo_client.py          # Poetry: poetry run python demo_client.py
python demo_client.py https://your-host/mcp   # against a hosted server
```

This connects over Streamable HTTP as a fresh learner, prints the negotiated protocol version,
lists the tools, saves a flashcard, misses a question (which comes straight back), builds a
plan, prints a progress summary, and finally connects as a second learner to show their data
is separate.

## Tools

| Tool | What it does |
|------|--------------|
| `quiz_me(subject?)` | Asks one due question; often-missed cards come first. Subject is optional |
| `check_answer(question_id, answer)` | Grades the answer (typo and filler-word tolerant) and schedules the next review |
| `add_flashcard(front, back, subject)` | Saves a flashcard from the learner's own notes |
| `study_summary()` | Streak, accuracy, cards due and weakest subjects |
| `plan_revision(subject, days, minutes_per_day)` | Builds a day-by-day plan and saves each day as a task |
| `add_study_task(title, subject, due_in_days)` | Adds a task |
| `list_study_tasks(include_done)` | Lists open tasks, soonest first |
| `complete_study_task(task_id)` | Marks a task done |

### How the learning works

Each card sits in a Leitner box from 1 to 5. A correct answer moves it up a box, so it returns
after 1, 2, 4, 8 or 16 days. A miss sends it back to box 1 and keeps it due today, so it returns
in the same session until it sticks.

### Who is the learner?

The server identifies a learner from the `Authorization` header, or `X-User-Id` if there is none.
The value is hashed before use. Requests with neither share one default learner.

## Project layout

| File | Purpose |
|------|---------|
| `server.py` | MCP server: tool definitions, simulator route, startup |
| `store.py` | SQLite storage and all study logic (standard library only) |
| `grading.py` | Answer grading (standard library only) |
| `simulator.html` | The Alexa+ simulator page |
| `demo_client.py` | Real MCP client that exercises the server over HTTP |
| `tests/` | Automated tests |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

`tests/test_grading.py` and `tests/test_store.py` need nothing but the standard library.
`tests/test_server.py` checks the MCP wiring and the simulator and needs the `mcp` package.

## Notes and limits

- The simulator's intent router is keyword-based. It stands in for Alexa+'s language model.
- Learners are told apart by request header only. There is no login, so do not store anything sensitive.
- The `mcp` package is pinned to `>=1.23,<2`, because version 2 renamed `FastMCP` and would break the imports.
- To reach the server from another machine, expose port 8000 with a tunnel such as cloudflared or ngrok.

## License

MIT, see `LICENSE`.
