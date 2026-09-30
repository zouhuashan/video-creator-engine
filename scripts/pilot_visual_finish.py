"""P47-08 visual references and a single-shot, provider-neutral handoff.

This module performs local file/QC work only. It never starts image/video APIs,
copies Codex credentials, or turns a still image into an approved moving shot.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from PIL import Image

from adapters.video_generation.wavespeed_wan import probe_video
from scripts import humanoid_performance as performance
from scripts.episode_workbench import characters
from scripts.modern_asset_library import _atomic, load_library, register_asset, review_asset

STATE = Path("production/character-performance/p47-08-visual-finish/state.json")
DIRECTORY = STATE.parent
ROLES = ("character", "scene", "keyframe", "end_keyframe")
RESULT_CHECKS = ("identity", "scene", "continuous_motion", "hand_contact", "expression", "temporal_stability")
_LOCK = threading.RLock()


def _read(project):
    path = project / STATE
    return json.loads(path.read_text()) if path.is_file() else {
        "schema_version": 1, "revision": 0, "assets": {}, "control_review": {}, "package": {}, "result": {},
    }


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _stream_sha(stream)


def _stream_sha(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _safe(project, relative):
    path = (project / str(relative)).resolve()
    if not path.is_relative_to(project.resolve()) or not path.is_file():
        raise ValueError("文件不属于当前项目或已不存在")
    return path


def _save(project, data, action):
    data["revision"] += 1
    data["updated_at"] = time.time()
    _atomic(project / STATE, data)
    log = project / "logs/p47-08-visual-finish.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": data["updated_at"], "action": action, "revision": data["revision"]}) + "\n")


def _expect(data, payload):
    if isinstance(payload.get("expected_revision"), bool) or payload.get("expected_revision") != data["revision"]:
        raise ValueError("资料已变化，请刷新后再操作")


def _snapshot(project, data):
    base = performance.status(project)
    control_path = project / base["output"]
    control_sha = _sha(control_path) if base["ready"] else ""
    assets = {}
    library = load_library(project)
    for role in ROLES:
        item = data["assets"].get(role)
        if not item:
            continue
        try:
            current_sha = _sha(_safe(project, item["path"]))
        except ValueError:
            current_sha = ""
        current = next((a for a in library["assets"] if a["path"] == item["path"]
                        and a["entity_id"] == item["entity_id"] and a["variant"] == item["variant"]), {})
        approved = current_sha == item["sha256"] and current.get("review_status") == "APPROVED"
        assets[role] = {**item, "review_status": current.get("review_status", "PENDING"), "approved": approved,
                        "fresh": bool(current_sha and current_sha == item["sha256"])}
    body = {"control_sha256": control_sha, "assets": {r: assets.get(r, {}).get("sha256", "") for r in ROLES}}
    signature = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    accepted = bool(control_sha and data.get("control_review", {}).get("sha256") == control_sha
                    and data["control_review"].get("status") == "ACCEPTED_AS_CONTROL")
    approved = len(assets) == len(ROLES) and all(a["approved"] for a in assets.values())
    return base, assets, signature, accepted, approved


def status(project):
    project = Path(project).resolve()
    with _LOCK:
        data = _read(project)
        base, assets, signature, accepted, approved = _snapshot(project, data)
        package = data.get("package", {})
        package_fresh = bool(package and package.get("signature") == signature and accepted and approved
                             and (project / package.get("path", "")).is_file())
        result = dict(data.get("result", {}))
        try:
            result_fresh = package_fresh and result.get("package_signature") == signature and _sha(_safe(project, result.get("path", ""))) == result.get("sha256")
        except ValueError:
            result_fresh = False
        review = result.get("review", {})
        can_expand = bool(result_fresh and review.get("status") == "PASS"
                          and review.get("video_sha256") == result.get("sha256")
                          and all(review.get("checks", {}).get(k) is True for k in RESULT_CHECKS))
        blockers = []
        if not base["ready"] or not base["technical_contact_pass"]:
            blockers.append("当前控制镜头尚未完成技术检查")
        if not approved:
            blockers.append("角色、场景和首尾目标关键帧需要逐项审核通过")
        if not accepted:
            blockers.append("需确认当前动作仅作为控制参考，画质由后续生成补齐")
        return {"task": "P47-08", "project_id": project.name, "revision": data["revision"],
                "assets": assets, "control": {"path": base["output"], "sha256": signature and _snapshot_control_sha(project, base), "accepted": accepted},
                "can_prepare": not blockers, "blockers": blockers, "signature": signature,
                "package": {**package, "fresh": package_fresh},
                "result": {**result, "fresh": bool(result_fresh)}, "result_checks": list(RESULT_CHECKS),
                "can_expand": can_expand, "publishing_allowed": False,
                "characters": [{"id": c["id"], "name": c["name"]} for c in characters(project)],
                "image_execution": "CODEX_IMAGE_TOOL_OR_LOCAL_IMPORT", "api_calls_started": 0}


def _snapshot_control_sha(project, base):
    return _sha(project / base["output"]) if base["ready"] else ""


def register_image(project, *, role, content, character_id="", source="local_import", prompt=""):
    project = Path(project).resolve()
    if role not in ROLES or not 0 < len(content) <= 12 * 1024 * 1024:
        raise ValueError("请提供不超过 12MB 的角色、场景或关键帧图片")
    if role == "character" and character_id not in {c["id"] for c in characters(project)}:
        raise ValueError("角色不属于当前项目")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 30_000_000 or image.width < 240 or image.height < 240:
                raise ValueError("图片尺寸不适合角色参考")
            image.verify()
            extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format]
    except (OSError, KeyError) as error:
        raise ValueError("请使用有效 PNG/JPEG/WebP 图片") from error
    with _LOCK:
        data = _read(project)
        digest = hashlib.sha256(content).hexdigest()
        existing = data["assets"].get(role, {})
        if existing.get("sha256") == digest and (role != "character" or existing.get("entity_id") == character_id):
            current = status(project)
            registered = any(a["path"] == existing["path"] and a["entity_id"] == existing["entity_id"]
                             and a["variant"] == existing["variant"] for a in load_library(project)["assets"])
            if registered and current["assets"][role]["fresh"]:
                return current
        asset = register_asset(project, kind="character" if role == "character" else "scene",
                               entity_id=character_id if role == "character" else "SCN-P47-08-ROOM",
                               variant="pilot_" + role, content=content, extension=extension)
        data["assets"][role] = {**asset, "source": str(source)[:200], "prompt": str(prompt)[:6000]}
        _save(project, data, "register_" + role)
        return status(project)


def upload_image(project, payload):
    with _LOCK:
        _expect(_read(project), payload)
        try:
            content = base64.b64decode(payload.get("content_base64", ""), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("图片上传数据无效") from error
        return register_image(project, role=payload.get("role"), character_id=payload.get("character_id", ""), content=content)


def review_image(project, payload):
    with _LOCK:
        data = _read(project)
        _expect(data, payload)
        asset = data["assets"].get(payload.get("role"))
        if not asset or payload.get("sha256") != asset["sha256"] or _sha(_safe(project, asset["path"])) != asset["sha256"]:
            raise ValueError("参考图已变化，请重新查看后审核")
        if payload.get("decision") not in ("APPROVED", "REJECTED"):
            raise ValueError("请选择通过或退回")
        review_asset(project, asset["path"], payload["decision"], str(payload.get("notes", ""))[:2000])
        _save(project, data, "review_" + payload["role"])
        return status(project)


def accept_control(project, payload):
    with _LOCK:
        data = _read(project)
        _expect(data, payload)
        base = performance.status(project)
        if not base["ready"] or not base["technical_contact_pass"]:
            raise ValueError("请先完成控制镜头技术检查")
        digest = _sha(project / base["output"])
        if payload.get("sha256") != digest or payload.get("accept_as_control") is not True:
            raise ValueError("请播放当前控制镜头，并明确接受其仅作为动作参考")
        data["control_review"] = {"status": "ACCEPTED_AS_CONTROL", "sha256": digest, "at": time.time(), "reviewed_by": "WEB_HUMAN"}
        _save(project, data, "accept_control")
        return status(project)


def prepare_package(project, payload):
    project = Path(project).resolve()
    with _LOCK:
        data = _read(project)
        _expect(data, payload)
        current = status(project)
        if not current["can_prepare"]:
            raise ValueError("；".join(current["blockers"]))
        signature = current["signature"]
        if current["package"]["fresh"]:
            return current
        target = project / DIRECTORY / "packages" / signature
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target) as temporary:
            folder = Path(temporary)
            control = _safe(project, current["control"]["path"])
            shutil.copy2(control, folder / "control.mp4")
            media = probe_video(control)
            for role, item in current["assets"].items():
                shutil.copy2(_safe(project, item["path"]), folder / (role + Path(item["path"]).suffix))
            for name, seek in (("control-first.png", ["-ss", "0"]), ("control-last.png", ["-sseof", "-0.05"])):
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *seek, "-i", str(control),
                                "-frames:v", "1", str(folder / name)], check=True, capture_output=True, timeout=60)
            prompt = ("使用 control.mp4 作为单镜动作、走位和时序参考。保持一次连续镜头，读取手机、抬眼、轻微面部反应及手指收紧的动作顺序；"
                      "人物身份、发型和服装以 character 参考为准，房间、桌面和夜间光线以 scene 参考为准。"
                      "keyframe 定义低头看手机的目标首帧美术，end_keyframe 定义抬眼反应的目标尾帧美术；两张图都不是已渲染的动作帧。"
                      "镜头不得变为静态图片推拉。保持五指、手腕和手机接触，手机不悬空；表情自然克制。"
                      f"时长 {media['duration_seconds']:.2f} 秒，竖屏；生成视觉即可，正式配音、字幕和混音由本地完成。"
                      "若所用服务不支持控制视频加多图，不得声称可锁定动作；应选择其真实支持的输入模式，并记录差异。")
            (folder / "prompt-zh.txt").write_text(prompt, encoding="utf-8")
            (folder / "negative-constraints.txt").write_text("身份漂移、换衣、畸形手指、手机悬空、穿模、僵硬眼神、脸部闪烁、静态缩放、突然剪切、额外人物、字幕、水印。", encoding="utf-8")
            contract = {"schema_version": 1, "task": "P47-08", "project_id": project.name, "package_signature": signature,
                        "duration_seconds": media["duration_seconds"], "width": media["width"], "height": media["height"],
                        "visual_provider": "manual_replaceable", "audio_strategy": "LOCAL_AFTER_VISUAL_REVIEW",
                        "assets": {role: {"entity_id": a["entity_id"], "sha256": a["sha256"]} for role, a in current["assets"].items()},
                        "control_sha256": current["control"]["sha256"], "review_checks": list(RESULT_CHECKS),
                        "publishing_allowed": False, "cost": {"local_package_rmb": 0, "remote_generation_started": False}}
            (folder / "scene.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            (folder / "README.txt").write_text("这是待人工生成的单镜素材包，不是已完成视频。\n按所选服务实际输入能力使用控制视频与参考图；人工生成可能计费。\n返回 Web 导入结果，完整播放并确认角色、场景、动作、手部、表情、闪烁六项后才能扩展。", encoding="utf-8")
            archive = target / "generation-package.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file in sorted(folder.iterdir()):
                    zip_file.write(file, file.name)
            shutil.copy2(folder / "scene.json", target / "scene.json")
            shutil.copy2(folder / "prompt-zh.txt", target / "prompt-zh.txt")
        data["package"] = {"path": archive.relative_to(project).as_posix(), "signature": signature,
                           "contract_path": (target / "scene.json").relative_to(project).as_posix(),
                           "prompt_path": (target / "prompt-zh.txt").relative_to(project).as_posix(),
                           "duration_seconds": media["duration_seconds"], "created_at": time.time()}
        _save(project, data, "prepare_package")
        return status(project)


def import_result(project, payload):
    project = Path(project).resolve()
    with _LOCK:
        data = _read(project)
        _expect(data, payload)
        current = status(project)
        if not current["package"]["fresh"] or payload.get("package_signature") != current["signature"]:
            raise ValueError("请先审核素材并导出当前版本生成包")
        try:
            content = base64.b64decode(payload.get("content_base64", ""), validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError("视频上传数据无效") from error
        if not 0 < len(content) <= 40 * 1024 * 1024:
            raise ValueError("请上传不超过 40MB 的单镜 MP4")
        digest = hashlib.sha256(content).hexdigest()
        if digest == current["control"]["sha256"]:
            raise ValueError("不能把原控制视频当作最终视觉结果，请导入生成后的单镜")
        if current["result"]["fresh"] and data.get("result", {}).get("sha256") == digest and data["result"].get("package_signature") == current["signature"]:
            return current
        folder = project / DIRECTORY / "results" / current["signature"] / digest
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / "result.mp4"
        video.write_bytes(content)
        try:
            media = probe_video(video)
            seconds = current["package"]["duration_seconds"]
            if abs(media["duration_seconds"] - seconds) > 0.35:
                raise ValueError(f"结果时长须与控制镜头 {seconds:.2f} 秒一致（误差不超过 0.35 秒）")
            control = probe_video(_safe(project, current["control"]["path"]))
            if media["width"] < 240 or abs(media["width"] / media["height"] - control["width"] / control["height"]) > 0.02:
                raise ValueError("结果须使用与控制镜头一致的竖屏比例")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(video),
                            "-map", "0:v:0", "-f", "null", "-"], check=True, capture_output=True, timeout=90)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                            "-frames:v", "1", str(folder / "poster.png")], check=True, capture_output=True, timeout=60)
        except Exception:
            video.unlink(missing_ok=True)
            raise
        result = {"path": video.relative_to(project).as_posix(), "poster": (folder / "poster.png").relative_to(project).as_posix(),
                  "sha256": digest, "package_signature": current["signature"], "media": media,
                  "review": {"status": "PENDING"}, "imported_at": time.time(), "technical_qc": "PASS"}
        _atomic(folder / "qc.json", result)
        data["result"] = result
        _save(project, data, "import_result")
        return status(project)


def review_result(project, payload):
    with _LOCK:
        data = _read(project)
        _expect(data, payload)
        current = status(project)
        result = data.get("result", {})
        if not current["result"]["fresh"] or payload.get("sha256") != result.get("sha256"):
            raise ValueError("结果或参考资料已变化，请重新查看当前结果")
        decision = payload.get("decision")
        if decision not in ("PASS", "REJECTED"):
            raise ValueError("请选择通过或退回")
        raw_checks = payload.get("checks", {})
        if not isinstance(raw_checks, dict):
            raise ValueError("请逐项检查画面")
        checks = {key: raw_checks.get(key) is True for key in RESULT_CHECKS}
        notes = str(payload.get("notes", "")).strip()[:2000]
        if decision == "PASS" and not all(checks.values()):
            raise ValueError("通过前需确认全部六项画面检查")
        if decision == "REJECTED" and len(notes) < 2:
            raise ValueError("退回时请填写修改意见")
        result["review"] = {"status": decision, "checks": checks, "notes": notes, "video_sha256": result["sha256"],
                            "reviewed_by": "WEB_HUMAN", "at": time.time()}
        history = project / DIRECTORY / "reviews" / f"{time.time_ns()}.json"
        _atomic(history, result["review"])
        _save(project, data, "review_result")
        return status(project)
