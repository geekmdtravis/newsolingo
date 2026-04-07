"""Reading exercise orchestration - ties together fetching, adaptation, and display."""

from __future__ import annotations

import logging
import random
import sqlite3
from urllib.parse import urlparse

from newsolingo.config import AppConfig
from newsolingo.fetcher.scraper import fetch_random_article, fetch_article_from_url
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
    direct_url: str | None = None,
) -> AdaptedArticle | None:
    """Prepare a reading exercise by fetching and adapting an article.

    This is the main orchestration function that:
    - If direct_url is provided: fetches article from that URL directly
    - Otherwise: picks a source for the given language/subject and fetches an article
    Then adapts it to the user's CEFR level and caches everything in the database.

    Args:
        config: Application configuration.
        llm_client: LLM client for text adaptation.
        db: Database for caching.
        source_registry: Registry of content sources.
        language_code: The language to practice.
        subject: Optional subject filter.
        direct_url: Optional direct URL to scrape (bypasses source registry).

    Returns:
        An AdaptedArticle ready for the exercise, or None on failure.
    """
    lang_config = config.get_language(language_code)

    # Direct URL mode
    if direct_url is not None:
        logger.info("Fetching direct URL: %s", direct_url)
        result = fetch_article_from_url(direct_url)
        if not result:
            logger.error("Failed to extract article from %s", direct_url)
            return None
        article_url, article_text = result
        # Determine source name from domain
        domain = urlparse(article_url).netloc
        source_name = domain.replace("www.", "")
        # Use provided subject or default "Direct"
        article_subject = subject or "Direct"

        try:
            article_id = db.save_article(
                language_code=language_code,
                source_name=source_name,
                subject=article_subject,
                original_url=article_url,
                original_text=article_text,
            )
        except sqlite3.IntegrityError:
            # Article already exists, fetch its ID
            row = db.conn.execute(
                "SELECT id, adapted_text, adapted_level, vocabulary_json FROM articles WHERE original_url = ?",
                (article_url,),
            ).fetchone()
            if row and row["adapted_text"]:
                # Already adapted, return cached version
                logger.info("Using cached adapted article: %s", article_url)
                vocab = []
                if row["vocabulary_json"]:
                    import json

                    raw_vocab = json.loads(row["vocabulary_json"])
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
                    original_text=article_text,
                    adapted_text=row["adapted_text"],
                    level=row["adapted_level"] or lang_config.level,
                    language_code=language_code,
                    vocabulary=vocab,
                    source_name=source_name,
                    subject=article_subject,
                    original_url=article_url,
                    article_id=row["id"],
                )
            # Article exists but not adapted yet, get its ID
            article_id = row["id"] if row else None
            # If no row (should not happen), fall back to insert with ignore?
            if article_id is None:
                # Try insert with OR IGNORE
                cursor = db.conn.execute(
                    """INSERT OR IGNORE INTO articles
                       (language_code, source_name, subject, original_url, original_text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        language_code,
                        source_name,
                        article_subject,
                        article_url,
                        article_text,
                    ),
                )
                db.conn.commit()
                article_id = cursor.lastrowid
        # Adapt the article
        try:
            adapted = adapt_article(
                client=llm_client,
                original_text=article_text,
                language_code=language_code,
                level=lang_config.level,
                max_length=config.exercise.max_adapted_length,
                source_name=source_name,
                subject=article_subject,
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
            logger.error("Failed to adapt article from direct URL: %s", e)
            return None

    # Normal mode (crawling)

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
