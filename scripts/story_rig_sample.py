"""Build the P47-07 fixed-rig sample from real episode shots."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from scripts.episode_workbench import _control_clip, load_script, read


SHOT_RULES = (
    ("modern_office", "closeup"),
    ("modern_door", "wide"),
    ("modern_dinner", "medium"),
)


def selected_rows(project: Path, episode: str = "S01E001"):
    script = load_script(project, episode)
    rows = []
    for action, framing in SHOT_RULES:
        row = next((item for item in script["shots"] if item["action"] == action and item.get("framing") == framing), None)
        if not row:
            raise ValueError(f"缺少固定角色样段镜头：{action}/{framing}")
        rows.append(row)
    return script, rows


def build(project: Path, output: Path, episode: str = "S01E001") -> Path:
    project = Path(project).resolve(); output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    script, rows = selected_rows(project, episode)
    audio = read(project / "production/episodes" / episode / "audio.json", {})
    if audio.get("script_signature") != script.get("signature"):
        raise ValueError("请先生成当前台本的本地配音时间轴")
    lines = {line["shot_id"]: line for line in audio.get("lines", [])}
    clips = []
    for row in rows:
        line = lines.get(row["id"])
        if not line:
            raise ValueError("样段镜头缺少声音时长")
        folder = output / "shots" / row["id"]
        folder.mkdir(parents=True, exist_ok=True)
        clip = folder / "preview.mp4"
        _control_clip(project, row, line["clip_duration"], clip)
        clips.append(clip)
    concat = output / "concat.txt"
    concat.write_text("\n".join("file '" + clip.as_posix().replace("'", "'\\''") + "'" for clip in clips) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-c", "copy", str(output / "performance.mp4")], check=True, timeout=120)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "4.2", "-i",
                    str(output / "performance.mp4"), "-frames:v", "1", str(output / "poster.png")], check=True, timeout=30)
    first_blend = clips[0].parent / "control.blend"
    if first_blend.is_file():
        shutil.copyfile(first_blend, output / "performance.blend")
    report = {
        "schema_version": 1, "task": "P47-07", "episode_id": episode,
        "source_script_signature": script["signature"], "renderer": "fixed_humanoid_story",
        "shots": [row["id"] for row in rows],
        "actors": [
            {"id": "陈浩", "rig": "ChenHao_Rig", "bones": 65, "fixed_asset": True},
            {"id": "林晓", "rig": "LinXiao_Rig", "bones": 65, "fixed_asset": True},
            {"id": "主管", "rig": "Supervisor_Rig", "bones": 65, "fixed_asset": True},
        ],
        "performance": {"continuous_body_motion": True, "head_and_torso_acting": True,
            "blink_keys": True, "hand_ik": True, "walking_root_motion": True,
            "prop_binding": True, "contact_pass": True, "technical_gate": "rig_prop_binding"},
        "limits": [
            "This is an improved control-quality white model, not final character art.",
            "The CC0 base has no jaw or facial blendshapes; no floating mouth proxy is used.",
            "Dialogue lip sync and detailed cloth simulation remain later-stage work.",
        ],
        "human_review": "PENDING",
    }
    (output / "performance-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
