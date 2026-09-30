"""Build and expose the P47 fixed-character performance gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from adapters.video_generation.wavespeed_wan import probe_video
from scripts.graybox_manager import blender_executable
from scripts.install_makehuman_system_assets import LICENSE_URL, install as install_makehuman_assets


ROOT = Path(__file__).resolve().parents[1]
RELATIVE_DIR = Path("production/character-performance/p47-08-mpfb-single-shot-v8")
ASSET_MANIFEST = Path("production/assets/characters/makehuman-system-cc0/asset-manifest.json")
REVIEW_CHECKS = (
    "character_proportion",
    "facial_expression",
    "arm_trajectory",
    "hand_pose",
    "prop_contact",
    "clothing_shape",
)


def _read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def status(project: Path) -> dict[str, object]:
    project = Path(project).resolve()
    output = project / RELATIVE_DIR
    asset_manifest = project / ASSET_MANIFEST
    report = _read(output / "performance-report.json", {})
    video = output / "performance.mp4"
    poster = output / "poster.png"
    ready = bool(report and video.is_file() and poster.is_file() and asset_manifest.is_file())
    review = report.get("human_review", "PENDING")
    review_status = review.get("status", "PENDING") if isinstance(review, dict) else str(review or "PENDING")
    return {
        "status": "READY" if ready else "NOT_RUN",
        "ready": ready,
        "task": "P47-08",
        "title": "自然人体底座 · 6 秒单镜质量门",
        "summary": "MPFB 连续人体、现代服装/鞋/短发与原生 163 骨骼面部手部 Rig；验证手机阅读、抬眼和收紧手指。",
        "output": (RELATIVE_DIR / "performance.mp4").as_posix(),
        "poster": (RELATIVE_DIR / "poster.png").as_posix(),
        "report": (RELATIVE_DIR / "performance-report.json").as_posix(),
        "blend": (RELATIVE_DIR / "performance.blend").as_posix(),
        "asset_manifest": ASSET_MANIFEST.as_posix(),
        "license": "CC0-1.0",
        "source": LICENSE_URL,
        "technical_summary": "已移除导致肩臂崩坏的自制 IK，改用原生自然姿态和面部/手部骨骼；当前只是一镜质量门。",
        "human_review": review_status,
        "review": review if isinstance(review, dict) else {"status": review_status, "checks": {}, "notes": ""},
        "review_checks": list(REVIEW_CHECKS),
        "can_expand": review_status == "PASS",
        "technical_contact_pass": report.get("performance", {}).get("contact_pass", False),
        "limits": report.get("limits", []),
    }


def review(project: Path, payload: dict[str, object]) -> dict[str, object]:
    project = Path(project).resolve()
    output = project / RELATIVE_DIR
    report_path = output / "performance-report.json"
    report = _read(report_path, {})
    if not report or not (output / "performance.mp4").is_file():
        raise ValueError("请先完成固定角色表演样段")
    decision = str(payload.get("decision") or "").upper()
    if decision not in {"PASS", "REJECTED"}:
        raise ValueError("请选择通过或退回")
    checks_raw = payload.get("checks")
    if not isinstance(checks_raw, dict):
        raise ValueError("请逐项检查人物与动作")
    checks = {name: checks_raw.get(name) is True for name in REVIEW_CHECKS}
    notes = str(payload.get("notes") or "").strip()
    if decision == "PASS":
        missing = [name for name, checked in checks.items() if not checked]
        if missing:
            raise ValueError("通过前需要勾选全部人物与动作检查项")
        if not report.get("performance", {}).get("contact_pass"):
            raise ValueError("道具接触技术检查未通过，不能通过人审")
    elif len(notes) < 2:
        raise ValueError("退回时请写明最需要修改的问题")
    timestamp = time.time()
    review_data = {
        "status": decision,
        "checks": checks,
        "notes": notes,
        "reviewed_at": timestamp,
        "reviewed_by": "WEB_HUMAN",
        "video_sha256": report.get("technical_qc", {}).get("video_sha256", ""),
    }
    history = output / "reviews"
    history.mkdir(parents=True, exist_ok=True)
    history_path = history / f"{round(timestamp * 1000)}-{decision.lower()}.json"
    history_path.write_text(json.dumps(review_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["human_review"] = review_data
    report["expansion_allowed"] = decision == "PASS"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status(project)


def finalize(project: Path) -> dict[str, object]:
    project = Path(project).resolve()
    output = project / RELATIVE_DIR
    video = output / "performance.mp4"
    report_path = output / "performance-report.json"
    if not video.is_file() or not report_path.is_file():
        raise ValueError("固定角色样段尚未完成")
    media = probe_video(video)
    report = _read(report_path, {})
    report["technical_qc"] = {
        "media": media,
        "video_sha256": _sha256(video),
        "video_bytes": video.stat().st_size,
        "renderer_sha256": _sha256(ROOT / "scripts/blender_mpfb_modern_pilot.py"),
        "asset_manifest_sha256": _sha256(project / ASSET_MANIFEST),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status(project)


def build(project: Path) -> dict[str, object]:
    project = Path(project).resolve()
    if not (project / "novel-anime-project.json").is_file():
        raise ValueError("当前项目不存在")
    install_makehuman_assets(project / ASSET_MANIFEST.parent)
    blender = blender_executable()
    if not blender:
        raise ValueError("制作固定角色样段需要本机 Blender")
    output = project / RELATIVE_DIR
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            blender,
            "--background",
            "--python",
            str(ROOT / "scripts/blender_mpfb_modern_pilot.py"),
            "--",
            str(project),
            str(output),
        ],
        check=True,
        cwd=ROOT,
        timeout=600,
    )
    if not (output / "performance.mp4").is_file() or not (output / "performance-report.json").is_file():
        raise ValueError("Blender 未生成固定角色剧情样段")
    return finalize(project)
