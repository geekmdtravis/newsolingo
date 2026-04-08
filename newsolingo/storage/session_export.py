"""Export sessions to human-readable Markdown files for review.

This module handles:
- Converting SessionResult objects to Markdown with YAML frontmatter
- Saving sessions to disk in the XDG data directory
- Listing and loading saved sessions
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from newsolingo.storage.database import get_xdg_data_dir
from newsolingo.storage.models import (
    SessionResult,
    AdaptedArticle,
    VocabularyItem,
    TranslationAssessment,
    QuestionItem,
    AnswerAssessment,
)

logger = logging.getLogger(__name__)


def get_sessions_dir() -> Path:
    """Return the sessions directory within XDG data directory."""
    return get_xdg_data_dir() / "sessions"


def ensure_sessions_dir() -> Path:
    """Create the sessions directory if it doesn't exist."""
    sessions_dir = get_sessions_dir()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def _escape_yaml_value(value: Any) -> str:
    """Escape a value for YAML frontmatter."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    # String: escape newlines and quotes
    escaped = str(value).replace("\n", "\\n").replace('"', '\\"')
    if (
        ":" in escaped
        or "[" in escaped
        or "]" in escaped
        or "{" in escaped
        or "}" in escaped
    ):
        return f'"{escaped}"'
    return escaped


def session_to_markdown(session: SessionResult) -> str:
    """Convert a SessionResult to Markdown with YAML frontmatter."""

    # Build YAML frontmatter
    frontmatter_lines = [
        "---",
        f"id: {session.session_id}",
        f"language_code: {session.language_code}",
        f"level: {session.level}",
        f"ignore_accents: {str(session.ignore_accents).lower()}",
        f"translation_score: {session.translation_score:.1f}",
        f"questions_score: {session.questions_score:.1f}",
        f"overall_score: {session.overall_score:.1f}",
        f"created_at: {datetime.now().isoformat()}",
    ]

    # Article metadata
    article = session.article
    frontmatter_lines.extend(
        [
            f"article_source: {_escape_yaml_value(article.source_name)}",
            f"article_subject: {_escape_yaml_value(article.subject)}",
            f"article_level: {_escape_yaml_value(article.level)}",
            f"article_url: {_escape_yaml_value(article.original_url)}",
        ]
    )

    frontmatter_lines.append("---")

    # Build Markdown content
    content_lines = []

    # Header
    content_lines.append(f"# Session {session.session_id} Review")
    content_lines.append("")

    # Summary table
    content_lines.append("## Session Summary")
    content_lines.append("")
    content_lines.append(
        f"- **Language**: {session.language_code} (Level: {session.level})"
    )
    content_lines.append(f"- **Overall Score**: {session.overall_score:.1f}/100")
    content_lines.append(
        f"- **Translation Score**: {session.translation_score:.1f}/100"
    )
    content_lines.append(f"- **Questions Score**: {session.questions_score:.1f}/100")
    content_lines.append(f"- **Ignore Accents**: {session.ignore_accents}")
    content_lines.append("")

    # Article section
    content_lines.append("## Article")
    content_lines.append("")
    content_lines.append(f"**Source**: {article.source_name}")
    content_lines.append(f"**Subject**: {article.subject}")
    content_lines.append(f"**Level**: {article.level}")
    if article.original_url:
        content_lines.append(f"**URL**: {article.original_url}")
    content_lines.append("")

    content_lines.append("### Adapted Text")
    content_lines.append("")
    content_lines.append(article.adapted_text)
    content_lines.append("")

    # Vocabulary
    if article.vocabulary:
        content_lines.append("### Vocabulary")
        content_lines.append("")
        for vocab in article.vocabulary:
            content_lines.append(f"- **{vocab.term}**: {vocab.translation}")
            if vocab.context:
                content_lines.append(f"  *Context*: {vocab.context}")
        content_lines.append("")

    # Translation
    content_lines.append("## Translation Exercise")
    content_lines.append("")
    content_lines.append("### User's Translation")
    content_lines.append("")
    if session.user_translation.strip():
        content_lines.append(session.user_translation)
    else:
        content_lines.append("*No translation provided*")
    content_lines.append("")

    content_lines.append("### Assessment")
    content_lines.append("")
    translation = session.translation_assessment
    content_lines.append(f"**Score**: {translation.score:.1f}/100")
    content_lines.append(f"**Accuracy**: {translation.accuracy}")
    content_lines.append(f"**Nuance**: {translation.nuance}")
    content_lines.append(f"**Completeness**: {translation.completeness}")
    content_lines.append(f"**Suggestions**: {translation.suggestions}")
    content_lines.append("")

    if translation.corrected_translation:
        content_lines.append("### Suggested Translation")
        content_lines.append("")
        content_lines.append(translation.corrected_translation)
        content_lines.append("")

    # Questions and Answers
    if session.questions:
        content_lines.append("## Comprehension Questions")
        content_lines.append("")

        for i, (question, user_answer, assessment) in enumerate(
            zip(session.questions, session.user_answers, session.answer_assessments), 1
        ):
            content_lines.append(f"### Question {i}")
            content_lines.append("")
            content_lines.append(f"**Question**: {question.question}")
            if question.expected_answer_hint:
                content_lines.append(
                    f"**Expected Hint**: {question.expected_answer_hint}"
                )
            content_lines.append("")
            content_lines.append(f"**Your Answer**: {user_answer}")
            content_lines.append("")
            content_lines.append(f"**Score**: {assessment.score:.1f}/100")
            content_lines.append(f"**Correctness**: {assessment.correctness}")
            content_lines.append(f"**Grammar**: {assessment.grammar}")
            content_lines.append(f"**Feedback**: {assessment.feedback}")
            content_lines.append("")

    # Join everything
    frontmatter = "\n".join(frontmatter_lines)
    content = "\n".join(content_lines)

    return f"{frontmatter}\n\n{content}"


def save_session_markdown(session: SessionResult, compress: bool = True) -> Path:
    """Save a session as a Markdown file.

    Args:
        session: The session result to save
        compress: If True, compress with gzip when file size > 10KB

    Returns:
        Path to the saved file
    """
    ensure_sessions_dir()

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{session.session_id}_{timestamp}.md"
    filepath = get_sessions_dir() / filename

    # Generate markdown
    markdown = session_to_markdown(session)

    # Write file
    filepath.write_text(markdown, encoding="utf-8")

    # Optionally compress if file is large
    if compress and filepath.stat().st_size > 10 * 1024:  # > 10KB
        compressed_path = filepath.with_suffix(".md.gz")
        with open(filepath, "rb") as f_in:
            with gzip.open(compressed_path, "wb") as f_out:
                f_out.write(f_in.read())
        filepath.unlink()
        filepath = compressed_path

    logger.info("Saved session %d to %s", session.session_id, filepath)
    return filepath


def list_sessions() -> list[dict[str, Any]]:
    """List all saved sessions by parsing YAML frontmatter.

    Returns:
        List of session metadata dictionaries, sorted by creation date (newest first)
    """
    sessions_dir = ensure_sessions_dir()
    sessions = []

    # Regex to extract YAML frontmatter
    frontmatter_re = re.compile(r"^---\n(.*?)\n---", re.DOTALL | re.MULTILINE)
    yaml_line_re = re.compile(r"^([^:]+):\s*(.*)$")

    for filepath in sorted(sessions_dir.glob("session_*.md"), reverse=True):
        try:
            # Read file (handle gzipped files)
            if filepath.suffix == ".gz":
                with gzip.open(filepath, "rt", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = filepath.read_text(encoding="utf-8")

            # Extract frontmatter
            match = frontmatter_re.match(content)
            if not match:
                continue

            frontmatter = match.group(1)
            metadata: dict[str, Any] = {}

            for line in frontmatter.split("\n"):
                line_match = yaml_line_re.match(line.strip())
                if line_match:
                    key = line_match.group(1).strip()
                    value = line_match.group(2).strip()

                    # Parse simple types
                    if value.lower() in ("true", "false"):
                        metadata[key] = value.lower() == "true"
                    elif value.isdigit():
                        metadata[key] = int(value)
                    elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
                        metadata[key] = float(value)
                    elif value.startswith('"') and value.endswith('"'):
                        metadata[key] = (
                            value[1:-1].replace('\\"', '"').replace("\\n", "\n")
                        )
                    else:
                        metadata[key] = value

            # Add file info
            metadata["filename"] = filepath.name
            metadata["filepath"] = str(filepath)
            metadata["compressed"] = filepath.suffix == ".gz"
            sessions.append(metadata)

        except Exception as e:
            logger.warning("Failed to parse session file %s: %s", filepath, e)
            continue

    # Sort by creation date if available, otherwise by filename
    sessions.sort(
        key=lambda x: (
            datetime.fromisoformat(x.get("created_at", "1970-01-01"))
            if "created_at" in x
            else datetime.min,
            x.get("filename", ""),
        ),
        reverse=True,
    )

    return sessions


def load_session_markdown(session_id: int | str) -> str | None:
    """Load the Markdown content of a session.

    Args:
        session_id: Either a numeric session ID or a filename

    Returns:
        Markdown content as string, or None if not found
    """
    sessions_dir = ensure_sessions_dir()

    # If given a filename, load directly
    if isinstance(session_id, str) and (
        session_id.endswith(".md") or session_id.endswith(".md.gz")
    ):
        filepath = sessions_dir / session_id
        if not filepath.exists():
            return None
    else:
        # Find by session ID
        session_files = list(sessions_dir.glob(f"session_{session_id}_*.md")) + list(
            sessions_dir.glob(f"session_{session_id}_*.md.gz")
        )
        if not session_files:
            return None
        # Get most recent
        filepath = max(session_files, key=lambda p: p.stat().st_mtime)

    # Read file
    try:
        if filepath.suffix == ".gz":
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                return f.read()
        else:
            return filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to load session file %s: %s", filepath, e)
        return None


def delete_session_file(session_id: int | str) -> bool:
    """Delete a session file.

    Args:
        session_id: Either a numeric session ID or a filename

    Returns:
        True if file was deleted, False otherwise
    """
    sessions_dir = ensure_sessions_dir()

    if isinstance(session_id, str) and (
        session_id.endswith(".md") or session_id.endswith(".md.gz")
    ):
        filepath = sessions_dir / session_id
    else:
        # Find by session ID
        session_files = list(sessions_dir.glob(f"session_{session_id}_*.md")) + list(
            sessions_dir.glob(f"session_{session_id}_*.md.gz")
        )
        if not session_files:
            return False
        filepath = session_files[0]

    try:
        filepath.unlink()
        logger.info("Deleted session file %s", filepath)
        return True
    except Exception as e:
        logger.error("Failed to delete session file %s: %s", filepath, e)
        return False
