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
    walk_start_time = float(actor.get("walk_start_time") or 0)
    stop_time = float(actor.get("stop_time") or 0)
    look_up_time = float(actor.get("look_up_time") or 0)
    hold_time = float(actor.get("hold_time") or 0)
    if not (0 <= walk_start_time < stop_time < look_up_time <= hold_time <= duration):
        raise GrayboxShotSpecError("actor timing must satisfy walk_start < stop < look_up <= hold <= duration")
    character = spec.get("character")
    if not isinstance(character, dict) or not str(character.get("name") or "").strip():
        raise GrayboxShotSpecError("graybox character identity is required")
    return spec


def apply_natural_language_adjustment(project_dir: Path, instruction: str, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    """Apply a small, deterministic graybox edit from common Chinese natural-language instructions.

    This intentionally handles only safe camera/timing/position changes. Unknown instructions are
    rejected instead of silently inventing motion.
    """
    text = str(instruction or "").strip()
    if not text:
        raise GrayboxShotSpecError("graybox adjustment instruction is empty")
    spec = load_spec(project_dir, spec_id)
    changed: list[str] = []

    duration = float(spec["duration_seconds"])
    actor = spec["actor"]
    camera = spec["camera_path"]

    if any(token in text for token in ("镜头慢一点", "镜头再慢", "运镜慢一点", "推进慢一点")):
        new_duration = min(15.0, round(duration + 1.0, 2))
        scale = new_duration / duration
        spec["duration_seconds"] = new_duration
        for key in ("stop_time", "look_up_time", "hold_time"):
            actor[key] = round(min(new_duration, float(actor[key]) * scale), 2)
        changed.append(f"duration_seconds {duration:g} → {new_duration:g}")

    hold_match = __import__("re").search(r"(?:结尾|最后).*?(\d+(?:\.\d+)?)\s*秒", text)
    if hold_match and any(token in text for token in ("停留", "停", "多留", "多停")):
        extra = max(0.2, min(5.0, float(hold_match.group(1))))
        old_duration = float(spec["duration_seconds"])
        new_duration = min(15.0, round(old_duration + extra, 2))
        spec["duration_seconds"] = new_duration
        actor["hold_time"] = new_duration
        changed.append(f"final_hold +{new_duration - old_duration:g}s")

    if any(token in text for token in ("推进幅度变小", "推进少一点", "镜头别推那么近", "镜头推进小一点")):
        start = list(camera["start"])
        end = list(camera["end"])
        factor = 0.55
        camera["end"] = [round(start[i] + (end[i] - start[i]) * factor, 3) for i in range(3)]
        changed.append("camera_dolly_distance ×0.55")

    if any(token in text for token in ("推进幅度变大", "推进多一点", "镜头推近一点")):
        start = list(camera["start"])
        end = list(camera["end"])
        factor = 1.25
        camera["end"] = [round(start[i] + (end[i] - start[i]) * factor, 3) for i in range(3)]
        changed.append("camera_dolly_distance ×1.25")

    if any(token in text for token in ("人物走路再平缓", "走路平缓", "走慢一点", "人物慢一点")):
        old_stop = float(actor["stop_time"])
        max_stop = max(0.8, float(spec["duration_seconds"]) - 2.2)
        actor["stop_time"] = round(min(max_stop, old_stop + 0.8), 2)
        actor["look_up_time"] = round(max(float(actor["look_up_time"]), float(actor["stop_time"]) + 0.55), 2)
        actor["hold_time"] = round(max(float(actor["hold_time"]), float(actor["look_up_time"]) + 0.8), 2)
        if actor["hold_time"] > float(spec["duration_seconds"]):
            spec["duration_seconds"] = min(15.0, round(actor["hold_time"] + 0.4, 2))
        changed.append(f"actor.stop_time {old_stop:g} → {actor['stop_time']:g}")

    if any(token in text for token in ("人物离建筑近一点", "人物靠近门", "贴近建筑", "离门近一点")):
        old = list(actor["stop"])
        actor["stop"] = [old[0], round(old[1] + 0.8, 3), old[2]]
        changed.append("actor.stop closer_to_gate +0.8m")

    if any(token in text for token in ("人物离建筑远一点", "离门远一点", "人物后退一点")):
        old = list(actor["stop"])
        actor["stop"] = [old[0], round(old[1] - 0.8, 3), old[2]]
        changed.append("actor.stop farther_from_gate -0.8m")

    if not changed:
        raise GrayboxShotSpecError(
            "暂不支持这条白模微调。当前支持：镜头慢一点、最后多停 N 秒、推进幅度变小/变大、"
            "人物走慢/平缓、人物离门近一点/远一点。"
        )

    spec["updated_at"] = utc_timestamp()
    spec["review"] = {"required": True, "status": "CHANGES_REQUESTED", "note": text}
    validated = validate_spec(project_dir, spec)
    write_spec(project_dir, validated, overwrite=True)
    return {
        "status": "UPDATED",
        "instruction": text,
        "changes": changed,
        "spec": validated,
    }


def review_spec(project_dir: Path, status: str, note: str = "", spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    value = str(status or "").strip().upper()
    if value not in {"APPROVED", "CHANGES_REQUESTED", "PENDING"}:
        raise GrayboxShotSpecError("graybox review status must be APPROVED, CHANGES_REQUESTED or PENDING")
    spec = load_spec(project_dir, spec_id)
    spec["review"] = {"required": True, "status": value, "note": str(note or "").strip()}
    spec["updated_at"] = utc_timestamp()
    validated = validate_spec(project_dir, spec)
    write_spec(project_dir, validated, overwrite=True)
    return {"status": value, "spec": validated}


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
    project_dir = Path(project_dir).resolve()
    path = spec_path(project_dir)
    if not path.is_file():
        return write_spec(project_dir, build_default_spec(project_dir))

    current = validate_spec(project_dir, _load_json(path))
    cfg = _load_json(CONFIG_PATH)
    template = cfg.get("default_shot") if isinstance(cfg.get("default_shot"), dict) else {}
    desired_revision = int((template or {}).get("blocking_revision") or 1)
    current_revision = int(current.get("blocking_revision") or 1)
    review = current.get("review") if isinstance(current.get("review"), dict) else {}
    ai_video = current.get("ai_video") if isinstance(current.get("ai_video"), dict) else {}

    # The first smoke shot is a disposable system default. If it is still untouched
    # (review PENDING and no final-video generation), migrate it to the latest
    # blocking revision automatically so a known-bad camera/actor layout does not persist.
    if (
        current_revision < desired_revision
        and str(review.get("status") or "PENDING").upper() == "PENDING"
        and str(ai_video.get("status") or "NOT_STARTED").upper() == "NOT_STARTED"
    ):
        replacement = build_default_spec(project_dir)
        replacement["created_at"] = current.get("created_at") or replacement["created_at"]
        replacement["review"] = {
            "required": True,
            "status": "PENDING",
            "note": f"Auto-migrated graybox blocking revision {current_revision} → {desired_revision}",
        }
        write_spec(project_dir, replacement, overwrite=True)
        return path

    return path


def load_spec(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    path = spec_path(project_dir, spec_id)
    return validate_spec(project_dir, _load_json(path))


if __name__ == "__main__":
    project = Path(sys.argv[1]).resolve()
    path = ensure_default_spec(project)
    print(json.dumps({"status": "PASS", "spec": str(path)}, ensure_ascii=False))
