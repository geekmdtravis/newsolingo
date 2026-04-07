"""Assessment of translations and comprehension answers via LLM."""

from __future__ import annotations

import logging

from newsolingo.llm.client import LLMClient
from newsolingo.llm.prompts import (
    assess_answer_system_prompt,
    assess_answer_user_prompt,
    assess_translation_system_prompt,
    assess_translation_user_prompt,
)
from newsolingo.languages.registry import get_language_info
from newsolingo.storage.models import AnswerAssessment, TranslationAssessment

logger = logging.getLogger(__name__)


def assess_translation(
    client: LLMClient,
    adapted_text: str,
    user_translation: str,
    language_code: str,
    level: str,
    ignore_accents: bool = True,
) -> TranslationAssessment:
    """Assess the quality of a user's English translation.

    Args:
        client: The LLM client.
        adapted_text: The adapted text the user was translating.
        user_translation: The user's English translation.
        language_code: The source language code.
        level: The user's CEFR level.
        ignore_accents: Whether to ignore missing accents/accept transliteration.

    Returns:
        A TranslationAssessment with score and feedback.
    """
    system_prompt = assess_translation_system_prompt(
        language_code, level, ignore_accents
    )
    user_prompt = assess_translation_user_prompt(adapted_text, user_translation)

    logger.info(
        "Assessing translation for %s at level %s (ignore_accents=%s)",
        language_code,
        level,
        ignore_accents,
    )

    result = client.chat_json(system_prompt, user_prompt, temperature=0.3)

    return TranslationAssessment(
        score=_clamp_score(result.get("score", 50)),
        accuracy=result.get("accuracy", "No assessment available"),
        nuance=result.get("nuance", "No assessment available"),
        completeness=result.get("completeness", "No assessment available"),
        suggestions=result.get("suggestions", "No suggestions available"),
        corrected_translation=result.get("corrected_translation", ""),
    )


def assess_answer(
    client: LLMClient,
    adapted_text: str,
    question: str,
    user_answer: str,
    expected_hint: str,
    language_code: str,
    level: str,
    ignore_accents: bool = True,
) -> AnswerAssessment:
    """Assess the quality of a user's answer to a comprehension question.

    Args:
        client: The LLM client.
        adapted_text: The adapted text the question is about.
        question: The comprehension question.
        user_answer: The user's answer in the target language.
        expected_hint: Hint about what the answer should contain.
        language_code: The target language code.
        level: The user's CEFR level.
        ignore_accents: Whether to ignore missing accents/accept transliteration.

    Returns:
        An AnswerAssessment with score and feedback.
    """
    system_prompt = assess_answer_system_prompt(language_code, level, ignore_accents)
    user_prompt = assess_answer_user_prompt(
        adapted_text, question, user_answer, expected_hint
    )

    logger.info(
        "Assessing answer for %s at level %s (ignore_accents=%s)",
        language_code,
        level,
        ignore_accents,
    )

    result = client.chat_json(system_prompt, user_prompt, temperature=0.3)

    return AnswerAssessment(
        score=_clamp_score(result.get("score", 50)),
        correctness=result.get("correctness", "No assessment available"),
        grammar=result.get("grammar", "No assessment available"),
        feedback=result.get("feedback", "No feedback available"),
    )


def _clamp_score(score: float | int) -> float:
    """Clamp a score to the 0-100 range."""
    try:
        return max(0.0, min(100.0, float(score)))
    except (ValueError, TypeError):
        return 50.0
