#!/usr/bin/env python3
"""Export one reviewable manual Hailuo H3 shot package.

No network request is made.  The archive contains the local motion/camera
control video, visual references, exact prompt, negative constraints and a QC
contract so a browser generation can be imported and compared later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHOT = "SHOT-S01E001-SC001-001"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg_path() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    fallback = Path("/usr/local/bin/ffmpeg")
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("ffmpeg is required")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--shot-id", default=DEFAULT_SHOT)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--character-reference", type=Path, required=True)
    parser.add_argument("--scene-reference", type=Path, required=True)
    return parser.parse_args()


def prompt_text(shot_id: str) -> str:
    return f"""镜头编号：{shot_id}

将 control.mp4 作为唯一的镜头、人物走位、动作、速度和时序骨架，只替换最终视觉。

严格保持：竖屏构图、透视关系、人物由古宅门内向镜头走来的路径、连续步行节奏、停步时点、最后缓慢抬头的动作、身体重心起伏、人物在画面中的尺寸变化、镜头运动和遮挡关系。不要增加镜头切换，不要改变总时长。

人物身份与服装严格参考 character-reference.png：同一名年轻中国男性，五官清俊冷峻，黑色高马尾，黑蓝长袍配暗红交领和腰封，铜金暗纹、护腕、长靴、腰间佩剑与挂饰。所有帧保持同一张脸、同一发型、同一服装和同一配饰。

场景严格参考 scene-reference.png：夜色古宅门楼，深色木构、石阶、石狮、暖色灯笼、薄雾和雨后湿润石板，远处庭院具有空间层次。冷月环境光与暖灯形成电影级冷暖对比，地面有克制而真实的反射。

0.0–3.4 秒：人物从门内稳定向前走，四次自然步态循环，脚掌真实接触地面，手臂轻微反向摆动，衣摆、发尾和腰间挂饰产生有重量的次级运动。
3.4–4.0 秒：人物减速并停稳，重心自然落定，衣摆延迟回落。
4.0–5.0 秒：人物保持站立，只缓慢抬头看向门上方灯笼，眼神由警觉转为疑惑；摄像机和背景仍严格继承 control.mp4。

画面风格：高质量中国国风动漫电影、写实三维质感与精致数字绘景结合、真实人体结构、细腻皮肤和布料、自然衣发物理、体积雾、电影灯光、稳定细节、24fps 连续运动、9:16。

输出不得包含字幕、标题、UI、平台水印或新文字。灯笼上已有的“府”字保持稳定，不生成其他可读文字。"""


def negative_text() -> str:
    return """禁止改变相机轨迹、镜头焦段、人物路径、动作顺序、步速、停步时点和抬头时点。
禁止换脸、脸部漂移、年龄变化、发型变化、服装变色、配饰消失、剑鞘跳动。
禁止多人物、人物复制、额外肢体、手指畸形、脚底滑行、关节反折、身体穿模。
禁止背景重构、门楼漂移、灯笼位置变化、石狮消失、地面融化、物体闪烁。
禁止突然推拉、镜头抖动、跳帧、慢动作、速度突变、动作回放、画面切换。
禁止过度飘带、无重力衣摆、头发穿脸、塑料皮肤、蜡像感、低清晰度、过度锐化。
禁止字幕、边框、Logo、平台水印和除“府”之外的新文字。"""


def main() -> None:
    cfg = parse_args()
    project = cfg.project.resolve()
    control = cfg.control.resolve()
    character = cfg.character_reference.resolve()
    scene = cfg.scene_reference.resolve()
    for path in (control, character, scene):
        if not path.is_file():
            raise FileNotFoundError(path)
    package_dir = project / "rendering" / "h3-shot-packages" / f"{cfg.shot_id}-p43"
    package_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()

    control_out = package_dir / "control.mp4"
    run([ffmpeg, "-y", "-loglevel", "error", "-i", str(control), "-an", "-c:v", "copy", str(control_out)])
    first = package_dir / "first-frame.png"
    last = package_dir / "last-frame.png"
    run([ffmpeg, "-y", "-loglevel", "error", "-i", str(control_out), "-frames:v", "1", str(first)])
    run([ffmpeg, "-y", "-loglevel", "error", "-sseof", "-0.05", "-i", str(control_out), "-frames:v", "1", str(last)])
    character_out = package_dir / "character-reference.png"
    scene_out = package_dir / "scene-reference.png"
    shutil.copy2(character, character_out)
    shutil.copy2(scene, scene_out)
    (package_dir / "prompt.txt").write_text(prompt_text(cfg.shot_id) + "\n", encoding="utf-8")
    (package_dir / "negative.txt").write_text(negative_text() + "\n", encoding="utf-8")
    (package_dir / "UPLOAD-ORDER.txt").write_text(
        "1. 在海螺 H3 选择参考视频/视频生视频模式。\n"
        "2. 上传 control.mp4 作为动作与镜头骨架。\n"
        "3. 上传 character-reference.png 和 scene-reference.png。\n"
        "4. 粘贴 prompt.txt；如果界面有负面提示词栏，再粘贴 negative.txt。\n"
        "5. 生成 5 秒、9:16；下载结果后回到 VideoCreator Web 的第 3 步导入。\n",
        encoding="utf-8",
    )
    qc = {
        "status": "PENDING_H3_RESULT",
        "automatic_checks": ["duration_is_5s", "resolution_is_vertical", "video_decodes", "no_long_freeze"],
        "human_checks": [
            "same_character_identity_all_frames", "same_costume_and_accessories", "camera_path_matches_control",
            "four_walk_cycles_then_stop", "head_raise_only_after_stop", "feet_do_not_slide",
            "hands_and_face_are_stable", "gate_lantern_lions_and_wet_ground_are_stable", "no_added_text_or_watermark",
        ],
        "decision": "PENDING",
    }
    (package_dir / "qc-checklist.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = [control_out, first, last, character_out, scene_out, package_dir / "prompt.txt",
             package_dir / "negative.txt", package_dir / "UPLOAD-ORDER.txt", package_dir / "qc-checklist.json"]
    manifest = {
        "schema_version": 1,
        "shot_id": cfg.shot_id,
        "status": "PACKAGE_READY",
        "provider_target": "hailuo_h3_manual_web",
        "created_at": int(time.time()),
        "billable_action_performed": False,
        "uploaded": False,
        "duration_seconds": 5.0,
        "fps": 24,
        "aspect_ratio": "9:16",
        "control": str(control_out.relative_to(project)),
        "first_frame": str(first.relative_to(project)),
        "last_frame": str(last.relative_to(project)),
        "character_reference": str(character_out.relative_to(project)),
        "scene_reference": str(scene_out.relative_to(project)),
        "prompt": str((package_dir / "prompt.txt").relative_to(project)),
        "negative": str((package_dir / "negative.txt").relative_to(project)),
        "qc_checklist": str((package_dir / "qc-checklist.json").relative_to(project)),
        "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files],
        "imported_result": "",
        "review_status": "PENDING",
    }
    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = package_dir.parent / f"{cfg.shot_id}-p43-h3-package.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for path in files + [manifest_path]:
            handle.write(path, path.name)
    manifest["archive"] = str(archive.relative_to(project))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
