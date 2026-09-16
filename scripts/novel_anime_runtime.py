#!/usr/bin/env python3
"""Persistent jobs, review gates, recovery, reruns, and legacy migration for P18."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import NovelAnimeProjectError, load_project, utc_timestamp  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository, NovelAnimeRepositoryError  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, NovelSourceCatalogError, load_catalog  # noqa: E402
from scripts.novel_story_bible import NovelStoryBibleError, readiness as story_bible_readiness  # noqa: E402
from scripts.novel_story_review import NovelStoryReviewError, audit_story, load_report as load_story_review  # noqa: E402


RUNTIME_SCHEMA_VERSION = 1
JOB_STATUSES = {"QUEUED", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "FAILED", "CANCELED"}
REVIEW_STATUSES = {"PENDING", "APPROVED", "CHANGES_REQUESTED"}
STATE_SEQUENCE = (
    "DRAFT", "SOURCE_READY", "BIBLE_READY", "WRITING_READY", "STORYBOARD_READY",
    "ASSETS_READY", "AUDIO_READY", "ANIMATIC_READY", "MOTION_READY", "EDIT_READY",
    "QC_READY", "HUMAN_APPROVED", "PACKAGED",
)
REQUIRED_GATE = {
    "SOURCE_READY": "source_rights",
    "BIBLE_READY": "story_bible",
    "WRITING_READY": "season_plan",
    "STORYBOARD_READY": "script_storyboard",
    "ASSETS_READY": "visual_assets",
    "AUDIO_READY": "audio",
    "ANIMATIC_READY": "animatic",
    "MOTION_READY": "motion",
    "EDIT_READY": "edit",
    "QC_READY": "qc",
    "HUMAN_APPROVED": "human_release",
    "PACKAGED": "package",
}


class NovelAnimeRuntimeError(RuntimeError):
    """Raised when a queue, lock, state, or migration operation is invalid."""


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _future_timestamp(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NovelAnimeRuntime:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.repository = NovelAnimeRepository(self.project_dir)
        self.db_path = self.repository.db_path

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise NovelAnimeRuntimeError("initialize the novel-anime repository before the runtime")
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> dict[str, int]:
        if not self.db_path.is_file():
            self.repository.initialize()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    job_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    available_at TEXT NOT NULL,
                    locked_by TEXT,
                    locked_at TEXT,
                    error TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_claim_order ON jobs(status, available_at, priority DESC, created_at);
                CREATE TABLE IF NOT EXISTS entity_locks (
                    target_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    worker_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    target_id TEXT NOT NULL,
                    gate TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reviewer TEXT,
                    note TEXT NOT NULL,
                    reviewed_at TEXT,
                    PRIMARY KEY (target_id, gate)
                );
                CREATE TABLE IF NOT EXISTS state_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS migrations (
                    migration_key TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                );
                """
            )
            connection.execute("INSERT OR REPLACE INTO runtime_meta(key, value) VALUES('schema_version', ?)", (str(RUNTIME_SCHEMA_VERSION),))
        return self.stats()

    def _require_initialized(self) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM runtime_meta WHERE key = 'schema_version'").fetchone()
        if row is None or int(row[0]) != RUNTIME_SCHEMA_VERSION:
            raise NovelAnimeRuntimeError("runtime schema is not initialized")

    def _target_exists(self, connection: sqlite3.Connection, target_id: str) -> bool:
        if connection.execute("SELECT 1 FROM entities WHERE entity_id = ?", (target_id,)).fetchone():
            return True
        project_id = connection.execute("SELECT value FROM repository_meta WHERE key = 'project_id'").fetchone()
        return bool(project_id and project_id[0] == target_id)

    def stats(self) -> dict[str, int]:
        self._require_initialized()
        with self._connect() as connection:
            counts = {status.lower(): int(connection.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()[0]) for status in sorted(JOB_STATUSES)}
            counts.update({
                "locks": int(connection.execute("SELECT COUNT(*) FROM entity_locks").fetchone()[0]),
                "reviews": int(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]),
                "transitions": int(connection.execute("SELECT COUNT(*) FROM state_transitions").fetchone()[0]),
                "migrations": int(connection.execute("SELECT COUNT(*) FROM migrations").fetchone()[0]),
            })
        return counts

    def submit_job(self, job_type: str, target_id: str, payload: dict[str, Any] | None = None, *, priority: int = 0, max_attempts: int = 3, idempotency_key: str | None = None) -> dict[str, Any]:
        self._require_initialized()
        job_type = job_type.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", job_type):
            raise NovelAnimeRuntimeError("job_type must be an uppercase identifier")
        if type(priority) is not int or not -100 <= priority <= 100:
            raise NovelAnimeRuntimeError("priority must be an integer from -100 to 100")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise NovelAnimeRuntimeError("max_attempts must be an integer from 1 to 10")
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 200):
            raise NovelAnimeRuntimeError("idempotency_key must be 1 to 200 characters")
        payload = payload or {}
        now = utc_timestamp()
        with self._connect() as connection:
            if not self._target_exists(connection, target_id):
                raise NovelAnimeRuntimeError(f"unknown job target: {target_id}")
            if idempotency_key:
                existing = connection.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if existing:
                    return self._job_dict(existing)
            job_id = f"JOB-{uuid.uuid4().hex[:20].upper()}"
            connection.execute(
                """INSERT INTO jobs(job_id, idempotency_key, job_type, target_id, payload_json, status, priority,
                   attempts, max_attempts, available_at, created_at, updated_at)
                   VALUES(?, ?, ?, ?, ?, 'QUEUED', ?, 0, ?, ?, ?, ?)""",
                (job_id, idempotency_key, job_type, target_id, json.dumps(payload, ensure_ascii=False, sort_keys=True), priority, max_attempts, now, now, now),
            )
            return self._job_dict(connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["result"] = json.loads(result.pop("result_json")) if result.get("result_json") else None
        result.pop("result_json", None)
        return result

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self._require_initialized()
        if not 1 <= limit <= 500:
            raise NovelAnimeRuntimeError("job list limit must be from 1 to 500")
        with self._connect() as connection:
            return [self._job_dict(row) for row in connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def recover_stale(self, *, now: str | None = None) -> list[str]:
        self._require_initialized()
        now = now or utc_timestamp()
        recovered: list[str] = []
        with self._connect() as connection:
            stale = list(connection.execute("SELECT l.job_id, j.attempts, j.max_attempts FROM entity_locks l JOIN jobs j ON j.job_id = l.job_id WHERE l.lease_expires_at <= ?", (now,)))
            for row in stale:
                status = "QUEUED" if int(row[1]) < int(row[2]) else "FAILED"
                error = "worker lease expired; recovered" if status == "QUEUED" else "worker lease expired; retry limit reached"
                connection.execute("UPDATE jobs SET status = ?, locked_by = NULL, locked_at = NULL, error = ?, available_at = ?, updated_at = ? WHERE job_id = ?", (status, error, now, now, row[0]))
                connection.execute("DELETE FROM entity_locks WHERE job_id = ?", (row[0],))
                recovered.append(str(row[0]))
        return recovered

    def claim_job(self, worker_id: str, *, lease_seconds: int = 300) -> dict[str, Any] | None:
        self._require_initialized()
        worker_id = worker_id.strip()
        if not worker_id or len(worker_id) > 100:
            raise NovelAnimeRuntimeError("worker_id must be 1 to 100 characters")
        if not 10 <= lease_seconds <= 3600:
            raise NovelAnimeRuntimeError("lease_seconds must be from 10 to 3600")
        now = utc_timestamp()
        self.recover_stale(now=now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM jobs WHERE status IN ('QUEUED', 'RETRY_WAIT') AND available_at <= ? ORDER BY priority DESC, created_at ASC", (now,)).fetchall()
            selected = None
            for row in rows:
                if connection.execute("SELECT 1 FROM entity_locks WHERE target_id = ?", (row["target_id"],)).fetchone() is None:
                    selected = row
                    break
            if selected is None:
                connection.commit()
                return None
            lease_expires = _future_timestamp(lease_seconds)
            connection.execute("INSERT INTO entity_locks(target_id, job_id, worker_id, acquired_at, lease_expires_at) VALUES(?, ?, ?, ?, ?)", (selected["target_id"], selected["job_id"], worker_id, now, lease_expires))
            connection.execute("UPDATE jobs SET status = 'RUNNING', attempts = attempts + 1, locked_by = ?, locked_at = ?, error = NULL, updated_at = ? WHERE job_id = ?", (worker_id, now, now, selected["job_id"]))
            connection.commit()
            return self._job_dict(connection.execute("SELECT * FROM jobs WHERE job_id = ?", (selected["job_id"],)).fetchone())

    def _running_job(self, connection: sqlite3.Connection, job_id: str, worker_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None or row["status"] != "RUNNING" or row["locked_by"] != worker_id:
            raise NovelAnimeRuntimeError("job is not running for this worker")
        return row

    def complete_job(self, job_id: str, worker_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_initialized()
        now = utc_timestamp()
        with self._connect() as connection:
            self._running_job(connection, job_id, worker_id)
            connection.execute("UPDATE jobs SET status = 'SUCCEEDED', result_json = ?, locked_by = NULL, locked_at = NULL, updated_at = ? WHERE job_id = ?", (json.dumps(result or {}, ensure_ascii=False, sort_keys=True), now, job_id))
            connection.execute("DELETE FROM entity_locks WHERE job_id = ?", (job_id,))
            return self._job_dict(connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())

    def fail_job(self, job_id: str, worker_id: str, error: str, *, retry_delay_seconds: int = 0) -> dict[str, Any]:
        self._require_initialized()
        error = error.strip()
        if not error:
            raise NovelAnimeRuntimeError("job error must not be empty")
        now = utc_timestamp()
        with self._connect() as connection:
            row = self._running_job(connection, job_id, worker_id)
            retry = int(row["attempts"]) < int(row["max_attempts"])
            status = "RETRY_WAIT" if retry else "FAILED"
            available_at = _future_timestamp(max(0, retry_delay_seconds)) if retry else now
            connection.execute("UPDATE jobs SET status = ?, available_at = ?, error = ?, locked_by = NULL, locked_at = NULL, updated_at = ? WHERE job_id = ?", (status, available_at, error[:2000], now, job_id))
            connection.execute("DELETE FROM entity_locks WHERE job_id = ?", (job_id,))
            return self._job_dict(connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        self._require_initialized()
        now = utc_timestamp()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise NovelAnimeRuntimeError("job not found")
            if row["status"] in {"SUCCEEDED", "FAILED", "CANCELED"}:
                return self._job_dict(row)
            connection.execute("UPDATE jobs SET status = 'CANCELED', locked_by = NULL, locked_at = NULL, updated_at = ? WHERE job_id = ?", (now, job_id))
            connection.execute("DELETE FROM entity_locks WHERE job_id = ?", (job_id,))
            return self._job_dict(connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())

    def record_review(self, target_id: str, gate: str, status: str, reviewer: str, note: str = "") -> dict[str, Any]:
        self._require_initialized()
        gate = gate.strip().lower()
        status = status.strip().upper()
        reviewer = reviewer.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,50}", gate):
            raise NovelAnimeRuntimeError("gate must be a lowercase identifier")
        if status not in REVIEW_STATUSES:
            raise NovelAnimeRuntimeError("invalid review status")
        if status != "PENDING" and not reviewer:
            raise NovelAnimeRuntimeError("completed review requires a reviewer")
        reviewed_at = utc_timestamp() if status != "PENDING" else None
        with self._connect() as connection:
            if not self._target_exists(connection, target_id):
                raise NovelAnimeRuntimeError("review target is unknown")
            connection.execute("INSERT INTO reviews(target_id, gate, status, reviewer, note, reviewed_at) VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(target_id, gate) DO UPDATE SET status=excluded.status, reviewer=excluded.reviewer, note=excluded.note, reviewed_at=excluded.reviewed_at", (target_id, gate, status, reviewer or None, note.strip(), reviewed_at))
        return {"target_id": target_id, "gate": gate, "status": status, "reviewer": reviewer or None, "note": note.strip(), "reviewed_at": reviewed_at}

    def transition(self, target_id: str, to_status: str, reason: str) -> dict[str, Any]:
        self._require_initialized()
        to_status = to_status.strip().upper()
        reason = reason.strip()
        if to_status not in STATE_SEQUENCE or not reason:
            raise NovelAnimeRuntimeError("transition status or reason is invalid")
        if to_status == "SOURCE_READY":
            try:
                catalog = load_catalog(self.project_dir / CATALOG_RELATIVE_PATH)
            except NovelSourceCatalogError as error:
                raise NovelAnimeRuntimeError(f"SOURCE_READY requires a valid source catalog: {error}") from error
            if catalog["adaptation_policy"]["script_adaptation_allowed"] is not True or catalog["rights_assessment"]["human_review"]["status"] != "APPROVED":
                raise NovelAnimeRuntimeError("SOURCE_READY requires approved source rights and script adaptation permission")
        if to_status == "BIBLE_READY":
            try:
                bible_state = story_bible_readiness(self.project_dir)
            except NovelStoryBibleError as error:
                raise NovelAnimeRuntimeError(f"BIBLE_READY requires a valid story bible: {error}") from error
            if not bible_state["ready"]:
                raise NovelAnimeRuntimeError(f"BIBLE_READY is blocked: {'; '.join(bible_state['blockers'])}")
        now = utc_timestamp()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM entities WHERE entity_id = ?", (target_id,)).fetchone()
            if row is None:
                raise NovelAnimeRuntimeError("state target must be a registered entity")
            current = str(row["status"])
            try:
                expected = STATE_SEQUENCE[STATE_SEQUENCE.index(current) + 1]
            except (ValueError, IndexError) as error:
                raise NovelAnimeRuntimeError(f"cannot advance terminal or unknown state: {current}") from error
            if to_status != expected:
                raise NovelAnimeRuntimeError(f"invalid transition {current} -> {to_status}; expected {expected}")
            if to_status == "WRITING_READY":
                try:
                    report = load_story_review(self.project_dir)
                    current_review = audit_story(self.project_dir)
                except (NovelStoryReviewError, ValueError) as error:
                    raise NovelAnimeRuntimeError(f"WRITING_READY requires a current story review: {error}") from error
                if report["input_revisions"] != current_review["input_revisions"]:
                    raise NovelAnimeRuntimeError("WRITING_READY requires a non-stale story review")
                if report["overall_status"] != "PASS" or report["human_review"]["status"] != "APPROVED":
                    raise NovelAnimeRuntimeError("WRITING_READY requires a PASS story review and explicit human approval")
            gate = REQUIRED_GATE[to_status]
            review = connection.execute("SELECT status FROM reviews WHERE target_id = ? AND gate = ?", (target_id, gate)).fetchone()
            if review is None or review[0] != "APPROVED":
                raise NovelAnimeRuntimeError(f"transition requires approved review gate: {gate}")
            payload = json.loads(row["payload_json"])
            payload["status"] = to_status
            payload["revision"] = int(payload.get("revision", row["revision"])) + 1
            connection.execute("UPDATE entities SET revision = ?, status = ?, payload_json = ?, updated_at = ? WHERE entity_id = ?", (payload["revision"], to_status, json.dumps(payload, ensure_ascii=False, sort_keys=True), now, target_id))
            connection.execute("INSERT INTO state_transitions(target_id, from_status, to_status, reason, created_at) VALUES(?, ?, ?, ?, ?)", (target_id, current, to_status, reason, now))
        return {"target_id": target_id, "from_status": current, "to_status": to_status, "required_gate": gate, "revision": payload["revision"]}

    def queue_rerun(self, root_id: str, reason: str) -> list[dict[str, Any]]:
        self._require_initialized()
        reason = reason.strip()
        if not reason:
            raise NovelAnimeRuntimeError("rerun reason must not be empty")
        impact = self.repository.impact([root_id])
        with self._connect() as connection:
            root = connection.execute("SELECT entity_type FROM entities WHERE entity_id = ?", (root_id,)).fetchone()
        if root is None:
            raise NovelAnimeRuntimeError("rerun root is unknown")
        targets = [{"entity_id": root_id, "entity_type": str(root[0]), "depth": 0}] + impact
        batch = uuid.uuid4().hex[:12]
        jobs = []
        for target in sorted(targets, key=lambda item: (-int(item["depth"]), str(item["entity_id"]))):
            jobs.append(self.submit_job(f"REBUILD_{str(target['entity_type']).upper()}", str(target["entity_id"]), {"rerun_root": root_id, "reason": reason, "dependency_depth": int(target["depth"])}, priority=int(target["depth"]), idempotency_key=f"rerun:{batch}:{target['entity_id']}"))
        return jobs

    def work_once(self, worker_id: str) -> dict[str, Any] | None:
        job = self.claim_job(worker_id)
        if job is None:
            return None
        try:
            if job["job_type"] == "VALIDATE_PROJECT":
                project = load_project(self.repository.manifest_path)
                result = {"project_id": project["project_id"], "episodes": len(project["episodes"]), "repository": self.repository.stats()}
            elif job["job_type"] == "IMPACT_ANALYSIS":
                roots = job["payload"].get("entity_ids") or [job["target_id"]]
                result = {"roots": roots, "impact": self.repository.impact(roots)}
            elif job["job_type"] == "CREATE_SNAPSHOT":
                result = self.repository.create_snapshot(str(job["payload"].get("label") or "runtime-snapshot"))
            else:
                raise NovelAnimeRuntimeError(f"no worker handler for {job['job_type']}")
        except Exception as error:
            return self.fail_job(job["job_id"], worker_id, str(error))
        return self.complete_job(job["job_id"], worker_id, result)

    def migrate_legacy_pilot(self, source_dir: Path) -> dict[str, Any]:
        self._require_initialized()
        source_dir = Path(source_dir).expanduser().resolve()
        if not source_dir.is_dir():
            raise NovelAnimeRuntimeError("legacy pilot directory does not exist")
        migration_key = "legacy-jinghua-yuan-local-pilot-v1"
        with self._connect() as connection:
            existing = connection.execute("SELECT report_json FROM migrations WHERE migration_key = ?", (migration_key,)).fetchone()
            if existing:
                report = json.loads(existing[0])
                report["reused"] = True
                return report
        migrated = []
        for index in range(1, 6):
            episode_id = f"S01E{index:03d}"
            source = source_dir / "episodes" / f"episode-{index:02d}" / "final.mp4"
            if not source.is_file():
                raise NovelAnimeRuntimeError(f"legacy episode is missing: {source}")
            target = self.project_dir / "assets" / "legacy" / "pilot" / f"{episode_id}-animatic.mp4"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and _sha256(target) != _sha256(source):
                raise NovelAnimeRuntimeError(f"legacy target exists with different content: {target}")
            if not target.exists():
                shutil.copy2(source, target)
            asset = self.repository.register_asset(f"AST-LEGACY-{episode_id}-ANIMATIC", "video", target, metadata={"title": f"旧样片 {episode_id}", "legacy": True, "publication_allowed": False}, source_entity_ids=[episode_id])
            migrated.append(asset)
        report = {"migration_key": migration_key, "source_path": str(source_dir), "target_project": self.project_dir.name, "assets": migrated, "publication_allowed": False, "reused": False, "completed_at": utc_timestamp()}
        report_dir = self.project_dir / ".videocreator" / "migrations"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{migration_key}.json"
        data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        descriptor, temp_name = tempfile.mkstemp(prefix=".migration.", suffix=".tmp", dir=report_dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(data)
            os.replace(temp_name, report_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        with self._connect() as connection:
            connection.execute("INSERT INTO migrations(migration_key, source_path, report_json, completed_at) VALUES(?, ?, ?, ?)", (migration_key, str(source_dir), json.dumps(report, ensure_ascii=False, sort_keys=True), report["completed_at"]))
        report["report_path"] = report_path.relative_to(self.project_dir).as_posix()
        return report


def runtime_stats(project_dir: Path) -> dict[str, int] | None:
    try:
        runtime = NovelAnimeRuntime(project_dir)
        if not runtime.db_path.is_file():
            return None
        return runtime.stats()
    except (NovelAnimeRuntimeError, sqlite3.DatabaseError):
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "stats", "jobs"):
        command = subparsers.add_parser(name)
        command.add_argument("project_dir", type=Path)
    submit = subparsers.add_parser("submit")
    submit.add_argument("project_dir", type=Path)
    submit.add_argument("--type", required=True)
    submit.add_argument("--target", required=True)
    submit.add_argument("--payload", default="{}")
    submit.add_argument("--idempotency-key")
    work = subparsers.add_parser("work-once")
    work.add_argument("project_dir", type=Path)
    work.add_argument("--worker", required=True)
    cancel = subparsers.add_parser("cancel")
    cancel.add_argument("project_dir", type=Path)
    cancel.add_argument("job_id")
    recover = subparsers.add_parser("recover")
    recover.add_argument("project_dir", type=Path)
    review = subparsers.add_parser("review")
    review.add_argument("project_dir", type=Path)
    review.add_argument("--target", required=True)
    review.add_argument("--gate", required=True)
    review.add_argument("--status", required=True, choices=sorted(REVIEW_STATUSES))
    review.add_argument("--reviewer", default="")
    review.add_argument("--note", default="")
    transition = subparsers.add_parser("transition")
    transition.add_argument("project_dir", type=Path)
    transition.add_argument("--target", required=True)
    transition.add_argument("--to", required=True)
    transition.add_argument("--reason", required=True)
    rerun = subparsers.add_parser("rerun")
    rerun.add_argument("project_dir", type=Path)
    rerun.add_argument("--root", required=True)
    rerun.add_argument("--reason", required=True)
    migrate = subparsers.add_parser("migrate-legacy")
    migrate.add_argument("project_dir", type=Path)
    migrate.add_argument("--source", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    runtime = NovelAnimeRuntime(args.project_dir)
    try:
        if args.command == "init":
            result: Any = runtime.initialize()
        elif args.command == "stats":
            result = runtime.stats()
        elif args.command == "jobs":
            result = runtime.list_jobs()
        elif args.command == "submit":
            payload = json.loads(args.payload)
            if not isinstance(payload, dict):
                raise NovelAnimeRuntimeError("job payload must be a JSON object")
            result = runtime.submit_job(args.type, args.target, payload, idempotency_key=args.idempotency_key)
        elif args.command == "work-once":
            result = runtime.work_once(args.worker)
        elif args.command == "cancel":
            result = runtime.cancel_job(args.job_id)
        elif args.command == "recover":
            result = runtime.recover_stale()
        elif args.command == "review":
            result = runtime.record_review(args.target, args.gate, args.status, args.reviewer, args.note)
        elif args.command == "transition":
            result = runtime.transition(args.target, args.to, args.reason)
        elif args.command == "rerun":
            result = runtime.queue_rerun(args.root, args.reason)
        else:
            result = runtime.migrate_legacy_pilot(args.source)
    except (NovelAnimeProjectError, NovelAnimeRepositoryError, NovelAnimeRuntimeError, NovelSourceCatalogError, OSError, sqlite3.DatabaseError, json.JSONDecodeError) as error:
        print(f"novel_anime_runtime: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
