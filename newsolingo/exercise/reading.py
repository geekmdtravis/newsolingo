"""Reading exercise orchestration - ties together fetching, adaptation, and display."""

from __future__ import annotations

import logging
import random

from newsolingo.config import AppConfig
from newsolingo.fetcher.scraper import fetch_random_article
from newsolingo.fetcher.sources import SourceRegistry
from newsolingo.llm.adaptor import adapt_article
from newsolingo.llm.client import LLMClient
from newsolingo.storage.database import Database
from newsolingo.storage.models import AdaptedArticle

logger = logging.getLogger(__name__)


def prepare_reading_exercise(
    config: AppConfig,
    llm_client: LLMClient,
    db: Database,
    source_registry: SourceRegistry,
    language_code: str,
    subject: str | None = None,
) -> AdaptedArticle | None:
    """Prepare a reading exercise by fetching and adapting an article.

    This is the main orchestration function that:
    1. Picks a source for the given language/subject
    2. Fetches an article from that source
    3. Adapts it to the user's CEFR level
    4. Caches everything in the database

    Args:
        config: Application configuration.
        llm_client: LLM client for text adaptation.
        db: Database for caching.
        source_registry: Registry of content sources.
        language_code: The language to practice.
        subject: Optional subject filter.

    Returns:
        An AdaptedArticle ready for the exercise, or None on failure.
    """
    lang_config = config.get_language(language_code)

    # Check if we have a cached unused article first
    cached = db.get_unused_article(language_code, subject)
    if cached and cached.get("adapted_text"):
        logger.info("Using cached article: %s", cached.get("original_url"))
        vocab = []
        if cached.get("vocabulary_json"):
            import json

            raw_vocab = json.loads(cached["vocabulary_json"])
            from newsolingo.storage.models import VocabularyItem

            vocab = [
                VocabularyItem(
                    term=v.get("term", ""),
                    translation=v.get("translation", ""),
                    context=v.get("context", ""),
                )
                for v in raw_vocab
            ]
        return AdaptedArticle(
            original_text=cached.get("original_text", ""),
            adapted_text=cached["adapted_text"],
            level=cached.get("adapted_level", lang_config.level),
            language_code=language_code,
            vocabulary=vocab,
            source_name=cached.get("source_name", ""),
            subject=cached.get("subject", ""),
            original_url=cached.get("original_url", ""),
            article_id=cached["id"],
        )

    # Determine which subjects to try
    if subject:
        subjects_to_try = [subject]
    else:
        subjects_to_try = list(lang_config.subjects)
        random.shuffle(subjects_to_try)

    # Try to fetch from each subject's sources
    for try_subject in subjects_to_try:
        result = source_registry.pick_random_source(language_code, try_subject)
        if not result:
            continue

        source, chosen_subject = result
        logger.info(
            "Trying source: %s (%s) for subject '%s'",
            source.name,
            source.url,
            chosen_subject,
        )

        article_result = fetch_random_article(source)
        if not article_result:
            continue

        article_url, article_text = article_result

        # Save the raw article to the database
        article_id = db.save_article(
            language_code=language_code,
            source_name=source.name,
            subject=chosen_subject,
            original_url=article_url,
            original_text=article_text,
        )

        # Adapt the article using the LLM
        try:
            adapted = adapt_article(
                client=llm_client,
                original_text=article_text,
                language_code=language_code,
                level=lang_config.level,
                max_length=config.exercise.max_adapted_length,
                source_name=source.name,
                subject=chosen_subject,
                original_url=article_url,
            )
            adapted.article_id = article_id

            # Update the database with the adapted version
            db.update_article_adaptation(
                article_id=article_id,
                adapted_text=adapted.adapted_text,
                adapted_level=adapted.level,
                vocabulary=[
                    {"term": v.term, "translation": v.translation, "context": v.context}
                    for v in adapted.vocabulary
                ],
            )

            return adapted

        except Exception as e:
            logger.error("Failed to adapt article: %s", e)
            continue

    logger.error("Could not prepare any reading exercise for %s", language_code)
    return None
