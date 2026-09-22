#!/usr/bin/env python3
"""Shot-level character/scene reference binding for the P32 graybox pipeline."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_SCENE_REFERENCE_BYTES = 12 * 1024 * 1024
DEFAULT_SPEC_ID = "GB-SHOT-001"


class GrayboxReferenceError(RuntimeError):
    pass


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def binding_path(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> Path:
    clean_id = str(spec_id or DEFAULT_SPEC_ID).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", clean_id):
        raise GrayboxReferenceError("invalid graybox shot spec id")
    return Path(project_dir).resolve() / "graybox" / "reference-bindings" / f"{clean_id}.json"


def _image_valid(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    return (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or (len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )


def _safe_relative_image(project_dir: Path, relative_path: str) -> Path:
    project = Path(project_dir).resolve()
    value = str(relative_path or "").strip().replace("\\", "/")
    candidate = (project / value).resolve()
    if project not in candidate.parents:
        raise GrayboxReferenceError("reference image is outside the project")
    if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS or not _image_valid(candidate):
        raise GrayboxReferenceError("reference image is missing or invalid")
    return candidate


def _relative(project_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(Path(project_dir).resolve()).as_posix()


def load_binding(project_dir: Path) -> dict[str, Any]:
    path = binding_path(project_dir)
    if not path.is_file():
        return {
            "schema_version": 1,
            "shot_spec_id": DEFAULT_SPEC_ID,
            "character_reference": None,
            "scene_reference": None,
            "updated_at": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GrayboxReferenceError("graybox reference binding is invalid") from error
    if not isinstance(payload, dict):
        raise GrayboxReferenceError("graybox reference binding must be an object")
    payload.setdefault("schema_version", 1)
    payload.setdefault("shot_spec_id", DEFAULT_SPEC_ID)
    payload.setdefault("character_reference", None)
    payload.setdefault("scene_reference", None)
    return payload


def _write_binding(project_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = binding_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["schema_version"] = 1
    payload["updated_at"] = _utc_timestamp()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return payload


def character_candidates(project_dir: Path) -> list[dict[str, Any]]:
    project = Path(project_dir).resolve()
    root = project / "lookdev" / "image-studio"
    items: list[dict[str, Any]] = []
    if not root.is_dir():
        return items
    for meta_path in root.rglob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict) or str(meta.get("artifact_type") or "") != "character_bible":
            continue
        output = str(meta.get("output") or "").strip()
        if not output:
            continue
        try:
            image = _safe_relative_image(project, output)
        except GrayboxReferenceError:
            continue
        items.append({
            "id": _relative(project, image),
            "path": _relative(project, image),
            "label": str(meta.get("character_id") or image.stem),
            "character_id": str(meta.get("character_id") or ""),
            "review_status": str(meta.get("review_status") or "PENDING"),
            "style_label": str(meta.get("style_label") or ""),
            "created_at": str(meta.get("created_at") or ""),
            "source": "image_studio_character",
            "metadata": _relative(project, meta_path),
        })
    rank = {"APPROVED": 0, "PENDING": 1, "CHANGES_REQUESTED": 2}
    items.sort(key=lambda item: (
        rank.get(str(item.get("review_status") or ""), 9),
        str(item.get("created_at") or ""),
    ), reverse=False)
    return items


def scene_candidates(project_dir: Path) -> list[dict[str, Any]]:
    project = Path(project_dir).resolve()
    items: list[dict[str, Any]] = []

    uploaded = project / "graybox" / "references" / "scenes"
    if uploaded.is_dir():
        for image in sorted(uploaded.iterdir(), reverse=True):
            if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS or not _image_valid(image):
                continue
            items.append({
                "id": _relative(project, image),
                "path": _relative(project, image),
                "label": image.name,
                "review_status": "BOUND_SOURCE",
                "source": "scene_upload",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(image.stat().st_mtime)),
            })

    # Existing Image Studio keyframes are offered as optional scene/style references.
    root = project / "lookdev" / "image-studio"
    if root.is_dir():
        for meta_path in root.rglob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict) or str(meta.get("artifact_type") or "") != "keyframe":
                continue
            output = str(meta.get("output") or "").strip()
            if not output:
                continue
            try:
                image = _safe_relative_image(project, output)
            except GrayboxReferenceError:
                continue
            items.append({
                "id": _relative(project, image),
                "path": _relative(project, image),
                "label": f"Image Studio 关键帧 · {image.name}",
                "review_status": str(meta.get("review_status") or "PENDING"),
                "source": "image_studio_keyframe",
                "created_at": str(meta.get("created_at") or ""),
                "metadata": _relative(project, meta_path),
            })
    return items


def bind_reference(project_dir: Path, *, kind: str, relative_path: str) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    normalized = str(kind or "").strip().lower()
    if normalized not in {"character", "scene"}:
        raise GrayboxReferenceError("reference kind must be character or scene")

    candidates = character_candidates(project) if normalized == "character" else scene_candidates(project)
    selected = next((item for item in candidates if item["path"] == relative_path), None)
    if selected is None:
        raise GrayboxReferenceError(f"{normalized} reference is not in the current project inventory")
    _safe_relative_image(project, relative_path)

    payload = load_binding(project)
    payload["shot_spec_id"] = DEFAULT_SPEC_ID
    payload[f"{normalized}_reference"] = {
        **selected,
        "bound_at": _utc_timestamp(),
    }
    return _write_binding(project, payload)


def upload_scene_reference(project_dir: Path, *, filename: str, content: bytes) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    if not content:
        raise GrayboxReferenceError("scene reference image is empty")
    if len(content) > MAX_SCENE_REFERENCE_BYTES:
        raise GrayboxReferenceError("scene reference image must be 12 MB or smaller")
    original = Path(str(filename or "scene-reference.png")).name
    suffix = Path(original).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise GrayboxReferenceError("scene reference must be PNG, JPEG or WebP")
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(original).stem).strip("-._")[:80] or "scene"
    root = project / "graybox" / "references" / "scenes"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime()) + f"-{time.time_ns() % 100000:05d}"
    target = root / f"{stamp}-{safe_stem}{suffix}"
    target.write_bytes(content)
    if not _image_valid(target):
        target.unlink(missing_ok=True)
        raise GrayboxReferenceError("uploaded scene reference is not a valid image")
    return {
        "status": "UPLOADED",
        "path": _relative(project, target),
        "bytes": target.stat().st_size,
        "filename": target.name,
    }


def resolve_bound_paths(project_dir: Path, *, require_complete: bool = False) -> tuple[Path | None, Path | None, dict[str, Any]]:
    project = Path(project_dir).resolve()
    binding = load_binding(project)

    def resolve(entry: Any) -> Path | None:
        if not isinstance(entry, dict):
            return None
        path = str(entry.get("path") or "").strip()
        if not path:
            return None
        try:
            return _safe_relative_image(project, path)
        except GrayboxReferenceError:
            return None

    character = resolve(binding.get("character_reference"))
    scene = resolve(binding.get("scene_reference"))
    if require_complete and (character is None or scene is None):
        missing = []
        if character is None:
            missing.append("人物参考")
        if scene is None:
            missing.append("场景参考")
        raise GrayboxReferenceError("最终视频生成前必须绑定：" + "、".join(missing))
    return character, scene, binding


def inventory(project_dir: Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    character, scene, binding = resolve_bound_paths(project)
    return {
        "binding": binding,
        "character_candidates": character_candidates(project),
        "scene_candidates": scene_candidates(project),
        "character_bound": character is not None,
        "scene_bound": scene is not None,
        "ready": character is not None and scene is not None,
        "max_scene_upload_bytes": MAX_SCENE_REFERENCE_BYTES,
    }
