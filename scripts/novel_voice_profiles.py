#!/usr/bin/env python3
"""Manage character voice profiles and line-level dialogue/narration assignments."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_episode_script import load_script_package
from scripts.novel_story_bible import load_bible
SCHEMA_PATH = ROOT / "schemas" / "novel-voice-profiles.schema.json"
OUTPUT = Path("audio/voice-profiles.json")
class NovelVoiceProfileError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_voice_profiles(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); scripts = load_script_package(project_dir); now = utc_timestamp(); profiles = [{"id": f"VOICE-{item['id']}-01", "character_id": item["id"], "language": "zh-CN", "gender": "", "age_range": "", "timbre": "", "pitch": "", "speed": 1.0, "provider": "local", "voice_id": "", "status": "DRAFT", "human_review": _review()} for item in bible["characters"]]; profile_ids = {item["character_id"]: item["id"] for item in profiles}; lines = []
    for script in scripts["episode_scripts"]:
        for scene in script["scenes"]:
            for unit in scene["units"]:
                if unit["kind"] not in {"DIALOGUE", "NARRATION"}: continue
                speaker = unit["speaker_character_id"] if unit["kind"] == "DIALOGUE" else None
                lines.append({"unit_id": unit["id"], "episode_id": script["episode_id"], "kind": unit["kind"], "speaker_character_id": speaker, "profile_id": profile_ids.get(speaker), "text": unit["text"], "emotion": (unit.get("emotion") or {}).get("label", "") if isinstance(unit.get("emotion"), dict) else "", "pronunciation_note": "", "status": "PLANNED"})
    return validate_voice_profiles(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "script_revision": scripts["revision"], "revision": 1, "created_at": now, "updated_at": now, "profiles": profiles, "line_assignments": lines})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelVoiceProfileError(f"voice schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_voice_profiles(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelVoiceProfileError("voice profiles must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); scripts = load_script_package(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelVoiceProfileError("voice profiles do not match project")
    if package["script_revision"] != scripts["revision"]: raise NovelVoiceProfileError("voice profiles upstream revision is stale")
    character_ids = {item["id"] for item in bible["characters"]}; profile_ids = {item["id"] for item in package["profiles"]}
    if {item["character_id"] for item in package["profiles"]} != character_ids: raise NovelVoiceProfileError("voice profiles must cover every story character")
    if len(profile_ids) != len(package["profiles"]): raise NovelVoiceProfileError("duplicate voice profile")
    expected = {unit["id"]: (script["episode_id"], unit) for script in scripts["episode_scripts"] for scene in script["scenes"] for unit in scene["units"] if unit["kind"] in {"DIALOGUE", "NARRATION"}}
    if {item["unit_id"] for item in package["line_assignments"]} != set(expected): raise NovelVoiceProfileError("voice line assignments must cover dialogue and narration units")
    for line in package["line_assignments"]:
        episode, unit = expected[line["unit_id"]]
        if line["episode_id"] != episode or line["text"] != unit["text"]: raise NovelVoiceProfileError(f"voice line {line['unit_id']} drifted from script")
        if line["kind"] == "DIALOGUE" and line["profile_id"] not in profile_ids: raise NovelVoiceProfileError(f"dialogue {line['unit_id']} requires a voice profile")
        if line["kind"] == "NARRATION" and line["profile_id"] is not None: raise NovelVoiceProfileError(f"narration {line['unit_id']} cannot bind a character profile")
    return package
def write_voice_profiles(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_voice_profiles(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelVoiceProfileError(f"refusing to overwrite voice profiles: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".voice-profiles.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_voice_profiles(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelVoiceProfileError(f"cannot read voice profiles: {e}") from e
    return validate_voice_profiles(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_voice_profiles(project_dir)
    except (NovelVoiceProfileError, ValueError): return None
    return {"revision": package["revision"], "profile_count": len(package["profiles"]), "ready_profile_count": sum(1 for item in package["profiles"] if item["status"] == "READY"), "line_count": len(package["line_assignments"]), "ready_line_count": sum(1 for item in package["line_assignments"] if item["status"] == "READY")}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_voice_profiles(args.project_dir, build_voice_profiles(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelVoiceProfileError, OSError, ValueError) as error: print(f"novel_voice_profiles: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
