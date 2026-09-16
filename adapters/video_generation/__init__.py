"""Provider-neutral video generation adapters."""

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult, normalize_image_paths
from .local_ken_burns import LocalKenBurnsVideo
from .router import VIDEO_GENERATION_PROVIDER_PRIORITY, choose_video_generation_provider

__all__ = [
    "LocalKenBurnsVideo",
    "VIDEO_GENERATION_PROVIDER_PRIORITY",
    "VideoGenerationError",
    "VideoGenerationProvider",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "choose_video_generation_provider",
    "normalize_image_paths",
]
