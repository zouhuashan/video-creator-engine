#!/usr/bin/env python3
"""Manage music, ambience, SFX, licensing, cues, and mix settings."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_animatic import load_animatic
SCHEMA_PATH = ROOT / "schemas" / "novel-audio-assets.schema.json"
OUTPUT = Path("audio/audio-assets.json")
class NovelAudioAssetError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_audio_assets(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); animatic = load_animatic(project_dir); now = utc_timestamp()
    return validate_audio_assets(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "animatic_revision": animatic["revision"], "revision": 1, "created_at": now, "updated_at": now, "tracks": [], "cues": [], "mix_profile": {"target_lufs": -16.0, "true_peak_db": -1.0, "dialogue_ducking_db": -6.0, "sample_rate": 48000}})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelAudioAssetError(f"audio schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_audio_assets(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelAudioAssetError("audio assets must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); animatic = load_animatic(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelAudioAssetError("audio assets do not match project")
    if package["animatic_revision"] != animatic["revision"]: raise NovelAudioAssetError("audio assets upstream revision is stale")
    track_ids = {track["id"] for track in package["tracks"]}; episode_ids = {episode["episode_id"] for episode in animatic["episodes"]}
    if len(track_ids) != len(package["tracks"]): raise NovelAudioAssetError("duplicate audio track")
    for track in package["tracks"]:
        if track["status"] == "READY" and (not track["path"] or track["license_status"] != "CLEARED" or track["human_review"]["status"] != "APPROVED"): raise NovelAudioAssetError(f"READY {track['id']} requires cleared reviewed media")
    cue_ids = set()
    for cue in package["cues"]:
        if cue["id"] in cue_ids: raise NovelAudioAssetError("duplicate audio cue")
        cue_ids.add(cue["id"])
        if cue["track_id"] not in track_ids or cue["episode_id"] not in episode_ids: raise NovelAudioAssetError(f"cue {cue['id']} has invalid reference")
    return package
def write_audio_assets(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_audio_assets(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelAudioAssetError(f"refusing to overwrite audio assets: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".audio-assets.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_audio_assets(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelAudioAssetError(f"cannot read audio assets: {e}") from e
    return validate_audio_assets(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_audio_assets(project_dir)
    except (NovelAudioAssetError, ValueError): return None
    return {"revision": package["revision"], "track_count": len(package["tracks"]), "ready_track_count": sum(1 for item in package["tracks"] if item["status"] == "READY"), "cue_count": len(package["cues"]), "cleared_track_count": sum(1 for item in package["tracks"] if item["license_status"] == "CLEARED"), "target_lufs": package["mix_profile"]["target_lufs"]}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_audio_assets(args.project_dir, build_audio_assets(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelAudioAssetError, OSError, ValueError) as error: print(f"novel_audio_assets: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
