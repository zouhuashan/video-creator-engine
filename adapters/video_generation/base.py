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
    prompt_text: str = ""
    model: str = "gen4.5"
    reference_video_paths: tuple[Path, ...] = ()
    reference_audio_paths: tuple[Path, ...] = ()

    def validate(self) -> None:
        if not self.image_paths and not self.reference_video_paths and not self.reference_audio_paths:
            raise VideoGenerationError("at least one image, reference video, or reference audio is required")
        if any(not Path(path).is_file() for path in self.image_paths):
            raise VideoGenerationError("every input image must exist")
        if any(not Path(path).is_file() for path in self.reference_video_paths):
            raise VideoGenerationError("every reference video must exist")
        if any(not Path(path).is_file() for path in self.reference_audio_paths):
            raise VideoGenerationError("every reference audio file must exist")
        if self.output_path.suffix.lower() != ".mp4":
            raise VideoGenerationError("output must be an .mp4 file")
        if self.shot_duration_seconds <= 0 or self.fps <= 0:
            raise VideoGenerationError("duration and fps must be positive")
        if self.width <= 0 or self.height <= 0:
            raise VideoGenerationError("video dimensions must be positive")
        if self.transition_seconds < 0 or self.transition_seconds >= self.shot_duration_seconds:
            raise VideoGenerationError("transition must be non-negative and shorter than a shot")
        if not isinstance(self.prompt_text, str):
            raise VideoGenerationError("prompt text must be a string")
        if not isinstance(self.model, str) or not self.model.strip():
            raise VideoGenerationError("model must be a non-empty string")


@dataclass(frozen=True)
class VideoGenerationResult:
    output_path: Path
    provider: str
    duration_seconds: float
    image_count: int
    remote_generation: bool = False
    task_id: str | None = None


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
