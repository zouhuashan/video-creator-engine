"""Provider-neutral boundary for extracting story entities from authorized text."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class StoryExtractionError(RuntimeError):
    """Raised when an extraction request is invalid or cannot be completed."""


@dataclass(frozen=True)
class ChapterText:
    chapter_id: str
    title: str
    text: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class ExtractionResult:
    provider: str
    characters: tuple[dict[str, Any], ...]
    locations: tuple[dict[str, Any], ...]
    props: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]


class StoryExtractionProvider(ABC):
    name: str
    remote_generation: bool

    @abstractmethod
    def extract(self, chapters: tuple[ChapterText, ...], lexicon: dict[str, Any]) -> ExtractionResult:
        """Extract review candidates without persisting the full chapter text."""
