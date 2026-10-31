"""Error types raised by fontmerge modules.

Every error carries a plain-language ``message`` and an optional ``hint`` telling the
user how to fix it. The CLI prints both; library callers can catch ``FontMergeError``.
"""

from __future__ import annotations


class FontMergeError(Exception):
    """Base class for every error fontmerge raises on purpose."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message} ({self.hint})"
        return self.message


class ConfigError(FontMergeError):
    """The merge configuration is invalid or inconsistent."""


class FontLoadError(FontMergeError):
    """A font file could not be opened or parsed."""


class UnsupportedFontError(FontMergeError):
    """The font opened, but uses a feature fontmerge does not support (e.g. variable)."""


class RoutingError(FontMergeError):
    """Codepoints could not be assigned to a source font."""


class GlyphLimitError(FontMergeError):
    """The merged font would exceed the OpenType limit of 65,535 glyphs."""


class MergeFailedError(FontMergeError):
    """Combining the prepared fonts failed."""


class ValidationFailedError(FontMergeError):
    """The merged font has error-level validation issues."""
