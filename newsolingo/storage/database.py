"""SQLite database setup and connection management."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default database location
DEFAULT_DB_PATH = Path("newsolingo.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS languages (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    current_level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    language_code TEXT NOT NULL,
    source_name TEXT,
    subject TEXT,
    original_url TEXT UNIQUE,
    original_text TEXT,
    adapted_text TEXT,
    adapted_level TEXT,
    vocabulary_json TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (language_code) REFERENCES languages(code)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    language_code TEXT NOT NULL,
    article_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    translation_score REAL,
    questions_score REAL,
    overall_score REAL,
    feedback_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (language_code) REFERENCES languages(code),
    FOREIGN KEY (article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS question_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    question_text TEXT,
    user_answer TEXT,
    score REAL,
    feedback TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""


class Database:
    """SQLite database wrapper for Newsolingo."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Language operations ---

    def upsert_language(self, code: str, name: str, level: str) -> None:
        """Insert or update a language entry."""
        self.conn.execute(
            """INSERT INTO languages (code, name, current_level)
               VALUES (?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET name=excluded.name, current_level=excluded.current_level""",
            (code, name, level),
        )
        self.conn.commit()

    def update_language_level(self, code: str, level: str) -> None:
        """Update the current level for a language."""
        self.conn.execute(
            "UPDATE languages SET current_level = ? WHERE code = ?",
            (level, code),
        )
        self.conn.commit()

    # --- Article operations ---

    def save_article(
        self,
        language_code: str,
        source_name: str,
        subject: str,
        original_url: str,
        original_text: str,
        adapted_text: str | None = None,
        adapted_level: str | None = None,
        vocabulary: list[dict[str, str]] | None = None,
    ) -> int:
        """Save an article and return its ID."""
        vocab_json = json.dumps(vocabulary, ensure_ascii=False) if vocabulary else None
        cursor = self.conn.execute(
            """INSERT INTO articles
               (language_code, source_name, subject, original_url, original_text,
                adapted_text, adapted_level, vocabulary_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                language_code,
                source_name,
                subject,
                original_url,
                original_text,
                adapted_text,
                adapted_level,
                vocab_json,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def update_article_adaptation(
        self,
        article_id: int,
        adapted_text: str,
        adapted_level: str,
        vocabulary: list[dict[str, str]] | None = None,
    ) -> None:
        """Update an article with its adapted version."""
        vocab_json = json.dumps(vocabulary, ensure_ascii=False) if vocabulary else None
        self.conn.execute(
            """UPDATE articles SET adapted_text = ?, adapted_level = ?, vocabulary_json = ?
               WHERE id = ?""",
            (adapted_text, adapted_level, vocab_json, article_id),
        )
        self.conn.commit()

    def get_article(self, article_id: int) -> dict[str, Any] | None:
        """Get an article by ID."""
        row = self.conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_unused_article(
        self, language_code: str, subject: str | None = None
    ) -> dict[str, Any] | None:
        """Get a cached article that hasn't been used in a session yet."""
        query = """
            SELECT a.* FROM articles a
            LEFT JOIN sessions s ON a.id = s.article_id
            WHERE a.language_code = ? AND s.id IS NULL
        """
        params: list[Any] = [language_code]
        if subject:
            query += " AND a.subject = ?"
            params.append(subject)
        query += " ORDER BY RANDOM() LIMIT 1"

        row = self.conn.execute(query, params).fetchone()
        return dict(row) if row else None

    # --- Session operations ---

    def create_session(
        self,
        language_code: str,
        article_id: int,
        level: str,
    ) -> int:
        """Create a new practice session and return its ID."""
        cursor = self.conn.execute(
            """INSERT INTO sessions (language_code, article_id, level)
               VALUES (?, ?, ?)""",
            (language_code, article_id, level),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def update_session_scores(
        self,
        session_id: int,
        translation_score: float,
        questions_score: float,
        overall_score: float,
        feedback: dict[str, Any] | None = None,
    ) -> None:
        """Update session with final scores."""
        feedback_json = json.dumps(feedback, ensure_ascii=False) if feedback else None
        self.conn.execute(
            """UPDATE sessions
               SET translation_score = ?, questions_score = ?, overall_score = ?,
                   feedback_json = ?
               WHERE id = ?""",
            (
                translation_score,
                questions_score,
                overall_score,
                feedback_json,
                session_id,
            ),
        )
        self.conn.commit()

    def save_question_response(
        self,
        session_id: int,
        question_text: str,
        user_answer: str,
        score: float,
        feedback: str,
    ) -> int:
        """Save a question response and return its ID."""
        cursor = self.conn.execute(
            """INSERT INTO question_responses
               (session_id, question_text, user_answer, score, feedback)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, question_text, user_answer, score, feedback),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # --- Progress queries ---

    def get_recent_sessions(
        self, language_code: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent sessions for a language."""
        rows = self.conn.execute(
            """SELECT s.*, a.source_name, a.subject, a.original_url
               FROM sessions s
               JOIN articles a ON s.article_id = a.id
               WHERE s.language_code = ?
               ORDER BY s.created_at DESC
               LIMIT ?""",
            (language_code, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_rolling_average(
        self, language_code: str, num_sessions: int = 10
    ) -> float | None:
        """Get the rolling average overall score for recent sessions."""
        row = self.conn.execute(
            """SELECT AVG(overall_score) as avg_score
               FROM (
                   SELECT overall_score FROM sessions
                   WHERE language_code = ? AND overall_score IS NOT NULL
                   ORDER BY created_at DESC
                   LIMIT ?
               )""",
            (language_code, num_sessions),
        ).fetchone()
        if row and row["avg_score"] is not None:
            return float(row["avg_score"])
        return None

    def get_session_count(self, language_code: str) -> int:
        """Get total number of completed sessions for a language."""
        row = self.conn.execute(
            """SELECT COUNT(*) as count FROM sessions
               WHERE language_code = ? AND overall_score IS NOT NULL""",
            (language_code,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def get_all_sessions_stats(self, language_code: str) -> dict[str, Any]:
        """Get aggregate statistics for a language."""
        row = self.conn.execute(
            """SELECT
                COUNT(*) as total_sessions,
                AVG(overall_score) as avg_score,
                MIN(overall_score) as min_score,
                MAX(overall_score) as max_score,
                AVG(translation_score) as avg_translation,
                AVG(questions_score) as avg_questions,
                MIN(created_at) as first_session,
                MAX(created_at) as last_session
               FROM sessions
               WHERE language_code = ? AND overall_score IS NOT NULL""",
            (language_code,),
        ).fetchone()
        return dict(row) if row else {}
