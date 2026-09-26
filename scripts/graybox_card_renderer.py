"""Render the current Blender blocking with Codex-created multi-angle character cards."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.graybox_manager import blender_executable

ROOT = Path(__file__).resolve().parents[1]


class GrayboxCardRenderError(RuntimeError):
    pass


def render_card_preview(project_dir: Path, spec_id: str = "GB-SHOT-001") -> dict[str, Any]:
    project = Path(project_dir).resolve()
    spec_path = project / "graybox" / "shot-specs" / f"{spec_id}.json"
    if not spec_path.is_file():
        raise GrayboxCardRenderError(f"缺少镜头方案：{spec_path.relative_to(project)}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    character_id = str((spec.get("character") or {}).get("id") or "")
    card_root = project / "lookdev" / "character-cards"
    character_dir = None
    for manifest_path in card_root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("character_id") == character_id:
            character_dir = manifest_path.parent
            break
    if character_dir is None:
        raise GrayboxCardRenderError(f"没有找到角色 {character_id} 的多角度角色卡")
    background = project / "graybox" / "references" / "scenes" / f"{spec_id}-scene-codex-v1.png"
    if not background.is_file():
        raise GrayboxCardRenderError("缺少 Codex 场景参考图，请先生成并保存场景资产")
    blender = blender_executable()
    if blender is None:
        raise GrayboxCardRenderError("未检测到 Blender")
    output = project / "graybox" / "card-renders" / f"{spec_id}-codex-cards-v6.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    script = ROOT / "scripts" / "blender_graybox_card_scene.py"
    command = [str(blender), "--background", "--python", str(script), "--", "--spec", str(spec_path), "--character-dir", str(character_dir), "--background", str(background), "--output", str(output)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        detail = (result.stderr or result.stdout or "Blender 未输出有效视频")[-4000:]
        raise GrayboxCardRenderError(f"角色卡本地预览失败：{detail}")
    metadata = {
        "schema_version": 6,
        "status": "PREVIEW_READY",
        "provider": "blender_codex_character_cards",
        "project_id": project.name,
        "shot_id": spec_id,
        "character_id": character_id,
        "character_card_dir": str(character_dir.relative_to(project)),
        "background": str(background.relative_to(project)),
        "output": str(output.relative_to(project)),
        "duration_seconds": spec.get("duration_seconds"),
        "fps": spec.get("fps"),
        "local_only": True,
        "billable": False,
        "images_uploaded": False,
        "review_status": "REJECTED",
        "quality_note": "整身角色卡仅平移和缩放，缺少可信的肢体动作；此算法输出只保留技术参考。",
        "limitations": ["角色以透明多角度整图卡片呈现，当前肢体形变有限", "场景参考作为背景板，复杂前后景遮挡尚未重建"]
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata
