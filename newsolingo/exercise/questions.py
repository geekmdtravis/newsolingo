"""Comprehension question generation via LLM."""

from __future__ import annotations

import logging

from newsolingo.llm.client import LLMClient
from newsolingo.llm.prompts import (
    generate_questions_system_prompt,
    generate_questions_user_prompt,
)
from newsolingo.storage.models import QuestionItem

logger = logging.getLogger(__name__)


def generate_questions(
    client: LLMClient,
    adapted_text: str,
    language_code: str,
    level: str,
    num_questions: int = 4,
) -> list[QuestionItem]:
    """Generate comprehension questions for an adapted article.

    Args:
        client: The LLM client.
        adapted_text: The adapted article text.
        language_code: The target language code.
        level: The user's CEFR level.
        num_questions: Number of questions to generate.

    Returns:
        List of QuestionItem objects.
    """
    system_prompt = generate_questions_system_prompt(language_code, level)
    user_prompt = generate_questions_user_prompt(adapted_text, num_questions)

    logger.info(
        "Generating %d questions for %s at level %s",
        num_questions,
        language_code,
        level,
    )

    result = client.chat_json(system_prompt, user_prompt, temperature=0.6)

    questions = []
    for q in result.get("questions", []):
        questions.append(
            QuestionItem(
                question=q.get("question", ""),
                expected_answer_hint=q.get("expected_answer_hint", ""),
            )
        )

    if not questions:
        logger.warning("LLM returned no questions, generating fallback")
        questions = [
            QuestionItem(
                question="What is this text about?",
                expected_answer_hint="A summary of the main topic",
            )
        ]

    return questions[:num_questions]
