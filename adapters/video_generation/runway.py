"""Runway Gen-4.5 image-to-video adapter.

The adapter uses the documented REST API and never uploads unless an API key is
explicitly supplied by the caller or RUNWAY_API_KEY is present in the process
environment.
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


class RunwayImageToVideo(VideoGenerationProvider):
    name = "runway"
    remote_generation = True
    api_url = "https://api.dev.runwayml.com/v1"
    api_version = "2024-11-06"

    def __init__(self, *, api_key: str | None = None, opener: Callable[..., object] = urllib.request.urlopen, sleeper: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("RUNWAY_API_KEY") or os.environ.get("RUNWAYML_API_SECRET")
        self.opener = opener
        self.sleeper = sleeper

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if not self.api_key:
            raise VideoGenerationError("RUNWAY_API_KEY is required for the Runway provider")
        if len(request.image_paths) != 1:
            raise VideoGenerationError("Runway image-to-video currently accepts one keyframe per task")
        payload = {
            "model": request.model,
            "promptImage": self._data_uri(request.image_paths[0]),
            "promptText": request.prompt_text or "Subtle natural motion, cinematic camera movement, preserve the character design.",
            "ratio": "768:1280" if request.height >= request.width else "1280:768",
            "duration": 5,
        }
        task = self._request("POST", "/image_to_video", payload)
        task_id = task.get("id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise VideoGenerationError("Runway response did not include a task id")
        result = self._wait_for_task(task_id)
        output_url = (result.get("output") or [None])[0]
        if not isinstance(output_url, str) or not output_url.startswith("http"):
            raise VideoGenerationError("Runway task completed without a downloadable output")
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.opener(output_url) as response:
                output.write_bytes(response.read())
        except Exception as error:
            raise VideoGenerationError("Runway output download failed") from error
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("Runway output is empty")
        return VideoGenerationResult(output, self.name, 5.0, 1, True, task_id)

    def _data_uri(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(self.api_url + endpoint, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}",
            "X-Runway-Version": self.api_version,
            "Content-Type": "application/json",
        })
        try:
            with self.opener(request) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise VideoGenerationError(f"Runway API request failed: {endpoint}") from error
        if not isinstance(parsed, dict):
            raise VideoGenerationError("Runway API returned a non-object response")
        return parsed

    def _wait_for_task(self, task_id: str) -> dict:
        for _ in range(60):
            task = self._request("GET", f"/tasks/{task_id}")
            status = task.get("status")
            if status == "SUCCEEDED":
                return task
            if status in {"FAILED", "CANCELED"}:
                raise VideoGenerationError(f"Runway task {status.lower()}: {task.get('failure') or task.get('failureCode') or 'unknown error'}")
            self.sleeper(5)
        raise VideoGenerationError("Runway task timed out after 5 minutes")
