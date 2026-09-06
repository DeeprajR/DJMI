"""Pre-screening questionnaire (PRD 7.6, P0-8).

A hard gate, not a medical assessment. Its only job is to stop a wasted trip to the
blood bank; final screening always happens on site.

Two rules the wording and the data model both have to respect:

- A disqualifying answer eliminates the donor **from this request only**. Temporary
  conditions (fever, medication, a recent tattoo) never touch the donor profile, so the
  donor stays eligible for the next request.
- Answers that suggest a lasting deferral raise ``review_flag`` for a human to look at.
  Nothing is ever phrased to the donor as a medical verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.enums import Sex


class FailKind(StrEnum):
    #: Passes on its own with time; profile untouched.
    TEMPORARY = "TEMPORARY"
    #: Worth a volunteer admin glance; still only blocks this request.
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Question:
    id: str
    #: i18n key for the question text.
    key: str
    #: The answer that disqualifies.
    disqualifying_answer: bool
    fail_kind: FailKind
    #: i18n key for the note shown when this answer ends the flow.
    fail_key: str
    #: Restrict to one sex, e.g. the pregnancy question.
    only_sex: Sex | None = None


QUESTIONS: tuple[Question, ...] = (
    Question(
        id="weight",
        key="questionnaire.weight",
        disqualifying_answer=False,
        fail_kind=FailKind.REVIEW,
        fail_key="questionnaire.fail.weight",
    ),
    Question(
        id="feeling_well",
        key="questionnaire.feeling_well",
        disqualifying_answer=False,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.feeling_well",
    ),
    Question(
        id="recent_illness",
        key="questionnaire.recent_illness",
        disqualifying_answer=True,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.recent_illness",
    ),
    Question(
        id="medication",
        key="questionnaire.medication",
        disqualifying_answer=True,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.medication",
    ),
    Question(
        id="tattoo",
        key="questionnaire.tattoo",
        disqualifying_answer=True,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.tattoo",
    ),
    Question(
        id="alcohol",
        key="questionnaire.alcohol",
        disqualifying_answer=True,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.alcohol",
    ),
    Question(
        id="pregnancy",
        key="questionnaire.pregnancy",
        disqualifying_answer=True,
        fail_kind=FailKind.TEMPORARY,
        fail_key="questionnaire.fail.pregnancy",
        only_sex=Sex.FEMALE,
    ),
)

BY_ID: dict[str, Question] = {q.id: q for q in QUESTIONS}


def questions_for(sex: str | None) -> tuple[Question, ...]:
    """The question set a donor of this sex is asked, in order."""
    return tuple(q for q in QUESTIONS if q.only_sex is None or q.only_sex == sex)


def question_at(sex: str | None, index: int) -> Question | None:
    """The ``index``-th question for this donor, or None when the set is exhausted."""
    asked = questions_for(sex)
    return asked[index] if 0 <= index < len(asked) else None


def total_questions(sex: str | None) -> int:
    return len(questions_for(sex))


def is_disqualifying(question: Question, answer: bool) -> bool:
    return answer == question.disqualifying_answer
