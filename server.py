"""StudyBuddy: an MCP server (Streamable HTTP) plus a simulated Alexa+ chat page.

Run:  python server.py        -> MCP endpoint http://localhost:8000/mcp
                              -> Simulator    http://localhost:8000/
"""
import json
import random
import re
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

mcp = FastMCP(
    "StudyBuddy",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
    json_response=True,
    # Relax DNS-rebinding checks so a tunnel (ngrok, cloudflared) can reach it.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# ---------------------------------------------------------------- data
QUIZ = {
    "biology": [
        ("Which organelle produces most of a cell's ATP?", "mitochondria"),
        ("What molecule carries genetic information?", "dna"),
        ("What process do plants use to make glucose from light?", "photosynthesis"),
    ],
    "math": [
        ("What is the derivative of x squared?", "2x"),
        ("What is the value of 7 times 8?", "56"),
        ("What is the square root of 144?", "12"),
    ],
    "history": [
        ("In which year did India gain independence?", "1947"),
        ("Who was the first Prime Minister of India?", "nehru"),
        ("Which empire built the Taj Mahal?", "mughal"),
    ],
}
TASKS: list[dict] = []
PENDING: dict[str, tuple[str, str]] = {}  # question_id -> (question, answer)
SCORE = {"right": 0, "wrong": 0}


# ---------------------------------------------------------------- tools
@mcp.tool()
def add_study_task(title: str, subject: str = "general", due_in_days: int = 1) -> dict:
    """Add a study task, e.g. 'revise chapter 4' for biology due in 2 days."""
    task = {
        "id": len(TASKS) + 1,
        "title": title,
        "subject": subject.lower(),
        "due": (date.today() + timedelta(days=due_in_days)).isoformat(),
        "done": False,
    }
    TASKS.append(task)
    return task


@mcp.tool()
def list_study_tasks(include_done: bool = False) -> list[dict]:
    """List study tasks, soonest due first."""
    items = [t for t in TASKS if include_done or not t["done"]]
    return sorted(items, key=lambda t: t["due"])


@mcp.tool()
def complete_study_task(task_id: int) -> dict:
    """Mark a study task as done."""
    for t in TASKS:
        if t["id"] == task_id:
            t["done"] = True
            return t
    return {"error": f"No task with id {task_id}"}


@mcp.tool()
def quiz_me(subject: str = "biology") -> dict:
    """Ask one quiz question. Subjects: biology, math, history."""
    subject = subject.lower()
    if subject not in QUIZ:
        return {"error": f"I only have {', '.join(QUIZ)} quizzes right now."}
    q, a = random.choice(QUIZ[subject])
    qid = f"q{random.randint(1000, 9999)}"
    PENDING[qid] = (q, a)
    return {"question_id": qid, "subject": subject, "question": q}


@mcp.tool()
def check_answer(question_id: str, answer: str) -> dict:
    """Check the learner's answer to a quiz question."""
    if question_id not in PENDING:
        return {"error": "That question has expired. Ask for a new quiz."}
    q, correct = PENDING.pop(question_id)
    ok = correct in answer.lower().replace(" ", "")
    SCORE["right" if ok else "wrong"] += 1
    return {"correct": ok, "right_answer": correct, "score": dict(SCORE)}


@mcp.tool()
def plan_revision(subject: str, days: int = 3, minutes_per_day: int = 45) -> dict:
    """Build a day-by-day revision plan and save each day as a task."""
    days = max(1, min(days, 14))
    phases = ["Read notes and mark weak spots", "Practice questions", "Teach it back aloud", "Mock quiz"]
    plan = []
    for d in range(days):
        phase = phases[min(d * len(phases) // days, len(phases) - 1)]
        add_study_task(f"{subject}: {phase} ({minutes_per_day} min)", subject, d + 1)
        plan.append({"day": d + 1, "focus": phase, "minutes": minutes_per_day})
    return {"subject": subject, "plan": plan}


# ---------------------------------------------------------------- simulator
LAST_QID = {"id": None}


async def route_utterance(text: str) -> dict:
    """Tiny intent router standing in for Alexa+'s LLM: maps speech to MCP tool calls."""
    t = text.lower().strip()
    calls = []

    async def call(name, args):
        res = await mcp.call_tool(name, args)
        if isinstance(res, tuple):  # (content, structured) for list-returning tools
            data = res[1].get("result", res[1])
        else:  # list of TextContent holding JSON for dict-returning tools
            data = json.loads(res[0].text)
        calls.append({"tool": name, "args": args, "result": data})
        return data

    n = re.search(r"(\d+)", t)
    subj = next((s for s in QUIZ if s in t), None)

    if LAST_QID["id"] and not any(k in t for k in ("quiz", "plan", "add", "list", "done")):
        r = await call("check_answer", {"question_id": LAST_QID["id"], "answer": text})
        LAST_QID["id"] = None
        if r.get("correct"):
            say = f"Correct! That's {r['score']['right']} right so far. Say quiz me for another."
        else:
            say = f"Not quite. The answer was {r.get('right_answer', '?')}."
    elif "quiz" in t:
        r = await call("quiz_me", {"subject": subj or "biology"})
        LAST_QID["id"] = r.get("question_id")
        say = r.get("question") or r.get("error")
    elif "plan" in t or "revise" in t and "for" in t:
        s = subj or "biology"
        r = await call("plan_revision", {"subject": s, "days": int(n.group(1)) if n else 3})
        say = f"Done. I planned {len(r['plan'])} days of {s} revision and added them to your list."
    elif t.startswith(("add", "remind")):
        title = re.sub(r"^(add|remind me to)( a)?( study)?( task)?( to)?", "", t).strip() or t
        r = await call("add_study_task", {"title": title, "subject": subj or "general"})
        say = f"Added: {r['title']}, due {r['due']}."
    elif "done" in t or "finished" in t or "complete" in t:
        if not n:
            say = "Which task number did you finish?"
        else:
            r = await call("complete_study_task", {"task_id": int(n.group(1))})
            say = r.get("error") or f"Nice work. Marked task {r['id']} as done."
    elif any(k in t for k in ("list", "tasks", "plate", "what do i")):
        r = await call("list_study_tasks", {})
        say = (
            "You have " + str(len(r)) + " open: " + "; ".join(f"{x['id']}. {x['title']}" for x in r[:5])
            if r else "Nothing open. You're clear."
        )
    else:
        say = "Try: quiz me on math, plan 4 days for biology, add a task to read chapter 5, or what's on my list."
    return {"say": say, "calls": calls}


@mcp.custom_route("/api/utter", methods=["POST"])
async def utter(request: Request):
    body = await request.json()
    return JSONResponse(await route_utterance(body.get("text", "")))


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request):
    return HTMLResponse(PAGE)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StudyBuddy on Alexa+ (simulator)</title>
<style>
:root{--bg:#0e1621;--panel:#16212f;--line:#263548;--ink:#e8eef6;--dim:#8fa3b8;--ring:#27c3ff;--me:#1d3a57}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Segoe UI",system-ui,sans-serif;
display:grid;grid-template-columns:1fr 340px;height:100vh}
@media(max-width:800px){body{grid-template-columns:1fr;grid-template-rows:1fr 220px}}
main{display:flex;flex-direction:column;min-width:0}
header{display:flex;align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid var(--line)}
.ring{width:34px;height:34px;border-radius:50%;border:4px solid var(--ring);box-shadow:0 0 14px var(--ring);flex:none}
.ring.busy{animation:p 1s ease-in-out infinite}@keyframes p{50%{opacity:.35}}
@media(prefers-reduced-motion:reduce){.ring.busy{animation:none}}
h1{font-size:18px;margin:0;font-weight:600}header span{color:var(--dim);font-size:13px}
#log{flex:1;overflow:auto;padding:22px;display:flex;flex-direction:column;gap:12px}
.m{max-width:min(520px,85%);padding:10px 14px;border-radius:16px;white-space:pre-wrap}
.a{background:var(--panel);border:1px solid var(--line);align-self:flex-start;border-top-left-radius:4px}
.u{background:var(--me);align-self:flex-end;border-top-right-radius:4px}
.chips{display:flex;gap:8px;flex-wrap:wrap;padding:0 22px 10px}
.chips button{background:none;border:1px solid var(--line);color:var(--dim);border-radius:99px;padding:5px 12px;cursor:pointer;font:inherit;font-size:13px}
.chips button:hover,.chips button:focus-visible{border-color:var(--ring);color:var(--ink);outline:none}
form{display:flex;gap:10px;padding:14px 22px 22px;border-top:1px solid var(--line)}
input{flex:1;background:var(--panel);border:1px solid var(--line);color:var(--ink);border-radius:12px;padding:12px 14px;font:inherit}
input:focus-visible{outline:2px solid var(--ring)}
form button{background:var(--ring);color:#04202e;border:0;border-radius:12px;padding:0 20px;font:inherit;font-weight:600;cursor:pointer}
aside{border-left:1px solid var(--line);background:#0b121b;display:flex;flex-direction:column;min-height:0}
aside h2{font-size:14px;margin:0;padding:18px 18px 10px;color:var(--dim);font-weight:600}
#trace{flex:1;overflow:auto;padding:0 18px 18px;font:12px/1.5 ui-monospace,Menlo,monospace}
.t{border-left:3px solid var(--ring);padding:2px 0 2px 10px;margin-bottom:12px}
.t b{color:var(--ring)}.t pre{margin:4px 0 0;white-space:pre-wrap;word-break:break-word;color:var(--dim)}
.empty{color:var(--dim);font:14px/1.5 "Segoe UI",system-ui,sans-serif}
</style></head><body>
<main>
<header><div class="ring" id="ring"></div><div><h1>StudyBuddy</h1><span>Simulated Alexa+ skill. Talks to the MCP server at /mcp</span></div></header>
<div id="log"><div class="m a">Hi, I'm StudyBuddy. Ask for a quiz, a revision plan, or add a task.</div></div>
<div class="chips" id="chips"></div>
<form id="f"><input id="q" autocomplete="off" placeholder="Say something to Alexa..." aria-label="Message"><button>Send</button></form>
</main>
<aside><h2>MCP tool calls</h2><div id="trace"><p class="empty">Tool calls the server handles will appear here.</p></div></aside>
<script>
const log=document.getElementById('log'),trace=document.getElementById('trace'),ring=document.getElementById('ring');
const add=(c,t)=>{const d=document.createElement('div');d.className='m '+c;d.textContent=t;log.append(d);log.scrollTop=log.scrollHeight};
["Quiz me on biology","Plan 4 days for math","Add a task to read chapter 5","What's on my list?"].forEach(s=>{
 const b=document.createElement('button');b.type='button';b.textContent=s;b.onclick=()=>send(s);chips.append(b)});
async function send(text){
 if(!text.trim())return;add('u',text);ring.classList.add('busy');
 try{
  const r=await fetch('/api/utter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  const j=await r.json();add('a',j.say);
  if(j.calls.length&&trace.querySelector('.empty'))trace.innerHTML='';
  j.calls.forEach(c=>{const d=document.createElement('div');d.className='t';
   d.innerHTML='<b></b><pre></pre>';d.querySelector('b').textContent=c.tool+'('+Object.entries(c.args).map(([k,v])=>k+'='+JSON.stringify(v)).join(', ')+')';
   d.querySelector('pre').textContent=JSON.stringify(c.result,null,1);trace.append(d);trace.scrollTop=trace.scrollHeight});
 }catch(e){add('a','Could not reach the server. Is it still running?')}
 ring.classList.remove('busy')}
f.onsubmit=e=>{e.preventDefault();const v=q.value;q.value='';send(v)};
</script></body></html>"""

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
