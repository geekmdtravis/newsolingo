"""Configuration loading and validation using Pydantic."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

# CEFR levels in order, including pre-A1 for absolute beginners
CEFR_LEVELS = ["pre-A1a", "pre-A1b", "A1", "A2", "B1", "B2", "C1", "C2"]


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


def get_xdg_config_dir() -> Path:
    """Return the XDG config directory for newsolingo.

    Follows XDG Base Directory Specification:
    - $XDG_CONFIG_HOME (default: ~/.config)
    - Creates newsolingo subdirectory
    """
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if not config_home:
        config_home = Path.home() / ".config"
    else:
        config_home = Path(config_home)

    app_dir = config_home / "newsolingo"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_xdg_config_path() -> Path:
    """Return the path to the user's config.yaml in XDG config directory."""
    return get_xdg_config_dir() / "config.yaml"


def get_default_config_template() -> str:
    """Generate a default config template with comments and placeholders."""
    return """# Newsolingo Configuration
# This file should be placed in ~/.config/newsolingo/config.yaml

user:
  # Name displayed in the CLI. Uses $USER environment variable if not set.
  name: "${USER}"

# Add languages you want to practice. Each language needs:
# - code: short identifier (e.g., 'pt_br', 'es', 'fr')
# - name: display name
# - level: CEFR level (pre-A1a, pre-A1b, A1, A2, B1, B2, C1, C2)
# - subjects: list of topics you're interested in
# Example:
# pt_br:
#   name: "Brazilian Portuguese"
#   level: "A2"
#   subjects:
#     - linux
#     - programming
#     - geopolitics
languages: {}

llm:
  # Which provider to use: "llamacpp", "openrouter", or "deepseek"
  provider: "deepseek"

  llamacpp:
    base_url: "http://127.0.0.1:8089/v1"
    # Model name reported by your llama.cpp server (often ignored but required by API)
    model: "local-model"

  openrouter:
    # Set OPENROUTER_API_KEY environment variable or put key here
    api_key: "${OPENROUTER_API_KEY}"
    model: "minimax/minimax-m2.5:free"

  deepseek:
    # Set DEEPSEEK_API_KEY environment variable or put key here
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"

advancement:
  # Suggest level advancement when rolling average exceeds this score (0-100)
  threshold_score: 80
  # Minimum number of completed sessions before suggesting advancement
  min_sessions: 10

exercise:
  # Number of comprehension questions per session
  num_questions: 4
  # Maximum length of adapted text in characters (to keep exercises manageable)
  max_adapted_length: 2000
"""


def ensure_config_exists() -> Path:
    """Ensure a config file exists in XDG location.

    If no config exists, creates one from template.
    Returns path to the config file.
    """
    config_path = get_xdg_config_path()
    if not config_path.exists():
        config_dir = config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)
        template = get_default_config_template()
        config_path.write_text(template, encoding="utf-8")
    return config_path


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

    @field_validator("name", mode="before")
    @classmethod
    def set_default_name(cls, v: str | None) -> str:
        """Set default name from environment variable if not specified."""
        if v is None or v == "Learner":
            return os.environ.get("USER", "Learner")
        return v


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
    2. XDG config directory (~/.config/newsolingo/config.yaml)
    3. ./config.yaml (current directory) - legacy location

    If no config file exists, creates a template in XDG location.
    """
    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    else:
        # Ensure XDG config exists (creates template if missing)
        xdg_config = ensure_config_exists()
        search_paths.append(xdg_config)

    # Add legacy paths for backward compatibility
    search_paths.extend(
        [
            Path("config.yaml"),
        ]
    )

    for path in search_paths:
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f)
            if raw is None:
                raw = {}
            expanded = _expand_env_vars(raw)
            config = AppConfig(**expanded)
            # Set default username from environment if not specified
            if config.user.name == "Learner":
                config.user.name = os.environ.get("USER", "Learner")
            return config

    # Should not reach here because ensure_config_exists creates a config
    # But fallback to defaults for safety
    config = AppConfig()
    config.user.name = os.environ.get("USER", "Learner")
    return config
