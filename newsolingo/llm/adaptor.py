"""Article text adaptation to CEFR proficiency levels."""

from __future__ import annotations

import logging
from typing import Any

from newsolingo.llm.client import LLMClient
from newsolingo.llm.prompts import (
    adapt_article_system_prompt,
    adapt_article_user_prompt,
)
from newsolingo.storage.models import AdaptedArticle, VocabularyItem

logger = logging.getLogger(__name__)

# Shorter fallback prompt for retry attempts when the first attempt fails
# due to JSON truncation (context window too small for full prompt).
_RETRY_SYSTEM = (
    "Simplify this {lang} text for a {level} language learner. "
    "Keep it in {lang}. Output ONLY valid JSON: "
    '{{"adapted_text":"...","vocabulary":[{{"term":"...","translation":"...","context":"..."}}]}}'
)

_RETRY_USER = "Simplify to 3-5 short sentences. Max 5 vocab items. JSON only.\n\n{text}"


def _parse_adaptation_result(
    result: dict[str, Any],
) -> tuple[str, list[VocabularyItem]]:
    """Extract adapted text and vocabulary from an LLM JSON response."""
    vocabulary = []
    for v in result.get("vocabulary", []):
        if isinstance(v, dict):
            vocabulary.append(
                VocabularyItem(
                    term=v.get("term", ""),
                    translation=v.get("translation", ""),
                    context=v.get("context", ""),
                )
            )

    adapted_text = result.get("adapted_text", "")
    return adapted_text, vocabulary


def adapt_article(
    client: LLMClient,
    original_text: str,
    language_code: str,
    level: str,
    max_length: int = 2000,
    source_name: str = "",
    subject: str = "",
    original_url: str = "",
) -> AdaptedArticle:
    """Adapt an article to a target CEFR level using the LLM.

    Includes retry logic: if the first attempt fails (e.g., JSON truncated
    due to limited context window), retries with a much shorter input.
    If both attempts fail, returns the original text truncated as a fallback
    so the session can still proceed.

    Args:
        client: The LLM client.
        original_text: The original article text.
        language_code: The language code (e.g., "pt_br", "he").
        level: The target CEFR level.
        max_length: Maximum adapted text length.
        source_name: Name of the content source.
        subject: The subject category.
        original_url: Original article URL.

    Returns:
        An AdaptedArticle with the simplified text and vocabulary.
    """
    from newsolingo.llm.prompts import LANGUAGE_NAMES

    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    adapted_text = ""
    vocabulary: list[VocabularyItem] = []

    # --- Attempt 1: normal adaptation ---
    try:
        system_prompt = adapt_article_system_prompt(language_code, level)
        user_prompt = adapt_article_user_prompt(original_text, max_length)

        logger.info("Adapting article to %s level %s", language_code, level)
        result = client.chat_json(system_prompt, user_prompt, temperature=0.5)
        adapted_text, vocabulary = _parse_adaptation_result(result)
    except (ValueError, Exception) as e:
        logger.warning("First adaptation attempt failed: %s", e)

    # --- Attempt 2: retry with aggressively shortened input ---
    if not adapted_text:
        try:
            logger.info("Retrying adaptation with shortened input")
            short_text = original_text[:800]
            retry_system = _RETRY_SYSTEM.format(lang=lang_name, level=level)
            retry_user = _RETRY_USER.format(text=short_text)
            result = client.chat_json(retry_system, retry_user, temperature=0.5)
            adapted_text, vocabulary = _parse_adaptation_result(result)
        except (ValueError, Exception) as e:
            logger.warning("Retry adaptation also failed: %s", e)

    # --- Fallback: use original text truncated ---
    if not adapted_text:
        logger.warning(
            "Both adaptation attempts failed. Using truncated original text as fallback."
        )
        adapted_text = original_text[:max_length]

    return AdaptedArticle(
        original_text=original_text,
        adapted_text=adapted_text,
        level=level,
        language_code=language_code,
        vocabulary=vocabulary,
        source_name=source_name,
        subject=subject,
        original_url=original_url,
    )
