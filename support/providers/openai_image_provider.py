"""OpenAI image-generation fallback provider for VideoCreator.

Dependency-free on purpose: the Web console can call this module with Python's
standard library only. API keys are supplied by the caller and are never
persisted or logged here.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class OpenAIImageError(RuntimeError):
    pass


class OpenAIImageProvider:
    provider_id = "openai_image"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-image-2",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 240.0,
    ) -> None:
        key = str(api_key or "").strip()
        if not key:
            raise OpenAIImageError("OpenAI Image API Key 未配置")
        self._api_key = key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str, output_path: Path, *, size: str, quality: str = "high") -> dict[str, Any]:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise OpenAIImageError("image prompt is empty")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": 1,
        }
        request = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                parsed = json.loads(error.read().decode("utf-8"))
                detail = str((parsed.get("error") or {}).get("message") or "")
            except Exception:
                detail = ""
            raise OpenAIImageError(
                f"OpenAI image API HTTP {error.code}" + (f": {detail}" if detail else "")
            ) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OpenAIImageError(f"OpenAI image API failed: {error}") from error

        items = result.get("data") if isinstance(result, dict) else None
        if not isinstance(items, list) or not items:
            raise OpenAIImageError("OpenAI image API returned no image")
        item = items[0] if isinstance(items[0], dict) else {}
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if item.get("b64_json"):
            try:
                output_path.write_bytes(base64.b64decode(item["b64_json"]))
            except (ValueError, OSError) as error:
                raise OpenAIImageError(f"failed to save generated image: {error}") from error
        elif item.get("url"):
            try:
                with urllib.request.urlopen(str(item["url"]), timeout=self.timeout_seconds) as response:
                    output_path.write_bytes(response.read())
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                raise OpenAIImageError(f"failed to download generated image: {error}") from error
        else:
            raise OpenAIImageError("OpenAI image API response contains neither b64_json nor url")

        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise OpenAIImageError("generated image file is missing or unexpectedly small")
        return {
            "provider": self.provider_id,
            "model": self.model,
            "size": size,
            "quality": quality,
            "output": str(output_path),
            "revised_prompt": str(item.get("revised_prompt") or ""),
        }


def character_bible_prompt(
    character: dict[str, Any],
    custom_prompt: str = "",
    *,
    style_direction: str = "",
    forbidden_direction: str = "",
) -> str:
    lock = character["visual_lock"]
    render = character["render_lock"]
    rules = "; ".join(str(item) for item in character.get("consistency_rules", []))
    extra = str(custom_prompt or "").strip()
    style = str(style_direction or "").strip()
    forbidden = str(forbidden_direction or "").strip()
    is_3d = "3d" in style.lower()
    parts = [
        (
            "Create one polished 3D production character-turnaround board for a premium animated feature. "
            if is_3d
            else "Create one polished production character-design board for a premium animated series. "
        ),
        f"Style direction: {style}. " if style else "Use a premium Chinese guofeng donghua direction. ",
        (
            "Every panel must be a camera render of the same fully modeled three-dimensional character; preserve true volume, perspective, material thickness and consistent studio lighting. Do not present flat painted views. "
            if is_3d
            else ""
        ),
        "The SAME character must appear consistently in every panel. ",
        "Include: large hero portrait, front full body, three-quarter full body, side profile, ",
        "back view, five facial expressions, and small costume/hair detail callouts. ",
        f"Character: {character['name']}, {character['role']}. ",
        f"Face: {lock['face']}. Hair: {lock['hair']}. Costume: {lock['costume']}. ",
        f"Body: {lock['body']}. Mood: {lock['mood']}. ",
        f"Rendering: {render['medium']}; {render['shading']}. Lighting: {render['lighting']}. ",
        f"Palette: {', '.join(render['palette'])}. ",
        (
            "Use a clean premium 3D turnaround-sheet layout with a neutral studio cyclorama/background; the beauty portrait should feel like a finished film character render. "
            if is_3d
            else "Use a clean elegant concept-board layout with a neutral warm background. "
        ),
        f"Forbidden style/content: {forbidden}. " if forbidden else "No app UI, no watermark, no random extra characters. ",
        f"Hard consistency rules: {rules}. ",
    ]
    if extra:
        parts.append(f"Additional direction: {extra}.")
    return "".join(parts)


def keyframe_prompt(
    character: dict[str, Any],
    shot: dict[str, Any],
    custom_prompt: str = "",
    *,
    style_direction: str = "",
    forbidden_direction: str = "",
) -> str:
    lock = character["visual_lock"]
    render = character["render_lock"]
    camera = shot["camera"]
    extra = str(custom_prompt or "").strip()
    style = str(style_direction or "").strip()
    forbidden = str(forbidden_direction or "").strip()
    is_3d = "3d" in style.lower()
    parts = [
        (
            "Create a finished cinematic 3D keyframe for a premium animated feature. "
            if is_3d
            else "Create a finished cinematic keyframe for a premium animated series. "
        ),
        f"Style direction: {style}. " if style else "Use a premium Chinese guofeng donghua set in ancient China / Chinese fantasy. ",
        f"The hero must exactly match the locked identity for {character['name']} ({character['role']}). ",
        f"Locked face: {lock['face']}. Locked hair: {lock['hair']}. ",
        f"Locked costume: {lock['costume']}. Locked body read: {lock['body']}. ",
        f"Action: {shot['action']} ",
        f"Environment: {shot['environment']}. Lighting: {shot['lighting']}. ",
        f"Camera: {camera['framing']}, {camera['lens_language']}, {camera['angle']}, ",
        f"DOF {camera['depth_of_field']}. ",
        f"Visual medium: {render['medium']}; {render['shading']}. ",
        (
            "Composition must read as a true 3D film frame: sculpted facial volume, dimensional hair geometry, cloth thickness and folds, perspective, contact shadows, cinematic key/fill/rim lighting, atmospheric depth and real depth of field; stylized NPR/toon finish with believable material response. "
            if is_3d
            else "Composition should feel like a frame from a high-end animated feature: readable eye-line, layered cloth, natural hair masses, cinematic atmospheric depth, refined anime/NPR finish. "
        ),
    ]
    if forbidden:
        parts.append(f"Forbidden style/content: {forbidden}. ")
    parts.append("No concept-sheet layout, no text, no UI, no watermark, no low-poly primitives. ")
    if extra:
        parts.append(f"Additional shot direction: {extra}.")
    return "".join(parts)

