#!/usr/bin/env python3
"""SQLite repository, asset versions, snapshots, and impact analysis for P18."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import (
    ID_PATTERNS,
    MANIFEST_NAME,
    NovelAnimeProjectError,
    load_project,
    utc_timestamp,
)


DB_RELATIVE_PATH = Path(".videocreator") / "project.db"
SNAPSHOT_DIRECTORY = Path(".videocreator") / "snapshots"
REPOSITORY_SCHEMA_VERSION = 1
ASSET_TYPES = {"character", "costume", "location", "prop", "keyframe", "audio", "music", "sfx", "subtitle", "video"}


class NovelAnimeRepositoryError(RuntimeError):
    """Raised when repository data, versions, or dependencies are invalid."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise NovelAnimeRepositoryError("snapshot label must contain ASCII letters or numbers")
    return slug[:48].rstrip("-")


def _entity_rows(project: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    rows = [(project["ip"]["id"], "ip", project["ip"]), (project["series"]["id"], "series", project["series"])]
    for field, kind in (
        ("source_editions", "source_edition"), ("seasons", "season"), ("arcs", "arc"),
        ("episodes", "episode"), ("scenes", "scene"), ("shots", "shot"),
        ("assets", "asset"), ("renders", "render"),
    ):
        rows.extend((entity["id"], kind, entity) for entity in project[field])
    return rows


def _manifest_dependencies(project: dict[str, Any]) -> set[tuple[str, str, str]]:
    dependencies: set[tuple[str, str, str]] = set()

    def add(upstream: str | None, downstream: str | None, relation: str) -> None:
        if upstream and downstream and upstream != downstream:
            dependencies.add((upstream, downstream, relation))

    ip = project["ip"]
    series = project["series"]
    for source_id in ip["source_edition_ids"]:
        add(source_id, ip["id"], "source_for")
    add(ip["id"], series["id"], "adapts_to")
    for season in project["seasons"]:
        add(series["id"], season["id"], "contains")
    for arc in project["arcs"]:
        add(arc["season_id"], arc["id"], "contains")
    for episode in project["episodes"]:
        add(episode["season_id"], episode["id"], "contains")
        add(episode.get("arc_id"), episode["id"], "contains")
    for scene in project["scenes"]:
        add(scene["episode_id"], scene["id"], "contains")
    for shot in project["shots"]:
        add(shot["scene_id"], shot["id"], "contains")
        for asset_id in shot["asset_refs"]:
            add(asset_id, shot["id"], "used_by")
    for render in project["renders"]:
        add(render["target_id"], render["id"], "rendered_as")
        for asset_id in render["asset_refs"]:
            add(asset_id, render["id"], "input_to")
    known = {entity_id for entity_id, _, _ in _entity_rows(project)}
    for entity_id, _, entity in _entity_rows(project):
        for ref in entity.get("input_refs", []):
            if ref in known:
                add(ref, entity_id, "input_to")
        for ref in entity.get("source_refs", []):
            if ref in known:
                add(ref, entity_id, "source_for")
    return dependencies


class NovelAnimeRepository:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.manifest_path = self.project_dir / MANIFEST_NAME
        self.db_path = self.project_dir / DB_RELATIVE_PATH

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> dict[str, int]:
        project = load_project(self.manifest_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS repository_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dependencies (
                    upstream_id TEXT NOT NULL,
                    downstream_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    PRIMARY KEY (upstream_id, downstream_id, relation),
                    FOREIGN KEY (upstream_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
                    FOREIGN KEY (downstream_id) REFERENCES entities(entity_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS asset_versions (
                    asset_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    asset_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
                    PRIMARY KEY (asset_id, version),
                    FOREIGN KEY (asset_id) REFERENCES entities(entity_id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_current_asset_version ON asset_versions(asset_id) WHERE is_current = 1;
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute("INSERT OR REPLACE INTO repository_meta(key, value) VALUES('schema_version', ?)", (str(REPOSITORY_SCHEMA_VERSION),))
            connection.execute("INSERT OR REPLACE INTO repository_meta(key, value) VALUES('project_id', ?)", (project["project_id"],))
        self.sync_manifest(project)
        return self.stats()

    def _require_initialized(self) -> None:
        if not self.db_path.is_file():
            raise NovelAnimeRepositoryError(f"repository is not initialized: {self.db_path}")

    def sync_manifest(self, project: dict[str, Any] | None = None) -> dict[str, int]:
        self._require_initialized()
        project = load_project(self.manifest_path) if project is None else project
        rows = _entity_rows(project)
        dependencies = _manifest_dependencies(project)
        now = utc_timestamp()
        with self._connect() as connection:
            for entity_id, entity_type, payload in rows:
                connection.execute(
                    """INSERT INTO entities(entity_id, entity_type, revision, status, payload_json, updated_at)
                       VALUES(?, ?, ?, ?, ?, ?)
                       ON CONFLICT(entity_id) DO UPDATE SET entity_type=excluded.entity_type,
                       revision=excluded.revision, status=excluded.status,
                       payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
                    (entity_id, entity_type, int(payload["revision"]), str(payload["status"]), _json(payload), now),
                )
            manifest_ids = {entity_id for entity_id, _, _ in rows}
            placeholders = ",".join("?" for _ in manifest_ids)
            if manifest_ids:
                connection.execute(f"DELETE FROM dependencies WHERE relation != 'registered_from' AND (upstream_id IN ({placeholders}) OR downstream_id IN ({placeholders}))", tuple(manifest_ids) * 2)
            for upstream, downstream, relation in dependencies:
                connection.execute("INSERT OR IGNORE INTO dependencies(upstream_id, downstream_id, relation) VALUES(?, ?, ?)", (upstream, downstream, relation))
        return self.stats()

    def stats(self) -> dict[str, int]:
        self._require_initialized()
        with self._connect() as connection:
            return {
                "entities": int(connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]),
                "dependencies": int(connection.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0]),
                "asset_versions": int(connection.execute("SELECT COUNT(*) FROM asset_versions").fetchone()[0]),
                "snapshots": int(connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]),
            }

    def current_asset_ids(self) -> set[str]:
        """Return assets with a selected current local version."""
        self._require_initialized()
        with self._connect() as connection:
            return {str(row[0]) for row in connection.execute("SELECT asset_id FROM asset_versions WHERE is_current = 1")}

    def register_dependency(self, upstream_id: str, downstream_id: str, relation: str = "input_to") -> None:
        self._require_initialized()
        relation = relation.strip()
        if not relation or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", relation):
            raise NovelAnimeRepositoryError("relation must be a lowercase identifier")
        with self._connect() as connection:
            existing = {row[0] for row in connection.execute("SELECT entity_id FROM entities WHERE entity_id IN (?, ?)", (upstream_id, downstream_id))}
            if existing != {upstream_id, downstream_id}:
                raise NovelAnimeRepositoryError("dependency endpoints must be registered entities")
            if upstream_id == downstream_id:
                raise NovelAnimeRepositoryError("an entity cannot depend on itself")
            connection.execute("INSERT OR IGNORE INTO dependencies(upstream_id, downstream_id, relation) VALUES(?, ?, ?)", (upstream_id, downstream_id, relation))

    def register_asset(self, asset_id: str, asset_type: str, file_path: Path, *, metadata: dict[str, Any] | None = None, source_entity_ids: Iterable[str] = ()) -> dict[str, Any]:
        self._require_initialized()
        if not ID_PATTERNS["asset"].fullmatch(asset_id):
            raise NovelAnimeRepositoryError("invalid asset ID")
        if asset_type not in ASSET_TYPES:
            raise NovelAnimeRepositoryError(f"unsupported asset type: {asset_type}")
        file_path = Path(file_path).expanduser().resolve()
        if self.project_dir not in file_path.parents or not file_path.is_file():
            raise NovelAnimeRepositoryError("asset file must exist inside the project directory")
        relative = file_path.relative_to(self.project_dir).as_posix()
        checksum = _sha256(file_path)
        now = utc_timestamp()
        metadata = metadata or {}
        sources = tuple(dict.fromkeys(source_entity_ids))
        with self._connect() as connection:
            known = {row[0] for row in connection.execute("SELECT entity_id FROM entities WHERE entity_id IN (%s)" % ",".join("?" for _ in sources), sources)} if sources else set()
            if known != set(sources):
                raise NovelAnimeRepositoryError("asset source references must be registered entities")
            current_row = connection.execute("SELECT version, asset_type, relative_path, checksum FROM asset_versions WHERE asset_id = ? AND is_current = 1", (asset_id,)).fetchone()
            if current_row and str(current_row[3]) == checksum and str(current_row[2]) == relative and str(current_row[1]) == asset_type:
                return {"asset_id": asset_id, "version": int(current_row[0]), "asset_type": asset_type, "relative_path": relative, "checksum": checksum, "reused": True}
            current = connection.execute("SELECT COALESCE(MAX(version), 0) FROM asset_versions WHERE asset_id = ?", (asset_id,)).fetchone()[0]
            version = int(current) + 1
            payload = {"id": asset_id, "title": str(metadata.get("title") or asset_id), "revision": version, "status": "DRAFT", "current_version": version, "asset_type": asset_type, "relative_path": relative, "checksum": checksum}
            connection.execute(
                """INSERT INTO entities(entity_id, entity_type, revision, status, payload_json, updated_at)
                   VALUES(?, 'asset', ?, 'DRAFT', ?, ?)
                   ON CONFLICT(entity_id) DO UPDATE SET revision=excluded.revision,
                   payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
                (asset_id, version, _json(payload), now),
            )
            connection.execute("UPDATE asset_versions SET is_current = 0 WHERE asset_id = ?", (asset_id,))
            connection.execute("INSERT INTO asset_versions(asset_id, version, asset_type, relative_path, checksum, metadata_json, created_at, is_current) VALUES(?, ?, ?, ?, ?, ?, ?, 1)", (asset_id, version, asset_type, relative, checksum, _json(metadata), now))
            for source_id in sources:
                connection.execute("INSERT OR IGNORE INTO dependencies(upstream_id, downstream_id, relation) VALUES(?, ?, 'registered_from')", (source_id, asset_id))
        return {"asset_id": asset_id, "version": version, "asset_type": asset_type, "relative_path": relative, "checksum": checksum, "reused": False}

    def impact(self, entity_ids: Iterable[str]) -> list[dict[str, Any]]:
        self._require_initialized()
        roots = tuple(dict.fromkeys(entity_ids))
        if not roots:
            raise NovelAnimeRepositoryError("impact analysis requires at least one entity ID")
        with self._connect() as connection:
            known = {row[0] for row in connection.execute("SELECT entity_id FROM entities WHERE entity_id IN (%s)" % ",".join("?" for _ in roots), roots)}
            if known != set(roots):
                raise NovelAnimeRepositoryError("impact root must be a registered entity")
            adjacency: dict[str, list[tuple[str, str]]] = {}
            for row in connection.execute("SELECT upstream_id, downstream_id, relation FROM dependencies ORDER BY upstream_id, downstream_id, relation"):
                adjacency.setdefault(str(row[0]), []).append((str(row[1]), str(row[2])))
            entity_types = {str(row[0]): str(row[1]) for row in connection.execute("SELECT entity_id, entity_type FROM entities")}
        queue = deque((root, 0, None, None) for root in roots)
        visited = set(roots)
        results: list[dict[str, Any]] = []
        while queue:
            current, depth, parent, relation = queue.popleft()
            if depth:
                results.append({"entity_id": current, "entity_type": entity_types[current], "depth": depth, "via": parent, "relation": relation})
            for downstream, edge_relation in adjacency.get(current, []):
                if downstream in visited:
                    continue
                visited.add(downstream)
                queue.append((downstream, depth + 1, current, edge_relation))
        return results

    def create_snapshot(self, label: str) -> dict[str, Any]:
        self._require_initialized()
        project = load_project(self.manifest_path)
        slug = _safe_slug(label)
        created_at = utc_timestamp()
        compact_time = created_at.replace("-", "").replace(":", "").replace(".", "").replace("Z", "Z")
        snapshot_id = f"SNP-{compact_time}-{slug}".upper()
        directory = self.project_dir / SNAPSHOT_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"{snapshot_id.lower()}.json"
        if output.exists():
            raise NovelAnimeRepositoryError(f"snapshot already exists: {output.name}")
        with self._connect() as connection:
            assets = [dict(row) for row in connection.execute("SELECT asset_id, version, asset_type, relative_path, checksum, metadata_json, created_at, is_current FROM asset_versions ORDER BY asset_id, version")]
            dependencies = [dict(row) for row in connection.execute("SELECT upstream_id, downstream_id, relation FROM dependencies ORDER BY upstream_id, downstream_id, relation")]
        payload = {"snapshot_schema_version": 1, "snapshot_id": snapshot_id, "label": label.strip(), "created_at": created_at, "project": project, "asset_versions": assets, "dependencies": dependencies}
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        descriptor, temp_name = tempfile.mkstemp(prefix=".snapshot.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
            os.replace(temp_name, output)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        manifest_sha256 = _sha256(self.manifest_path)
        with self._connect() as connection:
            connection.execute("INSERT INTO snapshots(snapshot_id, label, relative_path, manifest_sha256, created_at) VALUES(?, ?, ?, ?, ?)", (snapshot_id, label.strip(), output.relative_to(self.project_dir).as_posix(), manifest_sha256, created_at))
        return {"snapshot_id": snapshot_id, "label": label.strip(), "relative_path": output.relative_to(self.project_dir).as_posix(), "manifest_sha256": manifest_sha256}


def repository_stats(project_dir: Path) -> dict[str, int] | None:
    repository = NovelAnimeRepository(project_dir)
    if not repository.db_path.is_file():
        return None
    try:
        return repository.stats()
    except (sqlite3.DatabaseError, NovelAnimeRepositoryError):
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "stats"):
        command = subparsers.add_parser(name)
        command.add_argument("project_dir", type=Path)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("project_dir", type=Path)
    snapshot.add_argument("--label", required=True)
    impact = subparsers.add_parser("impact")
    impact.add_argument("project_dir", type=Path)
    impact.add_argument("entity_ids", nargs="+")
    asset = subparsers.add_parser("register-asset")
    asset.add_argument("project_dir", type=Path)
    asset.add_argument("--asset-id", required=True)
    asset.add_argument("--type", required=True, choices=sorted(ASSET_TYPES))
    asset.add_argument("--path", type=Path, required=True)
    asset.add_argument("--source", action="append", default=[])
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository = NovelAnimeRepository(args.project_dir)
    try:
        if args.command == "init":
            result: Any = repository.initialize()
        elif args.command == "stats":
            result = repository.stats()
        elif args.command == "snapshot":
            result = repository.create_snapshot(args.label)
        elif args.command == "impact":
            result = repository.impact(args.entity_ids)
        else:
            result = repository.register_asset(args.asset_id, args.type, args.path, source_entity_ids=args.source)
    except (NovelAnimeProjectError, NovelAnimeRepositoryError, OSError, sqlite3.DatabaseError) as error:
        print(f"novel_anime_repository: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
