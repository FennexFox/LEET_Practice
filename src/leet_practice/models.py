"""Core data models for LEET practice records.

The models are intentionally small at this stage. They define stable concepts
for later storage in JSON, SQLite, or an API layer.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Subject(StrEnum):
    """Supported subject areas."""

    VERBAL = "verbal"
    REASONING = "reasoning"
    WRITING = "writing"


class ExamForm(StrEnum):
    """Common exam form markers."""

    ODD = "odd"
    EVEN = "even"
    A = "a"
    B = "b"
    UNKNOWN = "unknown"


class QuestionType(StrEnum):
    """Controlled vocabulary for question type metadata."""

    CONSISTENCY = "consistency"
    INFERENCE = "inference"
    APPLICATION = "application"
    ARGUMENT_EVALUATION = "argument_evaluation"
    STRENGTHEN_WEAKEN = "strengthen_weaken"
    CONDITIONAL_REASONING = "conditional_reasoning"
    CALCULATION_LOGIC = "calculation_logic"
    CASE_ANALYSIS = "case_analysis"
    COUNTEREXAMPLE = "counterexample"
    STRUCTURE_ANALYSIS = "structure_analysis"
    UNKNOWN = "unknown"


class ErrorType(StrEnum):
    """Controlled vocabulary for diagnosed wrong-answer causes."""

    SKIPPED_VERIFICATION = "skipped_verification"
    SHIFTED_ELIMINATION_CRITERION = "shifted_elimination_criterion"
    STRONG_WORDING_AVOIDANCE = "strong_wording_avoidance"
    PARTIAL_CONDITION_MATCH = "partial_condition_match"
    NECESSARY_SUFFICIENT_CONFUSION = "necessary_sufficient_confusion"
    ARGUMENT_TARGET_REVERSAL = "argument_target_reversal"
    EXCEPT_QUESTION_MISREAD = "except_question_misread"
    HABITUAL_JUDGMENT_CRITERION = "habitual_judgment_criterion"
    HARD_CHOICE_AVOIDANCE = "hard_choice_avoidance"
    ADDED_PREMISE = "added_premise"
    REPRESENTATION_TARGET_CONFUSION = "representation_target_confusion"
    UNKNOWN = "unknown"


class TextStatus(StrEnum):
    """Trust level for stored text."""

    NONE = "none"
    OCR_RAW = "ocr_raw"
    MANUAL = "manual"
    VERIFIED = "verified"


class Exam(BaseModel):
    """A specific exam subject/form instance."""

    id: str = Field(examples=["leet-2026-verbal-even"])
    exam_name: str = Field(examples=["LEET"])
    year: int = Field(ge=1900, le=3000)
    subject: Subject
    form: ExamForm = ExamForm.UNKNOWN
    question_count: int = Field(gt=0)


class Passage(BaseModel):
    """A shared passage used by one or more questions."""

    id: str
    exam_id: str
    passage_no: int = Field(gt=0)
    question_range: tuple[int, int]
    body_text: str | None = None
    topic: str | None = None
    domain: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    text_status: TextStatus = TextStatus.NONE

    @field_validator("question_range")
    @classmethod
    def validate_question_range(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if start <= 0 or end < start:
            raise ValueError("question_range must be positive and ordered")
        return value


class Choice(BaseModel):
    """One answer choice."""

    choice_no: int = Field(ge=1, le=5)
    text: str | None = None
    is_correct: bool = False
    choice_role: str | None = None
    error_trigger: str | None = None


class Question(BaseModel):
    """A question and optional verified text."""

    id: str
    exam_id: str
    question_no: int = Field(gt=0)
    passage_id: str | None = None
    stem: str | None = None
    choices: list[Choice] = Field(default_factory=list)
    correct_answer: int = Field(ge=1, le=5)
    question_type: QuestionType = QuestionType.UNKNOWN
    difficulty: int | None = Field(default=None, ge=1, le=5)
    primary_skill: str | None = None
    trap_pattern: str | None = None
    text_status: TextStatus = TextStatus.NONE


class Attempt(BaseModel):
    """A single solving session."""

    id: str
    exam_id: str
    attempt_date: date
    mode: Literal["real", "review", "partial"] = "real"
    time_limit_minutes: int | None = Field(default=None, gt=0)
    notes: str | None = None


class AttemptAnswer(BaseModel):
    """A selected answer for one question in one attempt."""

    attempt_id: str
    question_id: str
    selected_answer: int = Field(ge=1, le=5)
    correct_answer: int = Field(ge=1, le=5)
    confidence: int | None = Field(default=None, ge=1, le=5)
    elapsed_seconds: int | None = Field(default=None, ge=0)
    marked_for_review: bool = False
    guessed: bool = False

    @property
    def is_correct(self) -> bool:
        return self.selected_answer == self.correct_answer


class AttemptReviewStatus(StrEnum):
    """Workflow status for one attempted question review."""

    UNREVIEWED = "unreviewed"
    USER_ENTERED = "user_entered"
    READY_FOR_FEEDBACK = "ready_for_feedback"
    FEEDBACK_ADDED = "feedback_added"
    RESOLVED = "resolved"


class UserResolutionStatus(StrEnum):
    """User decision on assistant feedback."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class AttemptChoiceAnswer(BaseModel):
    """Selected answer captured at attempt level."""

    question_no: int = Field(gt=0)
    selected_choice: int = Field(ge=1, le=5)
    confidence: int | None = Field(default=None, ge=1, le=5)
    elapsed_seconds: int | None = Field(default=None, ge=0)
    marked_for_review: bool = False
    guessed: bool = False


class AttemptRecord(BaseModel):
    """A stored attempt with selected answers independent of canonical data."""

    id: str
    exam_id: str
    attempt_date: date = Field(default_factory=date.today)
    mode: Literal["real", "review", "partial"] = "real"
    answers: list[AttemptChoiceAnswer] = Field(default_factory=list)
    time_limit_minutes: int | None = Field(default=None, gt=0)
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("answers")
    @classmethod
    def require_unique_question_numbers(cls, value: list[AttemptChoiceAnswer]) -> list[AttemptChoiceAnswer]:
        question_numbers = [answer.question_no for answer in value]
        if len(question_numbers) != len(set(question_numbers)):
            raise ValueError("attempt answers must not contain duplicate question_no values")
        return sorted(value, key=lambda answer: answer.question_no)


class ReviewGrading(BaseModel):
    """Grading result for one attempted question."""

    selected_choice: int = Field(ge=1, le=5)
    correct_choice: int = Field(ge=1, le=5)
    is_correct: bool = False

    @model_validator(mode="after")
    def derive_is_correct(self) -> "ReviewGrading":
        self.is_correct = self.selected_choice == self.correct_choice
        return self


class UserSelfReview(BaseModel):
    """Free-form user reasoning preserved separately from assistant feedback."""

    reasoning_text: str = ""
    why_selected: str = ""
    decisive_condition: str = ""
    why_rejected_correct: str = ""
    current_reflection: str = ""
    condition_notes: str = ""
    created_by: Literal["user"] = "user"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AssistantFeedback(BaseModel):
    """Assistant-generated diagnosis with explicitly provisional tags."""

    diagnosis_text: str = ""
    evidence: list[str] = Field(default_factory=list)
    provisional_error_tags: list[str] = Field(default_factory=list)
    correction_rule: str = ""
    created_by: Literal["assistant"] = "assistant"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class UserResolution(BaseModel):
    """User decision after reviewing assistant feedback."""

    status: UserResolutionStatus = UserResolutionStatus.PENDING
    final_error_tags: list[str] = Field(default_factory=list)
    note: str | None = None
    created_by: Literal["user"] = "user"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AttemptReviewRecord(BaseModel):
    """Per-question self-review record for the v1 attempt-review workflow."""

    attempt_id: str
    exam_id: str
    question_no: int = Field(gt=0)
    question_id: str | None = None
    status: AttemptReviewStatus = AttemptReviewStatus.UNREVIEWED
    grading: ReviewGrading
    user_self_review: UserSelfReview = Field(default_factory=UserSelfReview)
    assistant_feedback: AssistantFeedback | None = None
    user_resolution: UserResolution = Field(default_factory=UserResolution)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Review(BaseModel):
    """Legacy wrong-answer review record.

    The v1 attempt-review workflow uses AttemptReviewRecord instead so user
    reasoning is not forced into early fixed taxonomy choices.
    """

    id: str
    attempt_id: str
    question_id: str
    selected_answer: int = Field(ge=1, le=5)
    correct_answer: int = Field(ge=1, le=5)
    reasoning_category: Literal["A", "B", "C", "D", "E", "F"] | None = None
    initial_reason: str | None = None
    diagnosed_error_type: ErrorType = ErrorType.UNKNOWN
    error_description: str | None = None
    correction_rule: str | None = None
    next_time_checklist: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=datetime.now)
