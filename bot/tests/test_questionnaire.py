"""The screening gate (PRD 7.6).

The behaviour that matters is not which questions exist but what a failure means: this
request only, never the donor's standing.
"""

from __future__ import annotations

import pytest

from app.core import questionnaire as quiz
from app.enums import Sex
from app.i18n import t


def test_pregnancy_question_is_asked_only_of_female_donors():
    female = [q.id for q in quiz.questions_for(Sex.FEMALE)]
    male = [q.id for q in quiz.questions_for(Sex.MALE)]
    other = [q.id for q in quiz.questions_for(Sex.OTHER)]

    assert "pregnancy" in female
    assert "pregnancy" not in male
    assert "pregnancy" not in other


def test_question_count_matches_the_asked_set():
    assert quiz.total_questions(Sex.FEMALE) == quiz.total_questions(Sex.MALE) + 1


def test_walking_off_the_end_returns_none():
    last = quiz.total_questions(Sex.MALE)
    assert quiz.question_at(Sex.MALE, last - 1) is not None
    assert quiz.question_at(Sex.MALE, last) is None
    assert quiz.question_at(Sex.MALE, -1) is None


@pytest.mark.parametrize(
    ("question_id", "answer", "disqualifies"),
    [
        ("weight", False, True),  # under 45 kg
        ("weight", True, False),
        ("feeling_well", False, True),  # not well today
        ("feeling_well", True, False),
        ("recent_illness", True, True),
        ("recent_illness", False, False),
        ("medication", True, True),
        ("tattoo", True, True),
        ("alcohol", True, True),
        ("pregnancy", True, True),
    ],
)
def test_disqualifying_answers(question_id, answer, disqualifies):
    question = quiz.BY_ID[question_id]
    assert quiz.is_disqualifying(question, answer) is disqualifies


def test_only_lasting_conditions_are_flagged_for_review():
    """Fever, medication and tattoos pass with time; they must not touch the profile."""
    temporary = {q.id for q in quiz.QUESTIONS if q.fail_kind == quiz.FailKind.TEMPORARY}
    review = {q.id for q in quiz.QUESTIONS if q.fail_kind == quiz.FailKind.REVIEW}

    assert review == {"weight"}
    assert {"recent_illness", "medication", "tattoo", "alcohol", "pregnancy"} <= temporary


def test_every_question_has_translated_text_and_a_failure_note():
    for question in quiz.QUESTIONS:
        assert t(question.key) != question.key, f"missing text for {question.id}"
        assert t(question.fail_key) != question.fail_key, f"missing note for {question.id}"


def test_failure_notes_are_never_phrased_as_a_medical_verdict():
    """PRD 7.6: never tell a donor they are unfit -- only that today is not the day."""
    banned = ("you are not eligible", "unfit", "rejected", "you cannot donate", "disqualified")
    for question in quiz.QUESTIONS:
        note = t(question.fail_key).lower()
        for phrase in banned:
            assert phrase not in note, f"{question.id} reads as a verdict: {note!r}"


def test_elimination_message_reassures_about_future_requests():
    body = t("questionnaire.eliminated", reason="x").lower()
    assert "registration" in body
