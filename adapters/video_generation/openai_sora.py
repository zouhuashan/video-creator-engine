"""OpenAI Sora image-to-video adapter.

The adapter keeps the Sora Videos API behind the provider-neutral contract.  It
uses the REST API directly so the project does not require the OpenAI SDK just
to run the provider.  A key must be explicitly present before any image is
uploaded or billable generation is started.
"""

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
        request.validate()
        if request.reference_video_paths or request.reference_audio_paths:
            raise VideoGenerationError("OpenAI Sora adapter does not accept reference video/audio in this contract")
        if not self.api_key:
            raise VideoGenerationError("OPENAI_API_KEY is required for the OpenAI Sora provider")
        if len(request.image_paths) > 1:
            raise VideoGenerationError("OpenAI Sora image-to-video currently accepts one reference image per task")
        # ``gen4.5`` is the historical contract default; treat it as an
        # unspecified model when callers switch providers.
        model = "sora-2" if request.model == "gen4.5" else (request.model or "sora-2")
        if model not in self.allowed_models:
            raise VideoGenerationError(f"unsupported OpenAI video model: {model}")
        seconds = self._seconds(request.shot_duration_seconds)
        payload = {
            "model": model,
            "prompt": request.prompt_text or "Subtle natural motion, preserve the character and scene design.",
            "seconds": str(seconds),
            "size": self._size(request.width, request.height),
        }
        if request.image_paths:
            payload["input_reference"] = {"image_url": self._data_uri(request.image_paths[0])}
        created = self._request("POST", "/videos", payload)
        video_id = created.get("id") if isinstance(created, dict) else None
        if not isinstance(video_id, str) or not video_id:
            raise VideoGenerationError("OpenAI video response did not include a video id")
        result = self._wait_for_video(video_id)
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.opener(self._request_obj("GET", f"/videos/{video_id}/content")) as response:
                output.write_bytes(response.read())
        except Exception as error:
            raise VideoGenerationError("OpenAI video output download failed") from error
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("OpenAI video output is empty")
        return VideoGenerationResult(output, self.name, float(result.get("seconds") or seconds), 1, True, video_id)

    def _seconds(self, requested: float) -> int:
        return min(self.allowed_seconds, key=lambda value: abs(value - requested))

    def _size(self, width: int, height: int) -> str:
        if height >= width:
            return "720x1280" if height / max(width, 1) >= 1.4 else "1024x1792"
        return "1280x720" if width / max(height, 1) >= 1.4 else "1792x1024"

    def _data_uri(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def _request_obj(self, method: str, endpoint: str, payload: dict | None = None) -> urllib.request.Request:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(self.api_url + endpoint, data=data, method=method, headers=headers)

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        try:
            with self.opener(self._request_obj(method, endpoint, payload)) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise VideoGenerationError(f"OpenAI video API request failed: {endpoint}") from error
        if not isinstance(parsed, dict):
            raise VideoGenerationError("OpenAI video API returned a non-object response")
        return parsed

    def _wait_for_video(self, video_id: str) -> dict:
        for _ in range(60):
            video = self._request("GET", f"/videos/{video_id}")
            status = video.get("status")
            if status == "completed":
                return video
            if status == "failed":
                error = video.get("error") or {}
                detail = error.get("message") if isinstance(error, dict) else error
                raise VideoGenerationError(f"OpenAI video generation failed: {detail or 'unknown error'}")
            self.sleeper(self.poll_interval_seconds)
        raise VideoGenerationError("OpenAI video task timed out after 5 minutes")
