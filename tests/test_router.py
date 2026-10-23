"""Tests for router.py (keyword fallback). No MCP, no network: the tool caller is a fake."""
import asyncio

import router


def run(texts, session="r"):
    """Feed utterances through the router; return [(tool_called_or_None, reply), ...]."""
    out = []

    async def go():
        for text in texts:
            seen = []

            async def call(name, args):
                seen.append(name)
                return {"speech": f"<{name}>", "question_id": "5"}

            out.append((seen[0] if seen else None, await router.route(text, call, session), seen))

    router.STATE.clear()
    asyncio.run(go())
    return [(o[2][0] if o[2] else None) for o in out]


def after_quiz(answer):
    """The tool the router calls for `answer` while a quiz question is pending."""
    return run(["quiz me on biology", answer])[1]


def test_answers_containing_command_letters_are_graded_not_misrouted():
    for answer in ("photoplankton", "planet", "address", "playlist", "undone", "daddy", "listen", "mitochondria"):
        assert after_quiz(answer) == "check_answer", answer


def test_real_commands_still_work_while_a_question_is_pending():
    assert after_quiz("how am I doing") == "study_summary"
    assert after_quiz("plan 3 days for math") == "plan_revision"
    assert after_quiz("add a task to read chapter 5") == "add_study_task"
    assert after_quiz("what's on my list") == "list_study_tasks"


def test_commands_without_a_pending_question():
    assert run(["quiz me on math"])[0] == "quiz_me"
    assert run(["how am I doing"])[0] == "study_summary"
    assert run(["plan 4 days for biology"])[0] == "plan_revision"
    assert run(["mark task 2 as done"])[0] == "complete_study_task"
    assert run(["remember that mitosis is cell division"])[0] == "add_flashcard"
    assert run(["make flashcards from: Osmosis is water movement"])[0] == "generate_flashcards_from_notes"


def test_words_that_merely_contain_a_command_are_not_commands():
    assert run(["planet earth"])[0] is None      # falls through to the help text
    assert run(["I need an explanation"])[0] is None


def test_sessions_keep_separate_pending_questions():
    router.STATE.clear()

    async def go():
        async def call(name, args):
            return {"speech": name, "question_id": "5"}
        await router.route("quiz me", call, "alice")
        return router.STATE["alice"]["qid"], router.STATE.get("bob", {"qid": None})["qid"]

    assert asyncio.run(go()) == ("5", None)
