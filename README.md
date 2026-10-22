# StudyBuddy: an MCP server for Alexa+

StudyBuddy lets a voice assistant quiz a student, build a revision plan, and track study tasks.
It is a self-hosted **MCP server** (spec 2025-11-25, Streamable HTTP) built with the official
Python SDK, plus a browser simulator of an Alexa+ conversation.

## Run it

```bash
pip install -r requirements.txt
python server.py
```

- MCP endpoint: `http://localhost:8000/mcp`
- Alexa+ simulator: `http://localhost:8000/` (chat on the left, live MCP tool calls on the right)

## See the real MCP protocol in action

With the server running, in a second terminal:

```bash
python demo_client.py
```

This connects over Streamable HTTP, prints the negotiated protocol version, lists the tools,
and calls them the way an Alexa+ client would.

## Tools

| Tool | What it does |
|------|--------------|
| `quiz_me(subject)` | Asks one question (biology, math, history) |
| `check_answer(question_id, answer)` | Grades the answer and keeps a score |
| `plan_revision(subject, days, minutes_per_day)` | Builds a day-by-day plan and saves each day as a task |
| `add_study_task(title, subject, due_in_days)` | Adds a task |
| `list_study_tasks()` | Lists open tasks, soonest first |
| `complete_study_task(task_id)` | Marks a task done |

## Notes and limits

- The simulator's intent router is keyword-based. It stands in for Alexa+'s language model.
- Data is stored in memory and resets on restart.
- To reach the server from another machine, expose port 8000 with a tunnel such as cloudflared or ngrok.

## License

MIT, see `LICENSE`.
