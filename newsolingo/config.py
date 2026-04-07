"""Configuration loading and validation using Pydantic."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator


# CEFR levels in order, including pre-A1 for absolute beginners
CEFR_LEVELS = ["pre-A1", "A1", "A2", "B1", "B2", "C1", "C2"]


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} environment variable references in strings."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{(\w+)\}")

        def replacer(match: re.Match) -> str:
            return os.environ.get(match.group(1), match.group(0))

        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


class LanguageConfig(BaseModel):
    """Configuration for a single language."""

    name: str
    level: str
    subjects: list[str]

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v not in CEFR_LEVELS:
            raise ValueError(f"Invalid CEFR level '{v}'. Must be one of: {CEFR_LEVELS}")
        return v


class LlamaCppConfig(BaseModel):
    """Configuration for llama.cpp provider."""

    base_url: str = "http://127.0.0.1:8089/v1"
    model: str = "local-model"


class DeepSeekConfig(BaseModel):
    """Configuration for DeepSeek provider."""

    api_key: str = ""
    model: str = "deepseek-chat"


class OpenRouterConfig(BaseModel):
    """Configuration for OpenRouter provider."""

    api_key: str = ""
    model: str = "anthropic/claude-sonnet-4"


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "llamacpp"
    llamacpp: LlamaCppConfig = LlamaCppConfig()
    openrouter: OpenRouterConfig = OpenRouterConfig()
    deepseek: DeepSeekConfig = DeepSeekConfig()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ("llamacpp", "openrouter", "deepseek"):
            raise ValueError(
                f"Invalid LLM provider '{v}'. Must be 'llamacpp', 'openrouter', or 'deepseek'."
            )
        return v


class AdvancementConfig(BaseModel):
    """Level advancement configuration."""

    threshold_score: float = 80.0
    min_sessions: int = 10


class ExerciseConfig(BaseModel):
    """Exercise generation configuration."""

    num_questions: int = 4
    max_adapted_length: int = 2000


class UserConfig(BaseModel):
    """User information."""

    name: str = "Learner"


class AppConfig(BaseModel):
    """Top-level application configuration."""

    user: UserConfig = UserConfig()
    languages: dict[str, LanguageConfig] = {}
    llm: LLMConfig = LLMConfig()
    advancement: AdvancementConfig = AdvancementConfig()
    exercise: ExerciseConfig = ExerciseConfig()

    def get_language(self, code: str) -> LanguageConfig:
        """Get language config by code, raising if not found."""
        if code not in self.languages:
            available = ", ".join(self.languages.keys())
            raise KeyError(f"Language '{code}' not configured. Available: {available}")
        return self.languages[code]

    def next_level(self, current_level: str) -> str | None:
        """Return the next CEFR level, or None if already at C2."""
        try:
            idx = CEFR_LEVELS.index(current_level)
        except ValueError:
            return None
        if idx + 1 < len(CEFR_LEVELS):
            return CEFR_LEVELS[idx + 1]
        return None


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file.

    Searches in this order:
    1. Explicit path if provided
    2. ./config.yaml (current directory)
    3. ~/.config/newsolingo/config.yaml
    """
    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    search_paths.extend(
        [
            Path("config.yaml"),
            Path.home() / ".config" / "newsolingo" / "config.yaml",
        ]
    )

    for path in search_paths:
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f)
            if raw is None:
                raw = {}
            expanded = _expand_env_vars(raw)
            return AppConfig(**expanded)

    # No config file found - use defaults
    return AppConfig()
