#!/usr/bin/env python3
"""Audit causality, pacing, motivation, foreshadowing, and cross-episode continuity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import utc_timestamp  # noqa: E402
from scripts.novel_episode_planning import load_episode_planning, readiness as episode_planning_readiness  # noqa: E402
from scripts.novel_episode_script import load_script_package, preview_continuity_snapshot  # noqa: E402
from scripts.novel_series_plan import load_plan, readiness as series_plan_readiness  # noqa: E402
from scripts.novel_story_bible import load_bible  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-story-review.schema.json"
REPORT_PATH = Path("writing-room/story-review.json")
CATEGORIES = ("causality", "pacing", "motivation", "foreshadowing", "continuity", "provenance")


class NovelStoryReviewError(ValueError):
    """Raised when a story review cannot be generated or approved."""


def _finding(category: str, severity: str, code: str, message: str, *refs: str) -> dict[str, Any]:
    return {"category": category, "severity": severity, "code": code, "message": message, "entity_refs": list(dict.fromkeys(refs)), "status": "OPEN", "resolution": ""}


def _open(findings: list[dict[str, Any]], *, category: str | None = None) -> list[dict[str, Any]]:
    return [item for item in findings if item["status"] == "OPEN" and (category is None or item["category"] == category)]


def audit_story(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    bible = load_bible(project_dir)
    series = load_plan(project_dir)
    planning = load_episode_planning(project_dir)
    package = load_script_package(project_dir)
    findings: list[dict[str, Any]] = []
    if not series_plan_readiness(project_dir)["ready"]:
        findings.append(_finding("causality", "BLOCKER", "SERIES_PLAN_BLOCKED", "全剧、季度或角色弧规划尚未就绪。", series["series_plan"]["id"]))
    if not episode_planning_readiness(project_dir)["ready"]:
        findings.append(_finding("causality", "BLOCKER", "EPISODE_PLANNING_BLOCKED", "故事弧或单集卡尚未就绪。", *[item["id"] for item in planning["episode_cards"]]))
    snapshots = {item["id"] for item in bible["continuity_ledger"]["snapshots"]}
    cards = {item["episode_id"]: item for item in planning["episode_cards"]}
    deltas = {item["episode_id"]: item for item in package["continuity_deltas"]}
    for script in package["episode_scripts"]:
        episode_id = script["episode_id"]
        card = cards[episode_id]
        delta = deltas[episode_id]
        if card["status"] != "READY":
            findings.append(_finding("causality", "BLOCKER", "CARD_NOT_READY", f"{episode_id} 单集卡未就绪。", card["id"]))
        if script["status"] != "READY":
            findings.append(_finding("causality", "BLOCKER", "SCRIPT_NOT_READY", f"{episode_id} 场景剧本未就绪。", script["id"]))
        if delta["status"] != "READY":
            findings.append(_finding("continuity", "BLOCKER", "DELTA_NOT_READY", f"{episode_id} continuity delta 未就绪。", delta["id"]))
        if script["input_snapshot_id"] not in snapshots:
            findings.append(_finding("continuity", "BLOCKER", "CONTINUITY_INPUT_MISSING", f"{episode_id} 缺少前一集结束状态 {script['input_snapshot_id']}。", script["id"], script["input_snapshot_id"]))
        if card["status"] == "READY":
            chain = [card["goal"], card["obstacle"], card["turn"], card["climax"], card["ending_hook"]]
            if any(not value.strip() for value in chain):
                findings.append(_finding("causality", "BLOCKER", "CAUSAL_CHAIN_INCOMPLETE", f"{episode_id} 缺少目标—阻碍—转折—高潮—钩子因果链。", card["id"]))
        estimated = sum(unit["estimated_duration_seconds"] for scene in script["scenes"] for unit in scene["units"])
        if script["status"] == "READY" and estimated < script["target_duration_seconds"] * 0.45:
            findings.append(_finding("pacing", "WARNING", "PACING_UNDERRUN", f"{episode_id} 表演单元仅覆盖约 {estimated:.1f} 秒，低于目标时长的 45%。", script["id"]))
        if script["status"] == "READY" and len(script["scenes"]) > 12:
            findings.append(_finding("pacing", "WARNING", "SCENE_DENSITY_HIGH", f"{episode_id} 在短篇时长内包含超过 12 场。", script["id"]))
        scripted_characters = {character_id for scene in script["scenes"] for character_id in scene["character_ids"]}
        missing_characters = set(card["character_ids"]) - scripted_characters
        if card["status"] == "READY" and missing_characters:
            findings.append(_finding("motivation", "BLOCKER", "PLANNED_CHARACTER_ABSENT", f"{episode_id} 单集卡人物未出现在剧本场景：{', '.join(sorted(missing_characters))}。", card["id"], script["id"]))
        opened = set(delta["open_foreshadowing_ids"])
        closed = set(delta["close_foreshadowing_ids"])
        if set(card["foreshadowing_setup_ids"]) - opened:
            findings.append(_finding("foreshadowing", "BLOCKER", "FORESHADOW_SETUP_NOT_RECORDED", f"{episode_id} 计划设置的伏笔未写入 continuity delta。", card["id"], delta["id"]))
        if set(card["foreshadowing_payoff_ids"]) - closed:
            findings.append(_finding("foreshadowing", "BLOCKER", "FORESHADOW_PAYOFF_NOT_RECORDED", f"{episode_id} 计划回收的伏笔未在 continuity delta 关闭。", card["id"], delta["id"]))
        if script["status"] == "READY" and delta["status"] == "READY" and delta["input_snapshot_id"] in snapshots:
            try:
                preview_continuity_snapshot(project_dir, episode_id)
            except ValueError as error:
                findings.append(_finding("continuity", "BLOCKER", "DELTA_APPLICATION_FAILED", f"{episode_id} 状态增量无法应用：{error}", delta["id"]))
        for scene in script["scenes"]:
            if scene["provenance"]["kind"] == "UNSET" or any(unit["provenance"]["kind"] == "UNSET" for unit in scene["units"]):
                findings.append(_finding("provenance", "BLOCKER", "SCRIPT_PROVENANCE_MISSING", f"{scene['id']} 存在未标明来源或原创性质的内容。", scene["id"]))
    for index, finding in enumerate(findings, start=1):
        finding["id"] = f"FIND-{index:04d}"
    category_status = {}
    for category in CATEGORIES:
        items = _open(findings, category=category)
        category_status[category] = "BLOCKED" if any(item["severity"] == "BLOCKER" for item in items) else ("REVIEW_REQUIRED" if items else "PASS")
    overall = "BLOCKED" if any(value == "BLOCKED" for value in category_status.values()) else ("REVIEW_REQUIRED" if any(value == "REVIEW_REQUIRED" for value in category_status.values()) else "PASS")
    return validate_report({
        "schema_version": 1, "project_id": series["project_id"],
        "input_revisions": {"story_bible": bible["revision"], "series_plan": series["revision"], "episode_planning": planning["revision"], "script_package": package["revision"]},
        "generated_at": utc_timestamp(), "overall_status": overall, "category_status": category_status, "findings": findings,
        "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""},
    })


def validate_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelStoryReviewError("story review report must be an object")
    try:
        import jsonschema
    except ImportError:
        return payload
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "report"
        raise NovelStoryReviewError(f"story review schema violation at {path}: {errors[0].message}")
    return payload


def write_report(project_dir: Path, report: dict[str, Any], *, overwrite: bool = True) -> Path:
    report = validate_report(report)
    output = Path(project_dir).expanduser().resolve() / REPORT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise NovelStoryReviewError(f"refusing to overwrite review report: {output}")
    descriptor, temporary = tempfile.mkstemp(prefix=".story-review.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, output)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return output


def load_report(project_dir: Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve() / REPORT_PATH
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: raise NovelStoryReviewError(f"cannot read story review: {error}") from error
    return validate_report(payload)


def approve_report(project_dir: Path, reviewer: str, note: str) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer: raise NovelStoryReviewError("reviewer must not be empty")
    report = load_report(project_dir)
    try:
        current = audit_story(project_dir)
    except ValueError as error:
        raise NovelStoryReviewError(f"story review is stale or current inputs are invalid: {error}") from error
    if report["input_revisions"] != current["input_revisions"]:
        raise NovelStoryReviewError("story review is stale")
    if report["overall_status"] != "PASS" or _open(report["findings"]):
        raise NovelStoryReviewError("only a PASS report with no open findings can be approved")
    report["human_review"] = {"required": True, "status": "APPROVED", "reviewed_at": utc_timestamp(), "reviewed_by": reviewer, "note": note.strip()}
    write_report(project_dir, report)
    return report["human_review"]


def summary(project_dir: Path) -> dict[str, Any] | None:
    try: report = load_report(project_dir)
    except NovelStoryReviewError: return None
    return {"overall_status": report["overall_status"], "finding_count": len(report["findings"]), "blocker_count": sum(1 for item in _open(report["findings"]) if item["severity"] == "BLOCKER"), "warning_count": sum(1 for item in _open(report["findings"]) if item["severity"] == "WARNING"), "human_review_status": report["human_review"]["status"], "category_status": report["category_status"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "validate", "approve"))
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    try:
        if args.command == "audit":
            report = audit_story(args.project_dir); output = write_report(args.project_dir, report); result: Any = {"output": output.relative_to(Path(args.project_dir).resolve()).as_posix(), **summary(args.project_dir)}
        elif args.command == "validate": result = summary(args.project_dir)
        else: result = approve_report(args.project_dir, args.reviewer, args.note)
    except (NovelStoryReviewError, OSError, ValueError) as error:
        print(f"novel_story_review: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
