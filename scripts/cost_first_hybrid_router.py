#!/usr/bin/env python3
"""P36 cost-first hybrid renderer planner.

This planner deliberately treats paid remote video generation as the last
resort.  It classifies every shot using script semantics plus shot metadata,
estimates the user's observed H3 cost, deduplicates reusable still-image
requirements, and writes a plan that Web can inspect before any billable call.

No remote provider is called from this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import load_shot_breakdown


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cost-first-rendering.json"
OUTPUT = Path("rendering/cost-first-plan.json")
SHOT_TIMING_OUTPUT = Path("audio/shot-timing.json")


class CostFirstRoutingError(RuntimeError):
    pass


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_config() -> dict[str, Any]:
    try:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CostFirstRoutingError(f"cannot read cost-first policy: {error}") from error
    return payload


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _voice_timing_signature(project: Path) -> str:
    path = Path(project).resolve() / SHOT_TIMING_OUTPUT
    if not path.is_file():
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _actual_tts_timings(project: Path) -> dict[str, dict[str, Any]]:
    path = Path(project).resolve() / SHOT_TIMING_OUTPUT
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if str(payload.get("source") or "").upper() != "VOICE_TIMELINE":
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("shots", []):
        if not isinstance(item, dict) or str(item.get("timing_source") or "").upper() != "ACTUAL_TTS":
            continue
        shot_id = str(item.get("shot_id") or "").strip()
        try:
            duration = float(item.get("recommended_duration_seconds") or 0)
        except (TypeError, ValueError):
            continue
        if shot_id and duration > 0:
            result[shot_id] = {**item, "recommended_duration_seconds": duration}
    return result


def _scene_index(script_package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for episode in script_package["episode_scripts"]:
        for scene in episode["scenes"]:
            result[str(scene["id"])] = {
                **scene,
                "episode_id": str(episode["episode_id"]),
            }
    return result


def _keyword_hits(text: str, values: list[str]) -> list[str]:
    source = str(text or "")
    return sorted({item for item in values if item and item in source})


def _motion_analysis(scene: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    units = scene.get("units") or []
    kinds = [str(unit.get("kind") or "") for unit in units]
    text = " ".join(str(unit.get("text") or "") for unit in units)
    keywords = config["motion_keywords"]
    high = _keyword_hits(text, list(keywords.get("high") or []))
    medium = _keyword_hits(text, list(keywords.get("medium") or []))
    subtle = _keyword_hits(text, list(keywords.get("subtle") or []))

    action_count = kinds.count("ACTION")
    visual_count = kinds.count("VISUAL")
    dialogue_count = kinds.count("DIALOGUE")
    narration_count = kinds.count("NARRATION")
    sfx_count = kinds.count("SFX")
    characters = list(scene.get("character_ids") or [])

    score = 0.0
    score += action_count * 1.25
    score += visual_count * 0.35
    score += len(high) * 4.0
    score += len(medium) * 1.6
    score += len(subtle) * 0.35
    score += max(0, len(characters) - 1) * 0.45
    if action_count == 0 and dialogue_count + narration_count > 0:
        score -= 0.35
    if sfx_count and action_count:
        score += 0.25
    score = round(max(0.0, score), 2)

    return {
        "score": score,
        "high_keywords": high,
        "medium_keywords": medium,
        "subtle_keywords": subtle,
        "unit_counts": {
            "ACTION": action_count,
            "VISUAL": visual_count,
            "DIALOGUE": dialogue_count,
            "NARRATION": narration_count,
            "SFX": sfx_count,
        },
        "character_count": len(characters),
        "text_excerpt": text[:400],
    }


def _visual_signature(scene: dict[str, Any]) -> str:
    location = str(scene.get("location_id") or "NO-LOCATION")
    time_of_day = re.sub(r"\s+", "-", str(scene.get("time_of_day") or "UNSPECIFIED").strip().upper())
    chars = ",".join(sorted(str(item) for item in scene.get("character_ids") or [])) or "NO-CHARACTER"
    return f"{location}|{time_of_day}|{chars}"


def _select_route(
    *,
    shot: dict[str, Any],
    scene: dict[str, Any],
    motion: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    thresholds = config["route_thresholds"]
    policy = config["policy"]
    score = float(motion["score"])
    duration = float(shot.get("duration_seconds") or 1.0)
    has_high = bool(motion["high_keywords"])
    has_medium = bool(motion["medium_keywords"])
    character_count = int(motion["character_count"])
    only_dialogue_or_narration = (
        motion["unit_counts"]["ACTION"] == 0
        and motion["unit_counts"]["VISUAL"] == 0
        and (motion["unit_counts"]["DIALOGUE"] + motion["unit_counts"]["NARRATION"]) > 0
    )

    reasons: list[str] = []
    if not character_count:
        route = "LOCAL_SCENE_PLATE"
        required_stills = 1
        reasons.append("无角色动作，场景图 + 本地镜头运动即可")
    elif only_dialogue_or_narration and duration <= float(policy["max_local_single_still_seconds"]):
        route = "LOCAL_MICRO_MOTION"
        required_stills = 1
        reasons.append("对白/旁白为主且无显式动作，用单张角色画面做本地微动")
    elif not has_high and score <= float(thresholds["local_single_still_max_score"]) and duration <= float(policy["max_local_single_still_seconds"]):
        route = "LOCAL_MICRO_MOTION"
        required_stills = 1
        reasons.append("运动复杂度低，单张最终图 + 本地连续镜头运动优先")
    elif not has_high and score <= float(thresholds["local_two_cut_max_score"]) and duration <= float(policy["max_local_two_cut_seconds"]):
        route = "LOCAL_TWO_CUT"
        required_stills = 2
        reasons.append("中低运动镜头，优先拆成两段静帧切镜而不是生成整段 AI 视频")
        if has_medium:
            reasons.append("存在中等动作词：" + "、".join(motion["medium_keywords"][:4]))
    else:
        route = "H3_CANDIDATE"
        required_stills = 0
        reasons.append("连续动作复杂度超过本地静帧路线的安全范围")
        if has_high:
            reasons.append("高动态动作词：" + "、".join(motion["high_keywords"][:4]))

    h3_locked = route == "H3_CANDIDATE"
    return {
        "route": route,
        "required_new_stills": required_stills,
        "h3_locked": h3_locked,
        "h3_escalation_status": "REQUIRES_MANUAL_APPROVAL" if h3_locked else "NOT_NEEDED",
        "reasons": reasons,
    }


def diagnostics(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    script_root = project / "writing-room" / "episodes"
    shot_path = project / "storyboard" / "shot-breakdown.json"
    timing_path = project / SHOT_TIMING_OUTPUT
    plan_path = project / OUTPUT

    result: dict[str, Any] = {
        "checked_at": _now(),
        "project_id": project.name,
        "episode_script": {
            "path": "writing-room/episodes",
            "exists": script_root.is_dir(),
            "json_file_count": len(list(script_root.rglob("*.json"))) if script_root.is_dir() else 0,
            "revision": None,
            "episode_count": 0,
            "scene_count": 0,
            "unit_count": 0,
            "error": "",
        },
        "shot_breakdown": {
            "path": "storyboard/shot-breakdown.json",
            "exists": shot_path.is_file(),
            "revision": None,
            "scene_count": 0,
            "shot_count": 0,
            "error": "",
        },
        "voice_timing": {
            "path": SHOT_TIMING_OUTPUT.as_posix(),
            "exists": timing_path.is_file(),
            "actual_tts_count": len(_actual_tts_timings(project)),
            "error": "",
        },
        "plan": {
            "path": OUTPUT.as_posix(),
            "exists": plan_path.is_file(),
            "status": "",
            "route_count": 0,
            "error": "",
        },
        "blockers": [],
        "status": "BLOCKED",
    }

    try:
        scripts = load_script_package(project)
        episode_scripts = list(scripts.get("episode_scripts") or [])
        scenes = [scene for episode in episode_scripts for scene in (episode.get("scenes") or [])]
        units = [unit for scene in scenes for unit in (scene.get("units") or [])]
        result["episode_script"].update({
            "revision": scripts.get("revision"),
            "episode_count": len(episode_scripts),
            "scene_count": len(scenes),
            "unit_count": len(units),
        })
    except Exception as error:
        result["episode_script"]["error"] = f"{type(error).__name__}: {error}"

    try:
        shots = load_shot_breakdown(project)
        scene_breakdowns = list(shots.get("scene_breakdowns") or [])
        shot_items = [shot for scene in scene_breakdowns for shot in (scene.get("shots") or [])]
        result["shot_breakdown"].update({
            "revision": shots.get("revision"),
            "scene_count": len(scene_breakdowns),
            "shot_count": len(shot_items),
        })
    except Exception as error:
        result["shot_breakdown"]["error"] = f"{type(error).__name__}: {error}"

    if plan_path.is_file():
        try:
            raw_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            result["plan"].update({
                "status": str(raw_plan.get("status") or ""),
                "route_count": len(raw_plan.get("routes") or []),
            })
        except (OSError, json.JSONDecodeError) as error:
            result["plan"]["error"] = f"{type(error).__name__}: {error}"

    blockers: list[str] = []
    script_error = str(result["episode_script"]["error"] or "")
    shot_error = str(result["shot_breakdown"]["error"] or "")
    if script_error:
        blockers.append("Episode Script 读取失败：" + script_error)
    elif int(result["episode_script"]["scene_count"]) == 0:
        blockers.append("Episode Script 当前有 0 个 scene；P36 无法生成 Shot。")
    if shot_error:
        blockers.append("Shot Breakdown 读取失败：" + shot_error)
    elif int(result["shot_breakdown"]["shot_count"]) == 0:
        blockers.append("Shot Breakdown 当前有 0 个 Shot。")
    result["blockers"] = blockers
    result["status"] = "READY" if not blockers else "BLOCKED"
    return result


def build_plan(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    config = _load_config()
    shots = load_shot_breakdown(project)
    scripts = load_script_package(project)
    scenes = _scene_index(scripts)
    shell_rate = float(config["policy"]["h3_empirical_shell_per_second"])
    actual_tts_timings = _actual_tts_timings(project)
    voice_timing_signature = _voice_timing_signature(project)

    routes: list[dict[str, Any]] = []
    reuse_requirements: dict[str, dict[str, Any]] = {}
    all_h3_shells = 0.0
    hybrid_h3_shells = 0.0

    for scene_breakdown in shots["scene_breakdowns"]:
        scene_id = str(scene_breakdown["scene_id"])
        scene = scenes.get(scene_id)
        if scene is None:
            raise CostFirstRoutingError(f"script scene missing for shot routing: {scene_id}")
        motion = _motion_analysis(scene, config)
        signature = _visual_signature(scene)

        for shot in scene_breakdown["shots"]:
            shot_id = str(shot["id"])
            source_duration = float(shot.get("duration_seconds") or 1.0)
            actual_timing = actual_tts_timings.get(shot_id)
            if actual_timing:
                duration = float(actual_timing["recommended_duration_seconds"])
                timing_source = "ACTUAL_TTS"
            else:
                duration = source_duration
                timing_source = "SHOT_BREAKDOWN"
            effective_shot = {**shot, "duration_seconds": duration}
            selected = _select_route(shot=effective_shot, scene=scene, motion=motion, config=config)
            h3_estimate = round(duration * shell_rate, 1)
            all_h3_shells += h3_estimate
            if selected["route"] == "H3_CANDIDATE":
                hybrid_h3_shells += h3_estimate

            still_count = int(selected["required_new_stills"])
            reuse_key = signature if still_count else ""
            if still_count:
                entry = reuse_requirements.setdefault(reuse_key, {
                    "reuse_key": reuse_key,
                    "location_id": scene.get("location_id"),
                    "time_of_day": scene.get("time_of_day"),
                    "character_ids": list(scene.get("character_ids") or []),
                    "max_required_stills": 0,
                    "shot_ids": [],
                })
                entry["max_required_stills"] = max(int(entry["max_required_stills"]), still_count)
                entry["shot_ids"].append(str(shot["id"]))

            routes.append({
                "episode_id": str(scene["episode_id"]),
                "scene_id": scene_id,
                "shot_id": shot_id,
                "duration_seconds": round(duration, 3),
                "source_duration_seconds": round(source_duration, 3),
                "timing_source": timing_source,
                "shot_type": str(shot.get("shot_type") or ""),
                "camera_movement": str(shot.get("movement") or ""),
                "motion": motion,
                "visual_reuse_key": reuse_key,
                "h3_full_cost_shells": h3_estimate,
                "hybrid_cost_shells": h3_estimate if selected["route"] == "H3_CANDIDATE" else 0.0,
                "estimated_shells_saved": 0.0 if selected["route"] == "H3_CANDIDATE" else h3_estimate,
                "h3_escalation": {
                    "status": selected["h3_escalation_status"],
                    "approved": False,
                    "reason": "",
                    "approved_at": "",
                },
                **selected,
            })

    local_still_generations = sum(int(item["max_required_stills"]) for item in reuse_requirements.values())
    all_h3_shells = round(all_h3_shells, 1)
    hybrid_h3_shells = round(hybrid_h3_shells, 1)
    savings = round(max(0.0, all_h3_shells - hybrid_h3_shells), 1)
    savings_percent = round((savings / all_h3_shells * 100.0) if all_h3_shells else 0.0, 1)

    status = "PLANNED" if routes else "BLOCKED_NO_SHOTS"
    blockers = [] if routes else [
        "当前项目没有可供 P36 路由的 Shot；请先生成/重建 Episode Script 与 Shot Breakdown。"
    ]

    return {
        "schema_version": 1,
        "project_id": project.name,
        "status": status,
        "blockers": blockers,
        "policy": {
            "name": config["policy"]["name"],
            "remote_video_last_resort": True,
            "h3_empirical_shell_per_second": shell_rate,
            "h3_requires_manual_escalation": True,
            "default_local_fps": int(config["policy"].get("default_local_fps") or 24),
            "local_preview_width": int(config["policy"].get("local_preview_width") or 720),
            "local_preview_height": int(config["policy"].get("local_preview_height") or 1280),
        },
        "shot_breakdown_revision": int(shots["revision"]),
        "script_revision": int(scripts["revision"]),
        "voice_timing_signature": voice_timing_signature,
        "summary": {
            "shot_count": len(routes),
            "actual_tts_duration_count": sum(1 for item in routes if item["timing_source"] == "ACTUAL_TTS"),
            "shot_breakdown_duration_count": sum(1 for item in routes if item["timing_source"] == "SHOT_BREAKDOWN"),
            "local_route_count": sum(1 for item in routes if item["route"] != "H3_CANDIDATE"),
            "h3_candidate_count": sum(1 for item in routes if item["route"] == "H3_CANDIDATE"),
            "local_single_still_count": sum(1 for item in routes if item["route"] in {"LOCAL_SCENE_PLATE", "LOCAL_MICRO_MOTION"}),
            "local_two_cut_count": sum(1 for item in routes if item["route"] == "LOCAL_TWO_CUT"),
            "estimated_new_still_generations_after_reuse": local_still_generations,
            "all_h3_estimated_shells": all_h3_shells,
            "hybrid_h3_estimated_shells": hybrid_h3_shells,
            "estimated_shells_saved": savings,
            "estimated_shell_savings_percent": savings_percent,
        },
        "reuse_requirements": list(reuse_requirements.values()),
        "routes": routes,
        "created_at": _now(),
        "updated_at": _now(),
    }


def save_plan(project: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    project = Path(project).resolve()
    plan = payload or build_plan(project)
    _atomic_json(project / OUTPUT, plan)
    return plan


def load_plan(project: Path, *, rebuild_if_stale: bool = True) -> dict[str, Any]:
    project = Path(project).resolve()
    path = project / OUTPUT
    if not path.is_file():
        return save_plan(project)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return save_plan(project)

    routes = list(payload.get("routes") or [])
    expected_status = "PLANNED" if routes else "BLOCKED_NO_SHOTS"
    migrated = str(payload.get("status") or "") != expected_status
    payload["status"] = expected_status
    if routes:
        payload["blockers"] = []
    elif not payload.get("blockers"):
        payload["blockers"] = [
            "当前项目没有可供 P36 路由的 Shot；请先生成/重建 Episode Script 与 Shot Breakdown。"
        ]
    if migrated:
        payload["updated_at"] = _now()
        _atomic_json(path, payload)

    if rebuild_if_stale:
        try:
            shots = load_shot_breakdown(project)
            scripts = load_script_package(project)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            payload["status"] = "BLOCKED_UPSTREAM"
            payload["blockers"] = [str(error)]
            payload["diagnostics"] = diagnostics(project)
            return payload
        if (
            int(payload.get("shot_breakdown_revision") or 0) != int(shots["revision"])
            or int(payload.get("script_revision") or 0) != int(scripts["revision"])
            or str(payload.get("voice_timing_signature") or "") != _voice_timing_signature(project)
        ):
            return save_plan(project)
    return payload


def approve_h3_escalation(project: Path, shot_id: str, reason: str) -> dict[str, Any]:
    project = Path(project).resolve()
    shot_id = str(shot_id or "").strip()
    reason = str(reason or "").strip()
    if not shot_id:
        raise CostFirstRoutingError("shot_id is required")
    if len(reason) < 6:
        raise CostFirstRoutingError("H3 escalation requires a concrete reason")
    plan = load_plan(project)
    route = next((item for item in plan["routes"] if item["shot_id"] == shot_id), None)
    if route is None:
        raise CostFirstRoutingError("unknown shot_id")
    if route["route"] != "H3_CANDIDATE":
        raise CostFirstRoutingError("this shot does not require H3 escalation")
    route["h3_escalation"] = {
        "status": "APPROVED",
        "approved": True,
        "reason": reason,
        "approved_at": _now(),
    }
    plan["updated_at"] = _now()
    _atomic_json(project / OUTPUT, plan)
    return plan


def block_h3(project: Path, shot_id: str) -> dict[str, Any]:
    project = Path(project).resolve()
    plan = load_plan(project)
    route = next((item for item in plan["routes"] if item["shot_id"] == str(shot_id)), None)
    if route is None:
        raise CostFirstRoutingError("unknown shot_id")
    route["h3_escalation"] = {
        "status": "REQUIRES_MANUAL_APPROVAL" if route["route"] == "H3_CANDIDATE" else "NOT_NEEDED",
        "approved": False,
        "reason": "",
        "approved_at": "",
    }
    plan["updated_at"] = _now()
    _atomic_json(project / OUTPUT, plan)
    return plan


def require_h3_approval(project: Path, shot_id: str) -> dict[str, Any]:
    project = Path(project).resolve()
    shot_id = str(shot_id or "").strip()
    if not shot_id:
        raise CostFirstRoutingError("P36 H3 requires an explicit shot_id")
    plan = load_plan(project)
    route = next((item for item in plan.get("routes", []) if item.get("shot_id") == shot_id), None)
    if route is None:
        raise CostFirstRoutingError("P36 H3 shot is not present in the current routing plan")
    if route.get("route") != "H3_CANDIDATE":
        raise CostFirstRoutingError("P36 blocks H3 because this shot has a local route")
    escalation = route.get("h3_escalation") if isinstance(route.get("h3_escalation"), dict) else {}
    reason = str(escalation.get("reason") or "").strip()
    if escalation.get("approved") is not True or str(escalation.get("status") or "") != "APPROVED" or len(reason) < 6:
        raise CostFirstRoutingError("P36 H3 is locked; approve the H3 candidate with a concrete reason first")
    return route


__all__ = [
    "CostFirstRoutingError",
    "OUTPUT",
    "approve_h3_escalation",
    "block_h3",
    "build_plan",
    "diagnostics",
    "load_plan",
    "require_h3_approval",
    "save_plan",
]
