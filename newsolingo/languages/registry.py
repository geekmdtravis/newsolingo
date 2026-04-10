"""Language registry for extensible language support."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LanguageInfo:
    """Metadata about a supported language."""

    code: str
    name: str
    native_name: str
    script: str  # "latin", "arabic", "cyrillic", etc.
    direction: str  # "ltr" or "rtl"


# Built-in language definitions
LANGUAGES: dict[str, LanguageInfo] = {
    "pt_br": LanguageInfo(
        code="pt_br",
        name="Brazilian Portuguese",
        native_name="Portugu\u00eas Brasileiro",
        script="latin",
        direction="ltr",
    ),
}


def get_language_info(code: str) -> LanguageInfo | None:
    """Get language info by code."""
    return LANGUAGES.get(code)


def list_languages() -> list[LanguageInfo]:
    """List all supported languages."""
    return list(LANGUAGES.values())


def register_language(info: LanguageInfo) -> None:
    """Register a new language. Call this to add custom languages at runtime."""
    LANGUAGES[info.code] = info
