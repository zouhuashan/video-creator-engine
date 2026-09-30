"""Historical Sora provider identity; no requests after API retirement.

Keep constructor compatibility for archived configurations. Both API-key and
keyless calls fail locally before reading media or contacting any service.
"""

from __future__ import annotations

import os
import time
import urllib.request
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class OpenAISoraVideo(VideoGenerationProvider):
    name = "openai_sora"
    remote_generation = True
    api_url = "https://api.openai.com/v1"
    allowed_models = {"sora-2", "sora-2-pro"}
    allowed_seconds = (4, 8, 12)
    allowed_sizes = {"720x1280", "1280x720", "1024x1792", "1792x1024"}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        opener: Callable[..., object] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        poll_interval_seconds: float = 5.0,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.opener = opener
        self.sleeper = sleeper
        self.poll_interval_seconds = poll_interval_seconds

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        raise VideoGenerationError("OpenAI Sora Videos API 已于 2026-09-24 关闭；此适配器仅保留历史兼容，不再提交生成任务")
