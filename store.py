"""Storage and study logic for StudyBuddy. Standard library only (sqlite3).

Every function takes the database connection and a user id, so each caller sees only
its own cards, tasks and history. Functions accept an optional `today` so that
spaced-repetition and streak behaviour can be tested without waiting for real days.

Spaced repetition uses a simple Leitner scheme. Each card sits in a box from 1 to 5.
A correct answer moves it up one box (reviewed less often); a miss sends it back to
box 1 and keeps it due today, so it returns in the same session until you get it right.
"""
import sqlite3
from datetime import date, timedelta

from grading import grade

INTERVALS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}  # box -> days until the next review
MAX_BOX = max(INTERVALS)

BUILTIN_CARDS = {
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

REVISION_PHASES = [
    "Read notes and mark weak spots",
    "Practice questions",
    "Teach it back aloud",
    "Mock quiz",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards(
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user    TEXT NOT NULL,
  subject TEXT NOT NULL,
  front   TEXT NOT NULL,
  back    TEXT NOT NULL,
  box     INTEGER NOT NULL DEFAULT 1,
  due     TEXT NOT NULL,
  seen    INTEGER NOT NULL DEFAULT 0,
  missed  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cards_user_due ON cards(user, due);
CREATE TABLE IF NOT EXISTS tasks(
  user    TEXT NOT NULL,
  num     INTEGER NOT NULL,
  title   TEXT NOT NULL,
  subject TEXT NOT NULL,
  due     TEXT NOT NULL,
  done    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user, num)
);
CREATE TABLE IF NOT EXISTS reviews(
  user TEXT NOT NULL,
  day  TEXT NOT NULL,
  ok   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_user_day ON reviews(user, day);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Open (and create, if needed) the database. Use ':memory:' for tests."""
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def _today(today: date | None) -> date:
    return today or date.today()


# ------------------------------------------------------------------ cards
def seed(db: sqlite3.Connection, user: str, today: date | None = None) -> None:
    """Give a new user the built-in cards, once."""
    if db.execute("SELECT 1 FROM cards WHERE user=? LIMIT 1", (user,)).fetchone():
        return
    due = _today(today).isoformat()
    db.executemany(
        "INSERT INTO cards(user, subject, front, back, due) VALUES (?,?,?,?,?)",
        [(user, subj, q, a, due) for subj, qs in BUILTIN_CARDS.items() for q, a in qs],
    )
    db.commit()


def add_card(db, user, front, back, subject="general", today=None) -> dict:
    front, back = front.strip(), back.strip()
    if not front or not back:
        return {"error": "A flashcard needs both a question and an answer."}
    seed(db, user, today)
    cur = db.execute(
        "INSERT INTO cards(user, subject, front, back, due) VALUES (?,?,?,?,?)",
        (user, subject.strip().lower() or "general", front, back, _today(today).isoformat()),
    )
    db.commit()
    return {"card_id": cur.lastrowid, "subject": subject.strip().lower() or "general"}


def subjects(db, user) -> list[str]:
    rows = db.execute("SELECT DISTINCT subject FROM cards WHERE user=? ORDER BY subject", (user,))
    return [r["subject"] for r in rows]


def next_question(db, user, subject="", today=None) -> dict:
    """Pick one due card. Often-missed and low-box cards come first."""
    seed(db, user, today)
    subject = subject.strip().lower()
    if subject and subject not in subjects(db, user):
        return {"error": f"I don't have cards for {subject}. I have: {', '.join(subjects(db, user))}."}
    sql = "SELECT * FROM cards WHERE user=? AND due<=?"
    args: list = [user, _today(today).isoformat()]
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    row = db.execute(sql + " ORDER BY missed DESC, box ASC, RANDOM() LIMIT 1", args).fetchone()
    if row is None:
        return {"message": "Nothing is due right now. You're all caught up. Come back tomorrow."}
    return {"question_id": str(row["id"]), "subject": row["subject"], "question": row["front"]}


def check_answer(db, user, question_id, answer, today=None) -> dict:
    """Grade an answer, move the card between boxes and log the review."""
    try:
        card_id = int(question_id)
    except (TypeError, ValueError):
        return {"error": "That question doesn't exist. Ask for a new quiz."}
    card = db.execute("SELECT * FROM cards WHERE id=? AND user=?", (card_id, user)).fetchone()
    if card is None:
        return {"error": "That question doesn't exist. Ask for a new quiz."}
    day = _today(today)
    ok = grade(answer, card["back"])
    box = min(card["box"] + 1, MAX_BOX) if ok else 1
    # A miss stays due today, so it comes straight back in the same session.
    days = INTERVALS[box] if ok else 0
    due = (day + timedelta(days=days)).isoformat()
    db.execute(
        "UPDATE cards SET box=?, due=?, seen=seen+1, missed=missed+? WHERE id=?",
        (box, due, 0 if ok else 1, card_id),
    )
    db.execute("INSERT INTO reviews(user, day, ok) VALUES (?,?,?)", (user, day.isoformat(), int(ok)))
    db.commit()
    return {
        "correct": ok,
        "right_answer": card["back"],
        "box": box,
        "next_review_in_days": days,
    }


# ------------------------------------------------------------------ tasks
def add_task(db, user, title, subject="general", due_in_days=1, today=None) -> dict:
    title = title.strip()
    if not title:
        return {"error": "A task needs a title."}
    num = db.execute("SELECT COALESCE(MAX(num), 0) + 1 FROM tasks WHERE user=?", (user,)).fetchone()[0]
    due = (_today(today) + timedelta(days=due_in_days)).isoformat()
    subject = subject.strip().lower() or "general"
    db.execute(
        "INSERT INTO tasks(user, num, title, subject, due) VALUES (?,?,?,?,?)",
        (user, num, title, subject, due),
    )
    db.commit()
    return {"id": num, "title": title, "subject": subject, "due": due, "done": False}


def _task_dict(row) -> dict:
    return {"id": row["num"], "title": row["title"], "subject": row["subject"],
            "due": row["due"], "done": bool(row["done"])}


def list_tasks(db, user, include_done=False) -> list[dict]:
    sql = "SELECT * FROM tasks WHERE user=?" + ("" if include_done else " AND done=0")
    return [_task_dict(r) for r in db.execute(sql + " ORDER BY due, num", (user,))]


def complete_task(db, user, task_id) -> dict:
    cur = db.execute("UPDATE tasks SET done=1 WHERE user=? AND num=?", (user, task_id))
    db.commit()
    if cur.rowcount == 0:
        return {"error": f"No task with id {task_id}"}
    return _task_dict(db.execute("SELECT * FROM tasks WHERE user=? AND num=?", (user, task_id)).fetchone())


def plan_revision(db, user, subject, days=3, minutes_per_day=45, today=None) -> dict:
    """Build a day-by-day plan and save each day as a task."""
    days = max(1, min(int(days), 14))
    minutes = max(5, min(int(minutes_per_day), 240))
    subject = subject.strip().lower() or "general"
    plan = []
    for d in range(days):
        phase = REVISION_PHASES[min(d * len(REVISION_PHASES) // days, len(REVISION_PHASES) - 1)]
        add_task(db, user, f"{subject}: {phase} ({minutes} min)", subject, d + 1, today)
        plan.append({"day": d + 1, "focus": phase, "minutes": minutes})
    return {"subject": subject, "plan": plan}


# ------------------------------------------------------------------ progress
def summary(db, user, today=None) -> dict:
    """Streak, accuracy, cards due and weakest subjects."""
    seed(db, user, today)
    day = _today(today)
    days_with_reviews = {r["day"] for r in db.execute("SELECT DISTINCT day FROM reviews WHERE user=?", (user,))}
    # A streak stays alive until the end of the day after your last review.
    cursor = day if day.isoformat() in days_with_reviews else day - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days_with_reviews:
        streak += 1
        cursor -= timedelta(days=1)
    totals = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(ok), 0) AS n_ok FROM reviews WHERE user=?", (user,)
    ).fetchone()
    weakest = [
        r["subject"]
        for r in db.execute(
            "SELECT subject FROM cards WHERE user=? AND seen>0 GROUP BY subject "
            "HAVING SUM(missed)>0 ORDER BY SUM(missed)*1.0/SUM(seen) DESC, subject LIMIT 2",
            (user,),
        )
    ]
    counts = db.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(due<=?), 0) AS due FROM cards WHERE user=?",
        (day.isoformat(), user),
    ).fetchone()
    return {
        "streak_days": streak,
        "answered": totals["n"],
        "accuracy": round(totals["n_ok"] / totals["n"], 2) if totals["n"] else None,
        "weakest_subjects": weakest,
        "cards_total": counts["total"],
        "cards_due": counts["due"],
    }
