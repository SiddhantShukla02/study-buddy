"""Unit tests for store.py using an in-memory SQLite database. Standard library only."""
from datetime import date, timedelta

import store

D0 = date(2026, 10, 23)


def fresh():
    return store.connect(":memory:")


def card_row(db, user, card_id):
    return db.execute("SELECT * FROM cards WHERE id=? AND user=?", (card_id, user)).fetchone()


def find_question(db, user, subject, wanted_answer, today=D0):
    """Return the id of the built-in card whose answer is wanted_answer."""
    store.seed(db, user, today)
    return db.execute("SELECT id FROM cards WHERE user=? AND subject=? AND back=?",
                      (user, subject, wanted_answer)).fetchone()["id"]


# ---------------------------------------------------------------- seeding & isolation
def test_seed_adds_nine_builtin_cards_once():
    db = fresh()
    store.seed(db, "a", D0)
    store.seed(db, "a", D0)
    n = db.execute("SELECT COUNT(*) FROM cards WHERE user='a'").fetchone()[0]
    assert n == 9
    assert store.subjects(db, "a") == ["biology", "history", "math"]


def test_users_do_not_see_each_others_data():
    db = fresh()
    store.add_task(db, "a", "revise optics", today=D0)
    store.add_card(db, "a", "What is a lens?", "glass that bends light", "physics", today=D0)
    assert store.list_tasks(db, "b") == []
    assert "physics" not in store.subjects(db, "b")  # b is seeded fresh, without a's card
    assert store.complete_task(db, "b", 1).get("error")  # b has no task 1


def test_task_numbers_restart_per_user():
    db = fresh()
    assert store.add_task(db, "a", "one", today=D0)["id"] == 1
    assert store.add_task(db, "a", "two", today=D0)["id"] == 2
    assert store.add_task(db, "b", "other", today=D0)["id"] == 1


# ---------------------------------------------------------------- tasks
def test_add_task_validates_and_normalises():
    db = fresh()
    assert store.add_task(db, "a", "   ", today=D0).get("error")
    t = store.add_task(db, "a", " Read chapter 5 ", "Biology", 2, today=D0)
    assert t == {"id": 1, "title": "Read chapter 5", "subject": "biology",
                 "due": (D0 + timedelta(days=2)).isoformat(), "done": False}


def test_list_tasks_sorted_by_due_and_hides_done():
    db = fresh()
    store.add_task(db, "a", "later", due_in_days=5, today=D0)
    store.add_task(db, "a", "soon", due_in_days=1, today=D0)
    store.add_task(db, "a", "middle", due_in_days=3, today=D0)
    assert [t["title"] for t in store.list_tasks(db, "a")] == ["soon", "middle", "later"]
    done = store.complete_task(db, "a", 2)
    assert done["done"] is True and done["title"] == "soon"
    assert [t["title"] for t in store.list_tasks(db, "a")] == ["middle", "later"]
    assert len(store.list_tasks(db, "a", include_done=True)) == 3


def test_complete_unknown_task_is_an_error():
    db = fresh()
    assert store.complete_task(db, "a", 99) == {"error": "No task with id 99"}


def test_plan_revision_creates_dated_tasks_and_clamps_days():
    db = fresh()
    r = store.plan_revision(db, "a", "Biology", days=4, minutes_per_day=30, today=D0)
    assert [p["focus"] for p in r["plan"]] == store.REVISION_PHASES
    tasks = store.list_tasks(db, "a")
    assert len(tasks) == 4
    assert tasks[0]["due"] == (D0 + timedelta(days=1)).isoformat()
    assert tasks[3]["due"] == (D0 + timedelta(days=4)).isoformat()
    assert all("(30 min)" in t["title"] for t in tasks)
    assert len(store.plan_revision(db, "b", "math", days=0, today=D0)["plan"]) == 1
    assert len(store.plan_revision(db, "c", "math", days=99, today=D0)["plan"]) == 14
    assert store.plan_revision(db, "d", "math", minutes_per_day=1, today=D0)["plan"][0]["minutes"] == 5


# ---------------------------------------------------------------- flashcards
def test_add_card_validates_input():
    db = fresh()
    assert store.add_card(db, "a", "", "x", today=D0).get("error")
    assert store.add_card(db, "a", "x", "  ", today=D0).get("error")
    r = store.add_card(db, "a", "What is mitosis?", "cell division", "Biology", today=D0)
    assert r["subject"] == "biology" and isinstance(r["card_id"], int)


def test_custom_card_can_be_quizzed_and_graded():
    db = fresh()
    cid = store.add_card(db, "a", "What is mitosis?", "cell division", "notes", today=D0)["card_id"]
    q = store.next_question(db, "a", "notes", today=D0)
    assert q["question_id"] == str(cid) and q["question"] == "What is mitosis?"
    assert store.check_answer(db, "a", q["question_id"], "it is cell division", today=D0)["correct"] is True


def test_next_question_unknown_subject_lists_options():
    db = fresh()
    r = store.next_question(db, "a", "chemistry", today=D0)
    assert "chemistry" in r["error"] and "biology" in r["error"]


def test_next_question_respects_subject_filter():
    db = fresh()
    for _ in range(15):
        assert store.next_question(db, "a", "history", today=D0)["subject"] == "history"


def test_next_question_without_subject_uses_any_subject():
    db = fresh()
    seen = {store.next_question(db, "a", "", today=D0)["subject"] for _ in range(60)}
    assert seen <= {"biology", "math", "history"} and len(seen) >= 2


# ---------------------------------------------------------------- spaced repetition
def test_correct_answer_moves_up_a_box_and_schedules_review():
    db = fresh()
    cid = find_question(db, "a", "math", "56")
    r = store.check_answer(db, "a", str(cid), "it's 56", today=D0)
    assert r == {"correct": True, "right_answer": "56", "box": 2, "next_review_in_days": 2}
    row = card_row(db, "a", cid)
    assert row["box"] == 2 and row["due"] == (D0 + timedelta(days=2)).isoformat()
    assert row["seen"] == 1 and row["missed"] == 0


def test_answered_cards_return_only_after_their_interval():
    db = fresh()
    for answer in ("2x", "56", "12"):  # answer every math card correctly -> all move to box 2, due in 2 days
        cid = find_question(db, "a", "math", answer)
        assert store.check_answer(db, "a", str(cid), answer, today=D0)["correct"] is True
    assert "message" in store.next_question(db, "a", "math", today=D0)
    assert "message" in store.next_question(db, "a", "math", today=D0 + timedelta(days=1))
    assert "question_id" in store.next_question(db, "a", "math", today=D0 + timedelta(days=2))


def test_wrong_answer_resets_box_stays_due_and_returns_first():
    db = fresh()
    cid = find_question(db, "a", "math", "56")
    store.check_answer(db, "a", str(cid), "56", today=D0)               # box 2
    later = D0 + timedelta(days=2)
    r = store.check_answer(db, "a", str(cid), "banana", today=later)    # miss
    assert r["correct"] is False and r["box"] == 1 and r["next_review_in_days"] == 0
    row = card_row(db, "a", cid)
    assert row["missed"] == 1 and row["due"] == later.isoformat()
    for _ in range(25):  # missed cards are prioritised
        assert store.next_question(db, "a", "math", today=later)["question_id"] == str(cid)


def test_box_is_capped_at_five_with_sixteen_day_interval():
    db = fresh()
    cid = find_question(db, "a", "math", "56")
    day = D0
    r = None
    for _ in range(8):
        r = store.check_answer(db, "a", str(cid), "56", today=day)
        day += timedelta(days=20)
    assert r["box"] == 5 and r["next_review_in_days"] == 16


def test_check_answer_rejects_bad_ids_and_other_users_cards():
    db = fresh()
    cid = find_question(db, "a", "math", "56")
    store.seed(db, "b", D0)
    assert store.check_answer(db, "a", "abc", "56", today=D0).get("error")
    assert store.check_answer(db, "a", "999999", "56", today=D0).get("error")
    assert store.check_answer(db, "b", str(cid), "56", today=D0).get("error")  # a's card, asked by b
    assert card_row(db, "a", cid)["seen"] == 0  # untouched


def test_nothing_due_returns_a_friendly_message():
    db = fresh()
    store.seed(db, "a", D0)
    db.execute("UPDATE cards SET due=? WHERE user='a'", ((D0 + timedelta(days=30)).isoformat(),))
    db.commit()
    r = store.next_question(db, "a", "", today=D0)
    assert "message" in r and "question_id" not in r


# ---------------------------------------------------------------- summary
def answer_on(db, user, day, ok=True):
    cid = db.execute("SELECT id FROM cards WHERE user=? LIMIT 1", (user,)).fetchone()["id"]
    store.check_answer(db, user, str(cid), "wrong answer zzz" if not ok else
                       card_row(db, user, cid)["back"], today=day)


def test_summary_for_a_brand_new_user():
    db = fresh()
    s = store.summary(db, "a", D0)
    assert s == {"streak_days": 0, "answered": 0, "accuracy": None, "weakest_subjects": [],
                 "cards_total": 9, "cards_due": 9}


def test_streak_counts_consecutive_days_ending_today():
    db = fresh()
    store.seed(db, "a", D0)
    for back in (2, 1, 0):
        answer_on(db, "a", D0 - timedelta(days=back))
    assert store.summary(db, "a", D0)["streak_days"] == 3


def test_streak_survives_until_end_of_next_day_then_resets():
    db = fresh()
    store.seed(db, "a", D0)
    answer_on(db, "a", D0 - timedelta(days=1))
    answer_on(db, "a", D0 - timedelta(days=2))
    assert store.summary(db, "a", D0)["streak_days"] == 2                       # last review yesterday: alive
    assert store.summary(db, "a", D0 + timedelta(days=1))["streak_days"] == 0   # two days idle: gone


def test_gap_breaks_the_streak():
    db = fresh()
    store.seed(db, "a", D0)
    answer_on(db, "a", D0)
    answer_on(db, "a", D0 - timedelta(days=1))
    answer_on(db, "a", D0 - timedelta(days=3))  # day -2 missing
    assert store.summary(db, "a", D0)["streak_days"] == 2


def test_accuracy_and_weakest_subjects():
    db = fresh()
    math_id = find_question(db, "a", "math", "56")
    hist_id = find_question(db, "a", "history", "1947")
    bio_id = find_question(db, "a", "biology", "dna")
    store.check_answer(db, "a", str(math_id), "banana", today=D0)   # math: 1 miss of 1
    store.check_answer(db, "a", str(hist_id), "1947", today=D0)     # history: all right
    store.check_answer(db, "a", str(bio_id), "banana", today=D0)    # biology: 1 miss
    store.check_answer(db, "a", str(bio_id), "dna", today=D0)       # biology now 1 of 2 missed
    s = store.summary(db, "a", D0)
    assert s["answered"] == 4 and s["accuracy"] == 0.5
    assert s["weakest_subjects"] == ["math", "biology"]  # 100% missed, then 50%; history excluded


# ---------------------------------------------------------------- limits, timezones, anti-farming
def test_input_limits_are_enforced():
    db = fresh()
    assert store.add_card(db, "a", "q" * 301, "x", today=D0).get("error")
    assert store.add_card(db, "a", "q", "x" * 301, today=D0).get("error")
    assert store.add_task(db, "a", "t" * 201, today=D0).get("error")
    assert store.add_task(db, "a", "ok", due_in_days=-5, today=D0)["due"] == D0.isoformat()  # clamped to today
    assert store.add_card(db, "a", "q", "a", "s" * 100, today=D0)["subject"] == "s" * store.MAX_SUBJECT


def test_per_user_caps(monkeypatch=None):
    db = fresh()
    old = store.MAX_TASKS_PER_USER
    store.MAX_TASKS_PER_USER = 2
    try:
        assert "id" in store.add_task(db, "a", "one", today=D0)
        assert "id" in store.add_task(db, "a", "two", today=D0)
        assert "limit" in store.add_task(db, "a", "three", today=D0)["error"]
        assert "id" in store.add_task(db, "b", "other user is unaffected", today=D0)
    finally:
        store.MAX_TASKS_PER_USER = old


def test_timezone_validation_and_storage():
    db = fresh()
    assert store.valid_tz("Asia/Kolkata") and not store.valid_tz("Mars/Olympus") and not store.valid_tz(None)
    assert store.get_tz(db, "a") is None
    assert store.set_tz(db, "a", "Asia/Kolkata") == {"timezone": "Asia/Kolkata"}
    assert store.set_tz(db, "a", "America/New_York")["timezone"] == "America/New_York"  # update in place
    assert store.get_tz(db, "a") == "America/New_York" and store.get_tz(db, "b") is None
    assert store.set_tz(db, "a", "nope").get("error")
    assert isinstance(store.local_today("Asia/Kolkata"), date) and isinstance(store.local_today("bad"), date)


def test_reanswering_a_card_that_is_not_due_does_not_inflate_its_box():
    db = fresh()
    cid = find_question(db, "a", "math", "56")
    store.check_answer(db, "a", str(cid), "56", today=D0)             # due: box 2, back in 2 days
    r = store.check_answer(db, "a", str(cid), "56", today=D0)         # not due: no promotion
    assert r["correct"] is True and r["box"] == 2 and r["next_review_in_days"] == 2
    assert card_row(db, "a", cid)["due"] == (D0 + timedelta(days=2)).isoformat()
    r = store.check_answer(db, "a", str(cid), "banana", today=D0)     # a miss still resets, even early
    assert r["box"] == 1 and r["next_review_in_days"] == 0
