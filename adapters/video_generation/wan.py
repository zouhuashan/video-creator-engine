"""fal.ai Wan 2.1 image-to-video adapter."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class WanImageToVideo(VideoGenerationProvider):
    name = "wan"
    remote_generation = True
    queue_url = "https://queue.fal.run/fal-ai/wan-i2v"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        opener: Callable[..., object] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        poll_interval_seconds: float = 2.0,
    ):
        self.api_key = api_key or os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
        self.opener = opener
        self.sleeper = sleeper
        self.poll_interval_seconds = poll_interval_seconds

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if request.reference_video_paths or request.reference_audio_paths:
            raise VideoGenerationError("Wan image-to-video adapter does not accept reference video/audio")
        if not self.api_key:
            raise VideoGenerationError("FAL_KEY is required for the Wan provider")
        if len(request.image_paths) != 1:
            raise VideoGenerationError("Wan image-to-video currently accepts one keyframe per task")
        resolution = "720p" if max(request.width, request.height) >= 1080 else "480p"
        payload = {
            "image_url": self._data_uri(request.image_paths[0]),
            "prompt": request.prompt_text or "Subtle natural motion, preserve the character and scene design.",
            "num_frames": 81,
            "frames_per_second": 16,
            "resolution": resolution,
            "aspect_ratio": "9:16" if request.height >= request.width else "16:9",
        }
        created, headers = self._request("POST", self.queue_url, payload)
        request_id = created.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise VideoGenerationError("Wan response did not include a request id")
        status_url = created.get("status_url") or f"{self.queue_url}/requests/{request_id}/status"
        response_url = created.get("response_url") or f"{self.queue_url}/requests/{request_id}"
        self._wait_for_request(status_url, headers)
        result, _ = self._request("GET", response_url, None, headers=headers)
        video_url = self._video_url(result)
        if not video_url:
            raise VideoGenerationError("Wan task completed without a downloadable output")
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.opener(video_url) as response:
                output.write_bytes(response.read())
        except Exception as error:
            raise VideoGenerationError("Wan video output download failed") from error
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("Wan video output is empty")
        return VideoGenerationResult(output, self.name, 5.0, 1, True, request_id)

    def _data_uri(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def _request(self, method: str, url: str, payload: dict | None, *, headers: dict | None = None) -> tuple[dict, dict]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Authorization": f"Key {self.api_key}", "Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with self.opener(request) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise VideoGenerationError(f"Wan API request failed: {url}") from error
        if not isinstance(parsed, dict):
            raise VideoGenerationError("Wan API returned a non-object response")
        return parsed, {}

    def _wait_for_request(self, status_url: str, headers: dict) -> None:
        for _ in range(90):
            status, _ = self._request("GET", status_url, None, headers=headers)
            state = status.get("status")
            if state in {"COMPLETED", "completed"}:
                return
            if state in {"FAILED", "CANCELED", "failed", "canceled"}:
                raise VideoGenerationError(f"Wan task {str(state).lower()}: {status.get('error') or 'unknown error'}")
            self.sleeper(self.poll_interval_seconds)
        raise VideoGenerationError("Wan video task timed out after 3 minutes")

    def _video_url(self, result: dict) -> str | None:
        video = result.get("video")
        if isinstance(video, dict) and isinstance(video.get("url"), str):
            return video["url"]
        if isinstance(result.get("video_url"), str):
            return result["video_url"]
        return None
