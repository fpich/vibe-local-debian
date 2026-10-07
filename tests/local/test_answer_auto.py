from __future__ import annotations

from vibe.app_server.models import (
    QuestionChoice,
    UserAnswer,
    UserQuestion,
    UserQuestionRequest,
)
from vibe.cli.textual_ui.app import (
    _ANSWER_AUTO_DEFAULT_TEXT,
    _ANSWER_AUTO_PROMPT_CHAR_BUDGET,
    StartupOptions,
    VibeApp,
)


def _app_for(initial_prompt: str | None) -> VibeApp:
    app = VibeApp.__new__(VibeApp)
    app._initial_prompt = initial_prompt
    return app


def test_answer_auto_derives_text_from_initial_prompt() -> None:
    app = _app_for("Implement the auth module")
    text = app._derive_auto_answer_text()
    assert "auth module" in text
    assert "durcis" in text


def test_answer_auto_falls_back_to_default_text() -> None:
    app = _app_for(None)
    assert app._derive_auto_answer_text() == _ANSWER_AUTO_DEFAULT_TEXT
    app = _app_for("   ")
    assert app._derive_auto_answer_text() == _ANSWER_AUTO_DEFAULT_TEXT


def test_answer_auto_clips_long_prompt() -> None:
    app = _app_for("x" * 500)
    text = app._derive_auto_answer_text()
    assert "x" * _ANSWER_AUTO_PROMPT_CHAR_BUDGET in text
    assert "x" * (_ANSWER_AUTO_PROMPT_CHAR_BUDGET + 10) not in text


def test_answer_auto_builds_one_answer_per_question() -> None:
    app = _app_for("Implement the auth module")
    request = UserQuestionRequest(
        questions=[
            UserQuestion(
                question="Which DB?",
                options=[QuestionChoice(label="A"), QuestionChoice(label="B")],
            ),
            UserQuestion(
                question="Which port?",
                options=[QuestionChoice(label="1"), QuestionChoice(label="2")],
            ),
        ]
    )
    result = app._build_auto_user_question_result(request)
    assert not result.cancelled
    assert len(result.answers) == 2
    assert all(
        isinstance(answer, UserAnswer) and answer.is_other for answer in result.answers
    )
    assert {answer.question for answer in result.answers} == {
        "Which DB?",
        "Which port?",
    }
    assert all(
        "Implement the auth module" in answer.answer for answer in result.answers
    )


def test_startup_options_carry_answer_auto() -> None:
    assert StartupOptions().answer_auto is False
    assert StartupOptions(answer_auto=True).answer_auto is True
