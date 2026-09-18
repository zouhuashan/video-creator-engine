#!/usr/bin/env python3
"""Prepare three local, non-billable input bundles for P28 motion-provider comparison."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video.video_use import _media_tool, video_use_environment
from scripts.novel_acceptance import load_acceptance, validate_acceptance, write_acceptance
from scripts.novel_anime_project import utc_timestamp


TEST_SPECS = (
    {
        "id": "MOTIONTEST-001",
        "shot_id": "SHOT-S01E001-SC001-001",
        "provider": "runway",
        "label": "小蓬莱云海与玉碑环境运动",
        "source": "renders/episode-segments/shot-s01e001-sc001-001-draft.png",
        "source_kind": "image",
        "start_frame": "provider-tests/s01e001/motiontest-001-penglai-start.png",
        "prompt": "国风绢本设色动态漫。镜头缓慢向玉碑推进，云海分层流动，日光掠过碑面，少量花瓣随风穿过前景；建筑、玉碑纹样和竖屏构图保持稳定，不新增人物，不出现文字。",
        "motion_goal": "环境层次、镜头推进、云雾稳定性",
    },
    {
        "id": "MOTIONTEST-002",
        "shot_id": "SHOT-S01E001-SC002-001",
        "provider": "wan",
        "label": "百草仙子对白轻动作",
        "source": "renders/batch/shot-s01e001-sc002-001-final.mp4",
        "source_kind": "video_frame",
        "start_frame": "provider-tests/s01e001/motiontest-002-baicao-start.png",
        "prompt": "保持百草仙子的脸、发饰、服装纹样和身形完全一致。角色自然呼吸，轻微眨眼，发梢与袖摆受微风摆动，口部只做克制的说话动作；背景云海缓慢漂移，镜头稳定，不改变手指数目，不改变服装，不切镜。",
        "motion_goal": "角色身份一致、微表情、口部与衣摆自然度",
    },
    {
        "id": "MOTIONTEST-003",
        "shot_id": "SHOT-S01E001-SC003-001",
        "provider": "openai_sora",
        "label": "嫦娥瑶池花瓣与衣袂动作",
        "source": "renders/batch/shot-s01e001-sc003-002-final.mp4",
        "source_kind": "video_frame",
        "start_frame": "provider-tests/s01e001/motiontest-003-change-start.png",
        "prompt": "保持嫦娥面容、发髻、首饰和浅青白金服饰一致。角色含笑抬眼，衣袂和长发轻柔摆动，花瓣从近景掠过，远处云海与瀑布缓慢流动；国风绢本设色，竖屏固定镜头，不新增角色，不变形，不出现文字。",
        "motion_goal": "角色一致性、布料运动、粒子和远景运动协调",
    },
)


def _materialize_start_frame(project: Path, spec: dict[str, str]) -> Path:
    source = project / spec["source"]
    output = project / spec["start_frame"]
    if not source.is_file():
        raise ValueError(f"provider test source is missing: {spec['source']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if spec["source_kind"] == "image":
        shutil.copy2(source, output)
    else:
        ffmpeg = _media_tool("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is unavailable")
        subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", "0.200", "-i", str(source), "-frames:v", "1", str(output)], check=True, capture_output=True, env=video_use_environment())
    return output


def prepare(project: Path) -> dict[str, object]:
    project = project.expanduser().resolve()
    output_path = project / "provider-tests" / "s01e001" / "motion-provider-tests.json"
    existing_package = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else {}
    existing_tests = {str(item.get("id")): item for item in existing_package.get("tests", []) if isinstance(item, dict)}
    tests = []
    for spec in TEST_SPECS:
        output = _materialize_start_frame(project, spec)
        test = {
            "id": spec["id"],
            "episode_id": "S01E001",
            "shot_id": spec["shot_id"],
            "label": spec["label"],
            "provider": spec["provider"],
            "adapter_id": spec["provider"],
            "model": "configured_default",
            "start_frame": output.relative_to(project).as_posix(),
            "source": spec["source"],
            "prompt": spec["prompt"],
            "negative_constraints": ["禁止角色换脸", "禁止服装变色", "禁止多余肢体", "禁止新增文字或水印", "禁止切换画幅"],
            "motion_goal": spec["motion_goal"],
            "target_duration_seconds": 5,
            "target_aspect_ratio": "9:16",
            "output_path": f"provider-tests/s01e001/outputs/{spec['id'].lower()}-{spec['provider']}.mp4",
            "status": "BLOCKED_PENDING_AUTHORIZATION",
            "upload_authorized": False,
            "billable_confirmed": False,
            "cost_usd": None,
            "result": None,
            "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""},
        }
        previous = existing_tests.get(spec["id"])
        if previous and previous.get("start_frame") == test["start_frame"] and previous.get("prompt") == test["prompt"] and previous.get("provider") == test["provider"]:
            for key in ("status", "upload_authorized", "billable_confirmed", "cost_usd", "result", "human_review"):
                if key in previous:
                    test[key] = previous[key]
        tests.append(test)
    now = utc_timestamp()
    package = {
        "schema_version": 1,
        "project_id": project.name,
        "episode_id": "S01E001",
        "created_at": existing_package.get("created_at") or now,
        "updated_at": now,
        "status": "PREPARED",
        "remote_execution": "BLOCKED_PENDING_AUTHORIZATION",
        "tests": tests,
        "comparison_metrics": ["identity_consistency", "motion_naturalness", "prompt_adherence", "artifact_rate", "generation_seconds", "cost_usd"],
        "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""},
    }
    output_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    acceptance = load_acceptance(project)
    prepared = {item["id"]: item for item in tests}
    changed = False
    for item in acceptance["motion_tests"]:
        test = prepared[item["id"]]
        result = test.get("result") if isinstance(test.get("result"), dict) else {}
        acceptance_status = test.get("status") if test.get("status") in {"SUCCEEDED", "FAILED"} else "NOT_RUN"
        desired = {
            "episode_id": test["episode_id"],
            "shot_id": test["shot_id"],
            "provider": test["provider"],
            "status": acceptance_status,
            "cost_usd": test.get("cost_usd") if acceptance_status != "NOT_RUN" else None,
            "duration_seconds": result.get("duration_seconds") if acceptance_status != "NOT_RUN" else None,
            "consistency_status": str(result.get("consistency_status") or "NOT_ASSESSED") if acceptance_status != "NOT_RUN" else "NOT_ASSESSED",
            "note": "本地输入包已准备；待显式确认素材上传与计费后运行。" if acceptance_status == "NOT_RUN" else str(result.get("note") or "动作 Provider 测试已回写。"),
        }
        if any(item.get(key) != value for key, value in desired.items()):
            item.update(desired)
            changed = True
    if changed:
        acceptance["revision"] = int(acceptance.get("revision", 1)) + 1
        acceptance["updated_at"] = now
        write_acceptance(project, validate_acceptance(project, acceptance), overwrite=True)
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.project_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
