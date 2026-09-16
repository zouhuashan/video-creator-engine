#!/usr/bin/env python3
"""Build the six-gate QC report for a novel animation project."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp  # noqa: E402
from scripts.novel_animatic_review import load_review as load_animatic_review  # noqa: E402
from scripts.novel_asset_review import load_asset_review  # noqa: E402
from scripts.novel_audio_mix import load_audio_mix  # noqa: E402
from scripts.novel_dynamic_shots import load_dynamic_shots  # noqa: E402
from scripts.novel_edit_timelines import load_edit_timelines  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402
from scripts.novel_story_review import load_report as load_story_review  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-qc-report.schema.json"
OUTPUT = Path("qc/qc-report.json")
HISTORY_DIR = Path("qc/history")
CATEGORIES = ("RIGHTS", "STORY", "CONTINUITY", "CHARACTER_AV", "TECHNICAL", "PUBLISH")


class NovelQCError(ValueError):
    """Raised when a QC report or review annotation is invalid."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _finding(category: str, severity: str, code: str, message: str, *refs: str) -> dict[str, Any]:
    return {"category": category, "severity": severity, "code": code, "message": message, "entity_refs": list(dict.fromkeys(refs)), "status": "OPEN", "resolution": ""}


def _inputs(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    catalog = load_catalog(Path(project_dir) / CATALOG_RELATIVE_PATH)
    story = load_story_review(project_dir)
    animatic = load_animatic_review(project_dir)
    assets = load_asset_review(project_dir)
    audio = load_audio_mix(project_dir)
    dynamic = load_dynamic_shots(project_dir)
    edit = load_edit_timelines(project_dir)
    return {"project": project, "catalog": catalog, "story": story, "animatic": animatic, "assets": assets, "audio": audio, "dynamic": dynamic, "edit": edit}


def _story_revision(story: dict[str, Any]) -> int:
    return max(story["input_revisions"].values(), default=1)


def _input_revisions(data: dict[str, Any]) -> dict[str, int]:
    return {
        "source_catalog": data["catalog"]["revision"],
        "story_review": _story_revision(data["story"]),
        "animatic_review": data["animatic"]["revision"],
        "asset_review": data["assets"]["revision"],
        "audio_mix": data["audio"]["revision"],
        "dynamic_shots": data["dynamic"]["revision"],
        "edit_timelines": data["edit"]["revision"],
    }


def _open_blockers(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in findings if item["status"] == "OPEN" and item["severity"] == "BLOCKER"]


def _status(findings: list[dict[str, Any]]) -> str:
    open_items = [item for item in findings if item["status"] == "OPEN"]
    if any(item["severity"] == "BLOCKER" for item in open_items):
        return "BLOCKED"
    if open_items:
        return "REVIEW_REQUIRED"
    return "PASS"


def _build_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    catalog, story, animatic = data["catalog"], data["story"], data["animatic"]
    assets, audio, dynamic, edit = data["assets"], data["audio"], data["dynamic"], data["edit"]
    findings: list[dict[str, Any]] = []
    rights = catalog["rights_assessment"]
    if rights["status"] not in {"PUBLIC_DOMAIN_VERIFIED", "LICENSED"}:
        findings.append(_finding("RIGHTS", "BLOCKER", "SOURCE_RIGHTS_UNCLEARED", f"底本权利状态为 {rights['status']}，不能进入正式改编。", catalog["ip_id"]))
    if not rights["evidence"]:
        findings.append(_finding("RIGHTS", "BLOCKER", "RIGHTS_EVIDENCE_MISSING", "底本缺少可核验的权利证据。", catalog["ip_id"]))
    if catalog["adaptation_policy"]["script_adaptation_allowed"] is not True:
        findings.append(_finding("RIGHTS", "BLOCKER", "ADAPTATION_NOT_ALLOWED", "来源目录尚未允许剧本改编。", catalog["ip_id"]))
    if rights["human_review"]["status"] != "APPROVED":
        findings.append(_finding("RIGHTS", "BLOCKER", "RIGHTS_REVIEW_PENDING", "来源权利人工审核尚未批准。", catalog["ip_id"]))

    if story["overall_status"] == "BLOCKED":
        refs = [item["id"] for item in story["findings"] if item["status"] == "OPEN" and item["severity"] == "BLOCKER"]
        findings.append(_finding("STORY", "BLOCKER", "STORY_REVIEW_BLOCKED", "剧情审核存在未解决阻断项。", *refs))
    if story["human_review"]["status"] != "APPROVED":
        findings.append(_finding("STORY", "BLOCKER", "STORY_REVIEW_PENDING", "剧情审核尚未完成人工确认。", "story-review"))

    if story["category_status"].get("continuity") == "BLOCKED":
        findings.append(_finding("CONTINUITY", "BLOCKER", "STORY_CONTINUITY_BLOCKED", "剧情连续性账本或跨集状态存在阻断项。", "story-review"))
    continuity_findings = [item for item in animatic["findings"] if item["category"] in {"CHARACTER_CONTINUITY", "ENVIRONMENT_CONTINUITY", "PROP_CONTINUITY"} and item["status"] == "OPEN"]
    if continuity_findings:
        findings.append(_finding("CONTINUITY", "BLOCKER", "ANIMATIC_CONTINUITY_BLOCKED", f"Animatic 连续性审核有 {len(continuity_findings)} 个未解决问题。", *[item["entity_id"] for item in continuity_findings]))

    if not assets["reference_packages"] or any(item["human_review"]["status"] != "APPROVED" for item in assets["reference_packages"]):
        findings.append(_finding("CHARACTER_AV", "BLOCKER", "ASSET_REVIEW_PENDING", "角色、场景或道具参考包尚未完成美术审核。", "asset-review"))
    if animatic["overall_status"] == "BLOCKED":
        findings.append(_finding("CHARACTER_AV", "BLOCKER", "ANIMATIC_REVIEW_BLOCKED", "Animatic 视听审核存在未解决阻断项。", "animatic-review"))
    if any(item["status"] != "APPROVED" for item in dynamic["reviews"]):
        findings.append(_finding("CHARACTER_AV", "BLOCKER", "DYNAMIC_SHOT_REVIEW_PENDING", "动态镜头存在未批准的角色一致性或动作审核。", "dynamic-shots"))

    episode_count = len(edit["episodes"])
    ready_edits = sum(1 for item in edit["episodes"] if item["status"] == "READY")
    ready_mixes = sum(1 for item in audio["episodes"] if item["status"] == "READY")
    if ready_edits < episode_count:
        findings.append(_finding("TECHNICAL", "BLOCKER", "EDIT_OUTPUT_NOT_READY", f"剪辑时间线仅 {ready_edits}/{episode_count} 集 READY。", "edit-timelines"))
    if ready_mixes < len(audio["episodes"]):
        findings.append(_finding("TECHNICAL", "BLOCKER", "AUDIO_MIX_NOT_READY", f"混音计划仅 {ready_mixes}/{len(audio['episodes'])} 集 READY。", "audio-mix"))
    if any(job["status"] in {"FAILED", "CANCELLED"} for job in dynamic["jobs"]):
        findings.append(_finding("TECHNICAL", "BLOCKER", "DYNAMIC_JOB_FAILED", "动态镜头队列存在失败或取消任务。", "dynamic-shots"))

    if rights["publication_allowed"] is not True or catalog["adaptation_policy"]["publication_allowed"] is not True:
        findings.append(_finding("PUBLISH", "BLOCKER", "PUBLICATION_BLOCKED", "来源目录禁止正式发布。", catalog["ip_id"]))
    return findings


def build_qc_report(project_dir: Path) -> dict[str, Any]:
    data = _inputs(Path(project_dir).resolve())
    project = data["project"]
    now = utc_timestamp()
    findings = _build_findings(data)
    for index, item in enumerate(findings, start=1):
        item["id"] = f"QCF-{index:04d}"
    statuses: dict[str, str] = {}
    for category in CATEGORIES:
        statuses[category] = _status([item for item in findings if item["category"] == category])
    overall = _status(findings)
    return validate_qc_report(Path(project_dir), {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "revision": 1, "created_at": now, "updated_at": now, "input_revisions": _input_revisions(data), "overall_status": overall, "category_status": statuses, "findings": findings, "annotations": [], "issues": [], "human_review": _review()})


def _schema(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        raise NovelQCError(f"qc report schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")


def validate_qc_report(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelQCError("qc report must be an object")
    report = deepcopy(payload)
    _schema(report)
    data = _inputs(Path(project_dir).resolve())
    project = data["project"]
    if report["project_id"] != project["project_id"] or report["ip_id"] != project["ip"]["id"]:
        raise NovelQCError("qc report does not match project")
    if report["input_revisions"] != _input_revisions(data):
        raise NovelQCError("qc report upstream revisions are stale")
    finding_ids: set[str] = set()
    for item in report["findings"]:
        if item["id"] in finding_ids:
            raise NovelQCError(f"duplicate finding {item['id']}")
        finding_ids.add(item["id"])
    expected = {category: _status([item for item in report["findings"] if item["category"] == category]) for category in CATEGORIES}
    if report["category_status"] != expected or report["overall_status"] != _status(report["findings"]):
        raise NovelQCError("qc report status does not match findings")
    annotation_ids = {item["id"] for item in report["annotations"]}
    if len(annotation_ids) != len(report["annotations"]):
        raise NovelQCError("duplicate annotation")
    issue_ids = {item["id"] for item in report["issues"]}
    if len(issue_ids) != len(report["issues"]):
        raise NovelQCError("duplicate issue")
    if any(item["finding_id"] and item["finding_id"] not in finding_ids for item in report["annotations"] + report["issues"]):
        raise NovelQCError("annotation or issue references unknown finding")
    return report


def write_qc_report(project_dir: Path, report: dict[str, Any], overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).resolve()
    report = validate_qc_report(project_dir, report)
    path = project_dir / OUTPUT
    if path.exists() and not overwrite:
        raise NovelQCError(f"refusing to overwrite qc report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and overwrite:
        previous = json.loads(path.read_text(encoding="utf-8"))
        history = project_dir / HISTORY_DIR
        history.mkdir(parents=True, exist_ok=True)
        (history / f"qc-r{previous.get('revision', 0)}.json").write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".qc-report.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return path


def load_qc_report(project_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelQCError(f"cannot read qc report: {error}") from error
    return validate_qc_report(Path(project_dir), payload)


def _next_id(items: list[dict[str, Any]], prefix: str) -> str:
    numbers = [int(item["id"].split("-")[-1]) for item in items if re.fullmatch(rf"{prefix}-\d{{4}}", item["id"])]
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"


def add_annotation(project_dir: Path, target_id: str, note: str, author: str, finding_id: str | None = None) -> dict[str, Any]:
    report = load_qc_report(project_dir)
    annotation = {"id": _next_id(report["annotations"], "QCA"), "target_id": target_id.strip(), "finding_id": finding_id, "note": note.strip(), "author": author.strip(), "created_at": utc_timestamp()}
    if not annotation["target_id"] or not annotation["note"] or not annotation["author"]:
        raise NovelQCError("annotation target_id, note and author are required")
    report["annotations"].append(annotation)
    report["revision"] += 1
    report["updated_at"] = utc_timestamp()
    write_qc_report(project_dir, report, overwrite=True)
    return report


def add_issue(project_dir: Path, title: str, target_refs: list[str], finding_id: str | None = None) -> dict[str, Any]:
    report = load_qc_report(project_dir)
    if not title.strip() or not target_refs:
        raise NovelQCError("issue title and target_refs are required")
    issue = {"id": _next_id(report["issues"], "QCI"), "title": title.strip(), "finding_id": finding_id, "status": "OPEN", "target_refs": list(dict.fromkeys(target_refs)), "rerender_job_ids": [], "notes": [], "created_at": utc_timestamp(), "updated_at": utc_timestamp()}
    report["issues"].append(issue)
    report["revision"] += 1
    report["updated_at"] = utc_timestamp()
    write_qc_report(project_dir, report, overwrite=True)
    return report


def update_issue(project_dir: Path, issue_id: str, status: str, *, note: str | None = None, rerender_job_ids: list[str] | None = None) -> dict[str, Any]:
    report = load_qc_report(project_dir)
    issue = next((item for item in report["issues"] if item["id"] == issue_id), None)
    if issue is None or status not in {"OPEN", "IN_PROGRESS", "RESOLVED"}:
        raise NovelQCError("unknown issue or invalid status")
    issue["status"] = status
    if note:
        issue["notes"].append(note.strip())
    if rerender_job_ids is not None:
        issue["rerender_job_ids"] = list(dict.fromkeys(rerender_job_ids))
    issue["updated_at"] = utc_timestamp()
    report["revision"] += 1
    report["updated_at"] = utc_timestamp()
    write_qc_report(project_dir, report, overwrite=True)
    return report


def compare(project_dir: Path, baseline_revision: int | None = None) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    current = load_qc_report(project_dir)
    baseline = None
    if baseline_revision is not None:
        candidate = project_dir / HISTORY_DIR / f"qc-r{baseline_revision}.json"
        if candidate.is_file():
            baseline = json.loads(candidate.read_text(encoding="utf-8"))
    else:
        history = sorted((project_dir / HISTORY_DIR).glob("qc-r*.json")) if (project_dir / HISTORY_DIR).is_dir() else []
        if history:
            baseline = json.loads(history[-1].read_text(encoding="utf-8"))
    if baseline is None:
        return {"current_revision": current["revision"], "baseline_revision": None, "changed_categories": [], "added_finding_ids": [], "resolved_finding_ids": []}
    current_ids = {item["id"] for item in current["findings"] if item["status"] == "OPEN"}
    baseline_ids = {item["id"] for item in baseline.get("findings", []) if item["status"] == "OPEN"}
    changed = [category for category in CATEGORIES if current["category_status"][category] != baseline.get("category_status", {}).get(category)]
    return {"current_revision": current["revision"], "baseline_revision": baseline.get("revision"), "changed_categories": changed, "added_finding_ids": sorted(current_ids - baseline_ids), "resolved_finding_ids": sorted(baseline_ids - current_ids)}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        report = load_qc_report(project_dir)
    except (NovelQCError, ValueError):
        return None
    return {"revision": report["revision"], "overall_status": report["overall_status"], "category_status": report["category_status"], "finding_count": len(report["findings"]), "open_blocker_count": len(_open_blockers(report["findings"])), "annotation_count": len(report["annotations"]), "open_issue_count": sum(1 for item in report["issues"] if item["status"] != "RESOLVED"), "human_review_status": report["human_review"]["status"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "validate"))
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    try:
        result = {"output": write_qc_report(args.project_dir, build_qc_report(args.project_dir)).relative_to(Path(args.project_dir).resolve()).as_posix()} if args.command == "audit" else summary(args.project_dir)
    except (NovelQCError, OSError, ValueError) as error:
        print(f"novel_qc: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
