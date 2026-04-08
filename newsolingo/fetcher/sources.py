"""Source registry - loads and manages content sources from YAML files."""

from __future__ import annotations

import logging
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def get_xdg_data_dir() -> Path:
    """Return the XDG data directory for newsolingo.

    Follows XDG Base Directory Specification:
    - $XDG_DATA_HOME (default: ~/.local/share)
    - Creates newsolingo subdirectory
    """
    data_home = os.environ.get("XDG_DATA_HOME")
    if not data_home:
        data_home = Path.home() / ".local" / "share"
    else:
        data_home = Path(data_home)

    app_dir = data_home / "newsolingo"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_xdg_sources_dir() -> Path:
    """Return the XDG sources directory for newsolingo."""
    return get_xdg_data_dir() / "sources"


def get_package_sources_dir() -> Path:
    """Return the sources directory in the package (repo default sources)."""
    return Path(__file__).parent.parent.parent / "sources"


def ensure_default_sources() -> None:
    """Copy default sources from package to XDG directory if they don't exist."""
    xdg_sources = get_xdg_sources_dir()
    package_sources = get_package_sources_dir()

    if xdg_sources.exists() and any(xdg_sources.glob("*.yaml")):
        return

    if not package_sources.exists():
        logger.warning("Package sources directory not found: %s", package_sources)
        return

    xdg_sources.mkdir(parents=True, exist_ok=True)

    for yaml_file in package_sources.glob("*.yaml"):
        dest = xdg_sources / yaml_file.name
        if not dest.exists():
            shutil.copy2(yaml_file, dest)
            logger.info("Copied default sources: %s -> %s", yaml_file, dest)


# Look for sources directory relative to the project root
SOURCES_DIR = Path(__file__).parent.parent.parent / "sources"


@dataclass
class Source:
    """A content source (website) for a specific language and subject."""

    url: str
    name: str
    type: str
    description: str = ""


@dataclass
class SourceRegistry:
    """Registry of all available sources organized by language and subject."""

    sources: dict[str, dict[str, list[Source]]]  # {lang_code: {subject: [Source]}}

    def get_subjects(self, language_code: str) -> list[str]:
        """Get available subjects for a language."""
        lang_sources = self.sources.get(language_code, {})
        return list(lang_sources.keys())

    def get_sources(self, language_code: str, subject: str) -> list[Source]:
        """Get sources for a specific language and subject."""
        return self.sources.get(language_code, {}).get(subject, [])

    def pick_random_source(
        self, language_code: str, subject: str | None = None
    ) -> tuple[Source, str] | None:
        """Pick a random source, optionally filtered by subject.

        Returns:
            Tuple of (Source, subject_name) or None if no sources available.
        """
        lang_sources = self.sources.get(language_code, {})
        if not lang_sources:
            logger.warning("No sources found for language '%s'", language_code)
            return None

        if subject:
            sources = lang_sources.get(subject, [])
            if not sources:
                logger.warning(
                    "No sources for language '%s', subject '%s'",
                    language_code,
                    subject,
                )
                return None
            return random.choice(sources), subject
        else:
            # Pick a random subject, then a random source within it
            available_subjects = [s for s, srcs in lang_sources.items() if srcs]
            if not available_subjects:
                return None
            chosen_subject = random.choice(available_subjects)
            return random.choice(lang_sources[chosen_subject]), chosen_subject


def load_sources(sources_dir: Path | None = None) -> SourceRegistry:
    """Load all source YAML files from the sources directory.

    Each YAML file is named after the language code (e.g., pt_br.yaml, he.yaml).

    If sources_dir is not provided, uses XDG data directory and copies
    default sources from the package if they don't exist.
    """
    if sources_dir is None:
        ensure_default_sources()
        directory = get_xdg_sources_dir()
    else:
        directory = sources_dir

    sources: dict[str, dict[str, list[Source]]] = {}

    if not directory.exists():
        logger.warning("Sources directory not found at %s", directory)
        return SourceRegistry(sources={})

    for yaml_file in sorted(directory.glob("*.yaml")):
        lang_code = yaml_file.stem  # e.g., "pt_br" from "pt_br.yaml"
        logger.debug("Loading sources for '%s' from %s", lang_code, yaml_file)

        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        if not data or "subjects" not in data:
            logger.warning("Invalid source file: %s", yaml_file)
            continue

        lang_sources: dict[str, list[Source]] = {}
        for subject_name, source_list in data["subjects"].items():
            lang_sources[subject_name] = [
                Source(
                    url=s["url"],
                    name=s["name"],
                    type=s.get("type", "unknown"),
                    description=s.get("description", ""),
                )
                for s in source_list
            ]

        sources[lang_code] = lang_sources
        logger.info(
            "Loaded %d subjects with %d total sources for '%s'",
            len(lang_sources),
            sum(len(v) for v in lang_sources.values()),
            lang_code,
        )

    return SourceRegistry(sources=sources)
