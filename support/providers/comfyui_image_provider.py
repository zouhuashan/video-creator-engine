"""Local ComfyUI image provider for VideoCreator Engine."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "providers" / "comfyui-image-provider.json"


class ComfyUIImageError(RuntimeError):
    pass


def _load_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ComfyUIImageError(f"invalid ComfyUI provider config: {error}") from error
    if not isinstance(payload, dict):
        raise ComfyUIImageError("ComfyUI provider config must be an object")
    return payload


def _safe_base_url(value: str) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ComfyUIImageError("ComfyUI base URL must be http(s)")
    if parsed.username or parsed.password:
        raise ComfyUIImageError("ComfyUI base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ComfyUIImageError("ComfyUI base URL must not contain query or fragment")
    return candidate


def _parse_size(size: str) -> tuple[int, int]:
    try:
        width_text, height_text = str(size).lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as error:
        raise ComfyUIImageError("image size must use WIDTHxHEIGHT") from error
    if width < 256 or height < 256 or width > 4096 or height > 4096:
        raise ComfyUIImageError("image size is outside supported bounds")
    if width % 8 or height % 8:
        raise ComfyUIImageError("ComfyUI image dimensions must be divisible by 8")
    return width, height


class ComfyUIImageProvider:
    provider_id = "comfyui_image"

    def __init__(self, base_url: str | None = None, *, config_path: Path = DEFAULT_CONFIG_PATH, timeout_seconds: float | None = None) -> None:
        self.config_path = Path(config_path)
        self.config = _load_config(self.config_path)
        env_name = str(self.config.get("base_url_env") or "COMFYUI_BASE_URL")
        configured = base_url or os.environ.get(env_name) or self.config.get("default_base_url") or "http://127.0.0.1:8188"
        self.base_url = _safe_base_url(str(configured))
        self.timeout_seconds = float(timeout_seconds or self.config.get("timeout_seconds") or 180.0)
        self.poll_interval_seconds = max(0.05, float(self.config.get("poll_interval_seconds") or 0.5))

    def _request_json(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body,
            headers={"Content-Type": "application/json"} if body is not None else {}, method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            raise ComfyUIImageError(f"ComfyUI HTTP {error.code}" + (f": {detail}" if detail else "")) from error
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise ComfyUIImageError(f"ComfyUI request failed: {error}") from error
        if not isinstance(parsed, dict):
            raise ComfyUIImageError("ComfyUI returned a non-object JSON response")
        return parsed

    def health(self, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        payload = self._request_json("/system_stats", timeout=timeout_seconds)
        devices = payload.get("devices")
        return {"connected": True, "base_url": self.base_url, "device_count": len(devices) if isinstance(devices, list) else 0}

    @staticmethod
    def _checkpoint_names(payload: dict[str, Any]) -> list[str]:
        node = payload.get("CheckpointLoaderSimple")
        if not isinstance(node, dict):
            node = payload
        try:
            raw = node["input"]["required"]["ckpt_name"][0]
        except (KeyError, IndexError, TypeError):
            return []
        return [str(item) for item in raw if isinstance(item, str) and item.strip()] if isinstance(raw, list) else []

    def available_checkpoints(self, *, timeout_seconds: float | None = None) -> list[str]:
        try:
            payload = self._request_json("/object_info/CheckpointLoaderSimple", timeout=timeout_seconds)
        except ComfyUIImageError:
            payload = self._request_json("/object_info", timeout=timeout_seconds)
        return self._checkpoint_names(payload)

    def choose_checkpoint(self, available: list[str] | None = None) -> str:
        checkpoints = available if available is not None else self.available_checkpoints()
        env_name = str(self.config.get("checkpoint_env") or "COMFYUI_CHECKPOINT")
        preferred = str(os.environ.get(env_name) or self.config.get("checkpoint") or "").strip()
        if preferred:
            if preferred not in checkpoints:
                raise ComfyUIImageError(f"configured ComfyUI checkpoint is unavailable: {preferred}")
            return preferred
        if not checkpoints:
            raise ComfyUIImageError("ComfyUI has no checkpoint available")
        return checkpoints[0]

    def build_workflow(self, prompt: str, *, size: str, checkpoint: str, filename_prefix: str, seed: int | None = None, negative_prompt: str | None = None) -> dict[str, Any]:
        width, height = _parse_size(size)
        positive = str(prompt or "").strip()
        if not positive:
            raise ComfyUIImageError("image prompt is empty")
        negative = str(negative_prompt if negative_prompt is not None else self.config.get("negative_prompt") or "watermark, text, logo, malformed hands, extra fingers, duplicate limbs, low quality")
        chosen_seed = int(seed if seed is not None else time.time_ns() % (2**53 - 1))
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "seed": chosen_seed, "steps": int(self.config.get("steps") or 24), "cfg": float(self.config.get("cfg_scale") or 6.5),
                "sampler_name": str(self.config.get("sampler_name") or "euler"), "scheduler": str(self.config.get("scheduler") or "normal"),
                "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["6", 0]}},
        }

    def _first_output_image(self, history: dict[str, Any], prompt_id: str) -> dict[str, str] | None:
        record = history.get(prompt_id)
        if not isinstance(record, dict) and "outputs" in history:
            record = history
        if not isinstance(record, dict):
            return None
        status = record.get("status")
        if isinstance(status, dict) and str(status.get("status_str") or "").lower() == "error":
            raise ComfyUIImageError("ComfyUI workflow failed")
        outputs = record.get("outputs")
        if not isinstance(outputs, dict):
            return None
        for output in outputs.values():
            if isinstance(output, dict) and isinstance(output.get("images"), list):
                for image in output["images"]:
                    if isinstance(image, dict) and image.get("filename"):
                        return {"filename": str(image["filename"]), "subfolder": str(image.get("subfolder") or ""), "type": str(image.get("type") or "output")}
        return None

    def _download_image(self, image: dict[str, str], output_path: Path) -> None:
        query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{self.base_url}/view?{query}", method="GET"), timeout=self.timeout_seconds) as response:
                data = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            raise ComfyUIImageError(f"failed to download ComfyUI output: {error}") from error
        if not data:
            raise ComfyUIImageError("ComfyUI returned an empty image")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(output_path)

    def generate(self, prompt: str, output_path: Path, *, size: str, negative_prompt: str | None = None) -> dict[str, Any]:
        checkpoints = self.available_checkpoints()
        checkpoint = self.choose_checkpoint(checkpoints)
        prefix = f"videocreator/{Path(output_path).stem}-{uuid.uuid4().hex[:8]}"
        workflow = self.build_workflow(prompt, size=size, checkpoint=checkpoint, filename_prefix=prefix, negative_prompt=negative_prompt)
        queued = self._request_json("/prompt", method="POST", payload={"prompt": workflow, "client_id": uuid.uuid4().hex})
        prompt_id = str(queued.get("prompt_id") or "").strip()
        if not prompt_id:
            raise ComfyUIImageError("ComfyUI did not return prompt_id")
        deadline = time.monotonic() + self.timeout_seconds
        image = None
        while time.monotonic() < deadline:
            image = self._first_output_image(self._request_json(f"/history/{urllib.parse.quote(prompt_id, safe='')}"), prompt_id)
            if image:
                break
            time.sleep(self.poll_interval_seconds)
        if image is None:
            raise ComfyUIImageError("ComfyUI generation timed out")
        output_path = Path(output_path)
        self._download_image(image, output_path)
        return {"provider": self.provider_id, "model": checkpoint, "size": size, "quality": "local", "output": str(output_path), "prompt_id": prompt_id, "workflow": "builtin_txt2img_v1", "server_image": image}


__all__ = ["ComfyUIImageError", "ComfyUIImageProvider"]
