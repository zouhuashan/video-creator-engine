#!/usr/bin/env python3
"""Run the formal five-episode acceptance gate for the Jinghua Yuan series."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp  # noqa: E402
from scripts.novel_animatic import load_animatic  # noqa: E402
from scripts.novel_animatic_review import load_review as load_animatic_review  # noqa: E402
from scripts.novel_asset_review import load_asset_review, summary as asset_summary  # noqa: E402
from scripts.novel_audio_mix import load_audio_mix  # noqa: E402
from scripts.novel_dynamic_shots import load_dynamic_shots  # noqa: E402
from scripts.novel_edit_timelines import load_edit_timelines  # noqa: E402
from scripts.novel_qc import load_qc_report  # noqa: E402
from scripts.novel_story_review import load_report as load_story_review  # noqa: E402
from scripts.novel_episode_script import load_script_package  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-acceptance-report.schema.json"
OUTPUT = Path("acceptance/acceptance-report.json")


class NovelAcceptanceError(ValueError):
    """Raised when an acceptance report is invalid or stale."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _inputs(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    return {
        "project": project,
        "scripts": load_script_package(project_dir),
        "story_review": load_story_review(project_dir),
        "animatic": load_animatic(project_dir),
        "animatic_review": load_animatic_review(project_dir),
        "assets": load_asset_review(project_dir),
        "audio": load_audio_mix(project_dir),
        "dynamic": load_dynamic_shots(project_dir),
        "edit": load_edit_timelines(project_dir),
        "qc": load_qc_report(project_dir),
    }


def _input_revisions(data: dict[str, Any]) -> dict[str, int]:
    return {
        "project": data["project"]["revision"],
        "story_review": max(data["story_review"]["input_revisions"].values(), default=1),
        "asset_review": data["assets"]["revision"],
        "animatic": data["animatic"]["revision"],
        "audio_mix": data["audio"]["revision"],
        "dynamic_shots": data["dynamic"]["revision"],
        "edit_timelines": data["edit"]["revision"],
        "qc": data["qc"]["revision"],
    }


def _status(*values: str) -> str:
    return "READY" if values and all(value in {"READY", "PASS", "APPROVED"} for value in values) else "BLOCKED"


def _build_episode_rows(project_dir: Path, data: dict[str, Any]) -> list[dict[str, Any]]:
    scripts = {item["episode_id"]: item for item in data["scripts"]["episode_scripts"]}
    deltas = {item["episode_id"]: item for item in data["scripts"]["continuity_deltas"]}
    animatic = {item["episode_id"]: item for item in data["animatic"]["episodes"]}
    audio = {item["episode_id"]: item for item in data["audio"]["episodes"]}
    edit = {item["episode_id"]: item for item in data["edit"]["episodes"]}
    asset_state = asset_summary(project_dir)
    visual_ready = asset_state is not None and asset_state["ready"]
    voice_ready = bool(data["audio"].get("episodes")) and any(item["dialogue_line_ids"] for item in data["audio"]["episodes"])
    rows = []
    for episode in data["project"]["episodes"]:
        episode_id = episode["id"]
        script_status = scripts[episode_id]["status"]
        continuity_status = deltas[episode_id]["status"]
        animatic_status = animatic[episode_id]["status"]
        subtitle_status = animatic[episode_id]["subtitle_track"]["status"]
        audio_status = audio[episode_id]["status"]
        edit_status = edit[episode_id]["status"]
        row = {"episode_id": episode_id, "script_status": script_status, "continuity_status": continuity_status, "visual_status": "READY" if visual_ready else "BLOCKED", "voice_status": "READY" if voice_ready else "BLOCKED", "subtitle_status": subtitle_status, "animatic_status": animatic_status, "audio_status": audio_status, "edit_status": edit_status, "overall_status": _status(script_status, continuity_status, "READY" if visual_ready else "BLOCKED", "READY" if voice_ready else "BLOCKED", subtitle_status, animatic_status, audio_status, edit_status)}
        rows.append(row)
    return rows


def _legacy_reference(project_dir: Path) -> dict[str, Any]:
    migrations = []
    for path in sorted((Path(project_dir) / ".videocreator" / "migrations").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        migrations.append(payload)
    assets = sum(len(item.get("assets", [])) for item in migrations)
    publication_allowed = any(item.get("publication_allowed") is True for item in migrations)
    return {"migration_count": len(migrations), "reference_only": not publication_allowed, "publication_allowed": publication_allowed, "asset_count": assets}


def build_acceptance(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve(); data = _inputs(project_dir); project = data["project"]
    episode_rows = _build_episode_rows(project_dir, data)
    episode_id = episode_rows[0]["episode_id"] if episode_rows else "S01E001"
    motion_tests = [{"id": f"MOTIONTEST-{index:03d}", "episode_id": episode_id, "shot_id": None, "provider": "runway", "status": "NOT_RUN", "cost_usd": None, "duration_seconds": None, "consistency_status": "NOT_ASSESSED", "note": "待选定正式镜头、确认上传授权和人工批准后运行。"} for index in range(1, 4)]
    qc = {"overall_status": data["qc"]["overall_status"], "open_blocker_count": sum(1 for item in data["qc"]["findings"] if item["status"] == "OPEN" and item["severity"] == "BLOCKER"), "human_review_status": data["qc"]["human_review"]["status"]}
    now = utc_timestamp()
    report = {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "revision": 1, "created_at": now, "updated_at": now, "input_revisions": _input_revisions(data), "legacy_reference": _legacy_reference(project_dir), "episodes": episode_rows, "motion_tests": motion_tests, "qc": qc, "decision": "HOLD", "human_review": _review()}
    return validate_acceptance(project_dir, report)


def _schema(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        raise NovelAcceptanceError(f"acceptance schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")


def validate_acceptance(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelAcceptanceError("acceptance report must be an object")
    report = deepcopy(payload); _schema(report); data = _inputs(Path(project_dir).resolve()); project = data["project"]
    if report["project_id"] != project["project_id"] or report["ip_id"] != project["ip"]["id"]:
        raise NovelAcceptanceError("acceptance report does not match project")
    if report["input_revisions"] != _input_revisions(data):
        raise NovelAcceptanceError("acceptance report upstream revisions are stale")
    episode_ids = [item["id"] for item in project["episodes"]]
    if len(episode_ids) != 5 or [item["episode_id"] for item in report["episodes"]] != episode_ids:
        raise NovelAcceptanceError("acceptance must cover the project's five episodes in order")
    if report["legacy_reference"]["publication_allowed"] is not False or report["legacy_reference"]["reference_only"] is not True:
        raise NovelAcceptanceError("legacy pilot assets must remain reference-only")
    if len({item["id"] for item in report["motion_tests"]}) != 3 or any(item["episode_id"] not in episode_ids for item in report["motion_tests"]):
        raise NovelAcceptanceError("acceptance requires three valid motion test slots")
    if report["decision"] in {"ACCEPT", "EXPAND"}:
        if any(item["overall_status"] != "READY" for item in report["episodes"]) or report["qc"]["overall_status"] != "PASS" or report["qc"]["open_blocker_count"] or report["qc"]["human_review_status"] != "APPROVED" or any(item["status"] != "SUCCEEDED" for item in report["motion_tests"]):
            raise NovelAcceptanceError("acceptance decision cannot pass before all gates and motion tests are complete")
    return report


def write_acceptance(project_dir: Path, report: dict[str, Any], overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).resolve(); report = validate_acceptance(project_dir, report); path = project_dir / OUTPUT
    if path.exists() and not overwrite:
        raise NovelAcceptanceError(f"refusing to overwrite acceptance report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".acceptance-report.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path


def load_acceptance(project_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelAcceptanceError(f"cannot read acceptance report: {error}") from error
    return validate_acceptance(project_dir, payload)


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        report = load_acceptance(project_dir)
    except (NovelAcceptanceError, ValueError):
        return None
    return {"revision": report["revision"], "decision": report["decision"], "episode_count": len(report["episodes"]), "ready_episode_count": sum(1 for item in report["episodes"] if item["overall_status"] == "READY"), "motion_test_count": len(report["motion_tests"]), "motion_tests_run": sum(1 for item in report["motion_tests"] if item["status"] != "NOT_RUN"), "qc_status": report["qc"]["overall_status"], "open_blocker_count": report["qc"]["open_blocker_count"], "human_review_status": report["human_review"]["status"]}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("audit", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_acceptance(args.project_dir, build_acceptance(args.project_dir)).relative_to(Path(args.project_dir).resolve()).as_posix()} if args.command == "audit" else summary(args.project_dir)
    except (NovelAcceptanceError, OSError, ValueError) as error:
        print(f"novel_acceptance: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
