"""Progress tracking and level advancement suggestions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from newsolingo.config import AppConfig, CEFR_LEVELS
from newsolingo.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class ProgressReport:
    """A report on the user's progress in a language."""

    language_code: str
    language_name: str
    current_level: str
    total_sessions: int
    rolling_average: float | None
    all_time_average: float | None
    best_score: float | None
    worst_score: float | None
    avg_translation: float | None
    avg_questions: float | None
    should_suggest_advancement: bool
    suggested_next_level: str | None


def get_progress_report(
    db: Database,
    config: AppConfig,
    language_code: str,
) -> ProgressReport:
    """Generate a progress report for a language."""
    lang_config = config.get_language(language_code)
    stats = db.get_all_sessions_stats(language_code)
    total_sessions = db.get_session_count(language_code)
    rolling_avg = db.get_rolling_average(language_code, config.advancement.min_sessions)

    # Determine if we should suggest advancement
    should_suggest = False
    next_level = config.next_level(lang_config.level)
    if (
        next_level
        and total_sessions >= config.advancement.min_sessions
        and rolling_avg is not None
        and rolling_avg >= config.advancement.threshold_score
    ):
        should_suggest = True

    return ProgressReport(
        language_code=language_code,
        language_name=lang_config.name,
        current_level=lang_config.level,
        total_sessions=total_sessions,
        rolling_average=rolling_avg,
        all_time_average=stats.get("avg_score"),
        best_score=stats.get("max_score"),
        worst_score=stats.get("min_score"),
        avg_translation=stats.get("avg_translation"),
        avg_questions=stats.get("avg_questions"),
        should_suggest_advancement=should_suggest,
        suggested_next_level=next_level if should_suggest else None,
    )
