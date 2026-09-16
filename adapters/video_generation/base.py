"""Provider-neutral image-to-video generation contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class VideoGenerationError(RuntimeError):
    """Raised when a video-generation request cannot be fulfilled."""


@dataclass(frozen=True)
class VideoGenerationRequest:
    image_paths: tuple[Path, ...]
    output_path: Path
    shot_duration_seconds: float = 3.0
    fps: int = 30
    width: int = 1080
    height: int = 1920
    transition_seconds: float = 0.4

    def validate(self) -> None:
        if not self.image_paths:
            raise VideoGenerationError("at least one image is required")
        if any(not Path(path).is_file() for path in self.image_paths):
            raise VideoGenerationError("every input image must exist")
        if self.output_path.suffix.lower() != ".mp4":
            raise VideoGenerationError("output must be an .mp4 file")
        if self.shot_duration_seconds <= 0 or self.fps <= 0:
            raise VideoGenerationError("duration and fps must be positive")
        if self.width <= 0 or self.height <= 0:
            raise VideoGenerationError("video dimensions must be positive")
        if self.transition_seconds < 0 or self.transition_seconds >= self.shot_duration_seconds:
            raise VideoGenerationError("transition must be non-negative and shorter than a shot")


@dataclass(frozen=True)
class VideoGenerationResult:
    output_path: Path
    provider: str
    duration_seconds: float
    image_count: int
    remote_generation: bool = False


class VideoGenerationProvider(ABC):
    name: str
    remote_generation: bool

    @abstractmethod
    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Generate a video from one or more image keyframes."""


def normalize_image_paths(image_paths: Sequence[Path | str]) -> tuple[Path, ...]:
    normalized = tuple(Path(path).expanduser().resolve() for path in image_paths)
    if not normalized:
        raise VideoGenerationError("at least one image is required")
    return normalized
