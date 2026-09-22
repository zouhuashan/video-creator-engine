#!/usr/bin/env python3
"""Create and validate a deterministic Blender graybox shot specification."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp

CONFIG_PATH = ROOT / "config" / "graybox-to-video.json"
OUTPUT_DIR = Path("graybox") / "shot-specs"
DEFAULT_SPEC_ID = "GB-SHOT-001"


class GrayboxShotSpecError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GrayboxShotSpecError(f"cannot read JSON: {path}") from error
    if not isinstance(payload, dict):
        raise GrayboxShotSpecError(f"JSON must be an object: {path}")
    return payload


def _project_character(project_dir: Path) -> dict[str, str]:
    path = Path(project_dir) / "story-bible" / "characters" / "index.json"
    if not path.is_file():
        return {"id": "PROJECT-CHARACTER", "name": "项目主角", "role": "protagonist"}
    payload = _load_json(path)
    items = payload if isinstance(payload, list) else payload.get("characters", [])
    if not isinstance(items, list) or not items:
        return {"id": "PROJECT-CHARACTER", "name": "项目主角", "role": "protagonist"}
    item = next((x for x in items if isinstance(x, dict) and str(x.get("role") or "").lower() in {"protagonist", "main"}), None)
    if item is None:
        item = next((x for x in items if isinstance(x, dict)), {})
    return {
        "id": str(item.get("id") or item.get("character_id") or "PROJECT-CHARACTER"),
        "name": str(item.get("name") or item.get("title") or "项目主角"),
        "role": str(item.get("role") or "protagonist"),
    }


def build_default_spec(project_dir: Path, *, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    cfg = _load_json(CONFIG_PATH)
    template = deepcopy(cfg.get("default_shot") or {})
    if not isinstance(template, dict):
        raise GrayboxShotSpecError("default graybox shot config is invalid")
    character = _project_character(project_dir)
    template.update({
        "id": spec_id,
        "project_id": project["project_id"],
        "title": project["title"],
        "character": character,
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
        "review": {"required": True, "status": "PENDING", "note": ""},
        "ai_video": {
            "provider": "minimax_h3",
            "status": "NOT_STARTED",
            "prompt": str((cfg.get("minimax_h3") or {}).get("default_prompt") or ""),
        },
    })
    return validate_spec(project_dir, template)


def _vec3(name: str, value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise GrayboxShotSpecError(f"{name} must be a 3-number array")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as error:
        raise GrayboxShotSpecError(f"{name} must contain numbers") from error


def validate_spec(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GrayboxShotSpecError("graybox shot spec must be an object")
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    spec = deepcopy(payload)
    if str(spec.get("project_id") or "") != str(project["project_id"]):
        raise GrayboxShotSpecError("graybox shot spec does not match project")
    spec_id = str(spec.get("id") or "").strip()
    if not spec_id.startswith("GB-SHOT-"):
        raise GrayboxShotSpecError("graybox spec id must start with GB-SHOT-")
    duration = float(spec.get("duration_seconds") or 0)
    fps = int(spec.get("fps") or 0)
    width = int(spec.get("width") or 0)
    height = int(spec.get("height") or 0)
    if not 2 <= duration <= 15:
        raise GrayboxShotSpecError("graybox duration must be between 2 and 15 seconds")
    if not 12 <= fps <= 60:
        raise GrayboxShotSpecError("graybox fps must be between 12 and 60")
    if width < 256 or height < 256:
        raise GrayboxShotSpecError("graybox dimensions must be at least 256 pixels")
    actor = spec.get("actor")
    camera = spec.get("camera_path")
    if not isinstance(actor, dict) or not isinstance(camera, dict):
        raise GrayboxShotSpecError("graybox actor and camera_path are required")
    actor["start"] = _vec3("actor.start", actor.get("start"))
    actor["stop"] = _vec3("actor.stop", actor.get("stop"))
    camera["start"] = _vec3("camera_path.start", camera.get("start"))
    camera["end"] = _vec3("camera_path.end", camera.get("end"))
    camera["target"] = _vec3("camera_path.target", camera.get("target"))
    stop_time = float(actor.get("stop_time") or 0)
    look_up_time = float(actor.get("look_up_time") or 0)
    hold_time = float(actor.get("hold_time") or 0)
    if not (0 < stop_time < look_up_time <= hold_time <= duration):
        raise GrayboxShotSpecError("actor timing must satisfy stop < look_up <= hold <= duration")
    character = spec.get("character")
    if not isinstance(character, dict) or not str(character.get("name") or "").strip():
        raise GrayboxShotSpecError("graybox character identity is required")
    return spec


def spec_path(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> Path:
    return Path(project_dir).resolve() / OUTPUT_DIR / f"{spec_id}.json"


def write_spec(project_dir: Path, spec: dict[str, Any], *, overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).resolve()
    spec = validate_spec(project_dir, spec)
    path = spec_path(project_dir, str(spec["id"]))
    if path.exists() and not overwrite:
        raise GrayboxShotSpecError(f"refusing to overwrite graybox shot spec: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".graybox-shot.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(spec, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return path


def ensure_default_spec(project_dir: Path) -> Path:
    path = spec_path(project_dir)
    if path.is_file():
        validate_spec(project_dir, _load_json(path))
        return path
    return write_spec(project_dir, build_default_spec(project_dir))


def load_spec(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    path = spec_path(project_dir, spec_id)
    return validate_spec(project_dir, _load_json(path))


if __name__ == "__main__":
    project = Path(sys.argv[1]).resolve()
    path = ensure_default_spec(project)
    print(json.dumps({"status": "PASS", "spec": str(path)}, ensure_ascii=False))
