"""Data models for Newsolingo exercises and sessions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VocabularyItem:
    """A vocabulary word/phrase with its translation."""

    term: str
    translation: str
    context: str = ""


@dataclass
class AdaptedArticle:
    """An article that has been adapted to a CEFR level."""

    original_text: str
    adapted_text: str
    level: str
    language_code: str
    vocabulary: list[VocabularyItem] = field(default_factory=list)
    source_name: str = ""
    subject: str = ""
    original_url: str = ""
    article_id: int | None = None


@dataclass
class TranslationAssessment:
    """Assessment of the user's translation."""

    score: float  # 0-100
    accuracy: str  # Brief assessment of accuracy
    nuance: str  # Assessment of nuance capture
    completeness: str  # Assessment of completeness
    suggestions: str  # Suggestions for improvement
    corrected_translation: str = ""  # Model's suggested translation


@dataclass
class QuestionItem:
    """A comprehension question."""

    question: str
    expected_answer_hint: str = ""  # Brief hint about what a good answer includes


@dataclass
class AnswerAssessment:
    """Assessment of a single answer."""

    score: float  # 0-100
    correctness: str  # Assessment of content correctness
    grammar: str  # Assessment of grammar in the target language
    feedback: str  # Overall feedback


@dataclass
class SessionResult:
    """Complete result of a practice session."""

    session_id: int
    language_code: str
    level: str
    article: AdaptedArticle
    user_translation: str
    translation_assessment: TranslationAssessment
    ignore_accents: bool = True
    questions: list[QuestionItem] = field(default_factory=list)
    user_answers: list[str] = field(default_factory=list)
    answer_assessments: list[AnswerAssessment] = field(default_factory=list)

    @property
    def translation_score(self) -> float:
        return self.translation_assessment.score

    @property
    def questions_score(self) -> float:
        if not self.answer_assessments:
            return 0.0
        return sum(a.score for a in self.answer_assessments) / len(
            self.answer_assessments
        )

    @property
    def overall_score(self) -> float:
        # Weight translation at 40%, questions at 60%
        if not self.answer_assessments:
            return self.translation_score
        return (self.translation_score * 0.4) + (self.questions_score * 0.6)
