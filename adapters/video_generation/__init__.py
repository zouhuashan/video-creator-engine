"""Provider-neutral video generation adapters."""

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult, normalize_image_paths
from .local_ken_burns import LocalKenBurnsVideo
from .local_micro_motion import LocalMicroMotionVideo
from .local_scene_plate import LocalScenePlateVideo
from .local_two_cut import LocalTwoCutVideo
from .minimax_h3 import MiniMaxH3Video
from .openai_sora import OpenAISoraVideo
from .runway import RunwayImageToVideo
from .router import VIDEO_GENERATION_PROVIDER_PRIORITY, choose_video_generation_provider
from .wan import WanImageToVideo

__all__ = [
    "LocalKenBurnsVideo",
    "LocalMicroMotionVideo",
    "LocalScenePlateVideo",
    "LocalTwoCutVideo",
    "MiniMaxH3Video",
    "OpenAISoraVideo",
    "RunwayImageToVideo",
    "WanImageToVideo",
    "VIDEO_GENERATION_PROVIDER_PRIORITY",
    "VideoGenerationError",
    "VideoGenerationProvider",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "choose_video_generation_provider",
    "normalize_image_paths",
]
