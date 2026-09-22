"""MiniMax H3 reference-to-video adapter for graybox motion transfer."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class MiniMaxH3Video(VideoGenerationProvider):
    name = "minimax_h3"
    remote_generation = True
    api_url = "https://api.minimax.io"
    allowed_models = {"MiniMax-H3", "MiniMax-H3-Max"}
    allowed_resolutions = {"768P", "2K"}
    max_reference_video_bytes = 40 * 1024 * 1024

    def __init__(
        self,
        *,
        api_key: str | None = None,
        opener: Callable[..., object] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        poll_interval_seconds: float = 8.0,
        timeout_polls: int = 150,
        resolution: str = "768P",
    ):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self.opener = opener
        self.sleeper = sleeper
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_polls = timeout_polls
        self.resolution = resolution if resolution in self.allowed_resolutions else "768P"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if not self.api_key:
            raise VideoGenerationError("MINIMAX_API_KEY is required for the MiniMax H3 provider")
        if not request.reference_video_paths:
            raise VideoGenerationError("MiniMax H3 graybox workflow requires at least one reference video")
        if len(request.reference_video_paths) > 3:
            raise VideoGenerationError("MiniMax H3 accepts at most three reference videos")
        if len(request.image_paths) > 9:
            raise VideoGenerationError("MiniMax H3 accepts at most nine reference images")
        if len(request.reference_audio_paths) > 3:
            raise VideoGenerationError("MiniMax H3 accepts at most three reference audio files")

        model = "MiniMax-H3" if request.model in {"", "gen4.5"} else request.model
        if model not in self.allowed_models:
            raise VideoGenerationError(f"unsupported MiniMax video model: {model}")
        duration = max(4, min(15, int(round(request.shot_duration_seconds))))
        if model == "MiniMax-H3-Max":
            duration = max(5, duration)
        prompt = str(request.prompt_text or "").strip()
        if not prompt:
            raise VideoGenerationError("MiniMax H3 requires a non-empty prompt")

        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in request.reference_video_paths:
            path = Path(path).expanduser().resolve()
            if path.stat().st_size > self.max_reference_video_bytes:
                raise VideoGenerationError(
                    "graybox reference video is too large for safe inline upload; keep it below 40 MB"
                )
            content.append({
                "type": "video_url",
                "video_url": {"url": self._data_uri(path, "video/mp4")},
                "role": "reference_video",
            })
        for path in request.image_paths:
            path = Path(path).expanduser().resolve()
            content.append({
                "type": "image_url",
                "image_url": {"url": self._data_uri(path)},
                "role": "reference_image",
            })
        for path in request.reference_audio_paths:
            path = Path(path).expanduser().resolve()
            content.append({
                "type": "audio_url",
                "audio_url": {"url": self._data_uri(path)},
                "role": "reference_audio",
            })

        payload = {
            "model": model,
            "content": content,
            "resolution": self.resolution,
            "duration": duration,
            "ratio": self._ratio(request.width, request.height),
        }
        created = self._request_json("POST", "/v2/video_generation", payload)
        task_id = str(created.get("task_id") or "")
        if not task_id:
            raise VideoGenerationError("MiniMax H3 response did not include task_id")
        task = self._wait_for_task(task_id)
        result_url = str(((task.get("content") or {}).get("url") if isinstance(task.get("content"), dict) else "") or "")
        if not result_url.startswith(("https://", "http://")):
            raise VideoGenerationError("MiniMax H3 completed without a downloadable video URL")

        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.opener(result_url) as response:
                output.write_bytes(response.read())
        except Exception as error:
            raise VideoGenerationError("MiniMax H3 output download failed") from error
        if not output.is_file() or output.stat().st_size < 1024:
            raise VideoGenerationError("MiniMax H3 output is empty or unexpectedly small")

        actual_duration = float(task.get("duration") or duration)
        return VideoGenerationResult(
            output_path=output,
            provider=self.name,
            duration_seconds=actual_duration,
            image_count=len(request.image_paths),
            remote_generation=True,
            task_id=task_id,
        )

    def _data_uri(self, path: Path, forced_mime: str | None = None) -> str:
        mime = forced_mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _ratio(width: int, height: int) -> str:
        if height > width:
            return "9:16"
        if width > height:
            return "16:9"
        return "1:1"

    def _request_obj(self, method: str, endpoint: str, payload: dict | None = None) -> urllib.request.Request:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(self.api_url + endpoint, data=data, method=method, headers=headers)

    def _request_json(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        try:
            with self.opener(self._request_obj(method, endpoint, payload)) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                payload = json.loads(error.read().decode("utf-8"))
                detail = str((payload.get("error") or {}).get("message") or "")
            except Exception:
                pass
            raise VideoGenerationError(
                f"MiniMax H3 API HTTP {error.code}" + (f": {detail}" if detail else "")
            ) from error
        except Exception as error:
            raise VideoGenerationError(f"MiniMax H3 API request failed: {endpoint}") from error
        if not isinstance(parsed, dict):
            raise VideoGenerationError("MiniMax H3 API returned a non-object response")
        if isinstance(parsed.get("error"), dict):
            raise VideoGenerationError(str(parsed["error"].get("message") or "MiniMax H3 API error"))
        return parsed

    def _wait_for_task(self, task_id: str) -> dict:
        for _ in range(self.timeout_polls):
            result = self._request_json("GET", f"/v2/query/video_generation/{task_id}")
            task = result.get("task")
            if not isinstance(task, dict):
                raise VideoGenerationError("MiniMax H3 query response did not include task")
            status = str(task.get("status") or "").lower()
            if status in {"succeeded", "success", "completed"}:
                return task
            if status in {"failed", "cancelled", "canceled"}:
                error = task.get("error")
                detail = error.get("message") if isinstance(error, dict) else error
                raise VideoGenerationError(f"MiniMax H3 generation failed: {detail or status}")
            self.sleeper(self.poll_interval_seconds)
        raise VideoGenerationError("MiniMax H3 video task timed out")
