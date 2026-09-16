#!/usr/bin/env python3
"""Create mix, loudness, and audio-video synchronization plans."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_animatic import load_animatic
from scripts.novel_audio_assets import load_audio_assets
from scripts.novel_voice_profiles import load_voice_profiles
SCHEMA_PATH = ROOT / "schemas" / "novel-audio-mix.schema.json"
OUTPUT = Path("audio/mix-plan.json")
class NovelAudioMixError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_audio_mix(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); audio = load_audio_assets(project_dir); voices = load_voice_profiles(project_dir); animatic = load_animatic(project_dir); now = utc_timestamp(); episodes = [{"episode_id": item["episode_id"], "dialogue_line_ids": [], "cue_ids": [], "target_lufs": audio["mix_profile"]["target_lufs"], "true_peak_db": audio["mix_profile"]["true_peak_db"], "sync_offset_ms": 0.0, "status": "DRAFT", "output_path": None, "human_review": _review()} for item in animatic["episodes"]]
    return validate_audio_mix(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "audio_assets_revision": audio["revision"], "voice_profiles_revision": voices["revision"], "animatic_revision": animatic["revision"], "revision": 1, "created_at": now, "updated_at": now, "episodes": episodes})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelAudioMixError(f"audio mix schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_audio_mix(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelAudioMixError("audio mix must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); audio = load_audio_assets(project_dir); voices = load_voice_profiles(project_dir); animatic = load_animatic(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelAudioMixError("audio mix does not match project")
    if (package["audio_assets_revision"], package["voice_profiles_revision"], package["animatic_revision"]) != (audio["revision"], voices["revision"], animatic["revision"]): raise NovelAudioMixError("audio mix upstream revisions are stale")
    episode_ids = {episode["episode_id"] for episode in animatic["episodes"]}; cue_ids = {cue["id"] for cue in audio["cues"]}; line_ids = {line["unit_id"] for line in voices["line_assignments"]}
    if {item["episode_id"] for item in package["episodes"]} != episode_ids: raise NovelAudioMixError("audio mix must cover every episode")
    for episode in package["episodes"]:
        if set(episode["cue_ids"]) - cue_ids or set(episode["dialogue_line_ids"]) - line_ids: raise NovelAudioMixError(f"{episode['episode_id']} references unknown audio input")
        if episode["sync_offset_ms"] < -100 or episode["sync_offset_ms"] > 100: raise NovelAudioMixError(f"{episode['episode_id']} audio-video sync offset exceeds 100ms")
        if episode["status"] == "READY" and (not episode["output_path"] or episode["human_review"]["status"] != "APPROVED"): raise NovelAudioMixError(f"READY {episode['episode_id']} requires reviewed mix output")
    return package
def write_audio_mix(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_audio_mix(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelAudioMixError(f"refusing to overwrite audio mix: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".mix-plan.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_audio_mix(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelAudioMixError(f"cannot read audio mix: {e}") from e
    return validate_audio_mix(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_audio_mix(project_dir)
    except (NovelAudioMixError, ValueError): return None
    return {"revision": package["revision"], "episode_count": len(package["episodes"]), "ready_episode_count": sum(1 for item in package["episodes"] if item["status"] == "READY"), "mix_output_count": sum(1 for item in package["episodes"] if item["output_path"]), "max_sync_offset_ms": max((abs(item["sync_offset_ms"]) for item in package["episodes"]), default=0)}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_audio_mix(args.project_dir, build_audio_mix(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelAudioMixError, OSError, ValueError) as error: print(f"novel_audio_mix: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
