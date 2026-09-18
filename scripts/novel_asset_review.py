#!/usr/bin/env python3
"""Manage reference packages, asset-version choices, and art review gates."""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_character_designs import NovelCharacterDesignError, load_character_designs
from scripts.novel_visual_bible import load_visual_bible, readiness as visual_readiness
from scripts.novel_environment_assets import load_environment_assets

SCHEMA_PATH = ROOT / "schemas" / "novel-asset-review.schema.json"
OUTPUT = Path("visual-bible/asset-review.json")
class NovelAssetReviewError(ValueError): pass

def signature(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _review(target_type: str, target_id: str) -> dict[str, Any]:
    return {"id": f"ARTREV-{target_type[:4]}-{target_id}", "target_type": target_type, "target_id": target_id, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": "", "blocking_findings": []}
def _current_assets(project_dir: Path) -> dict[str, int]:
    repo = NovelAnimeRepository(project_dir)
    if not repo.db_path.is_file(): return {}
    with sqlite3.connect(repo.db_path) as db:
        return {str(row[0]): int(row[1]) for row in db.execute("SELECT asset_id, version FROM asset_versions WHERE is_current = 1")}
def build_asset_review(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); visual = load_visual_bible(project_dir); environment = load_environment_assets(project_dir); now = utc_timestamp(); packages = []; reviews = []; current = _current_assets(project_dir)
    try:
        characters = load_character_designs(project_dir)
    except NovelCharacterDesignError:
        characters = {"character_designs": []}
    for design in characters.get("character_designs", []):
        refs = []
        for item in design["turnarounds"]:
            if item["asset_id"] in current:
                refs.append({"id": f"REF-{design['character_id']}-{item['view'].replace('_', '-')}", "view": item["view"], "asset_id": item["asset_id"], "version": current[item["asset_id"]], "role": "IDENTITY", "status": "CANDIDATE", "continuity_signature": item["identity_signature"]})
        for item in design["expressions"]:
            if item["asset_id"] in current:
                refs.append({"id": f"REF-{item['id']}", "view": item["emotion"], "asset_id": item["asset_id"], "version": current[item["asset_id"]], "role": "POSE", "status": "CANDIDATE", "continuity_signature": item["identity_signature"]})
        for item in design["costumes"]:
            if item["asset_id"] in current:
                refs.append({"id": f"REF-{item['id']}", "view": item["name"], "asset_id": item["asset_id"], "version": current[item["asset_id"]], "role": "COLOR", "status": "CANDIDATE", "continuity_signature": item["identity_signature"]})
        if refs:
            package_id = f"REFPACK-{design['character_id']}"; packages.append({"id": package_id, "entity_id": design["character_id"], "entity_type": "character", "purpose": "角色身份、表情与服装参考", "references": refs, "selected_reference_ids": [], "human_review": _review("REFERENCE_PACKAGE", package_id)}); reviews.append(packages[-1]["human_review"])
    for design in environment.get("location_designs", []):
        if design["variants"]:
            package_id = f"REFPACK-{design['location_id']}"; refs = [{"id": f"REF-{item['id']}", "view": item["id"], "asset_id": item["asset_id"], "version": current[item["asset_id"]], "role": "ENVIRONMENT", "status": "CANDIDATE", "continuity_signature": item["continuity_signature"]} for item in design["variants"] if item["asset_id"] in current]
            packages.append({"id": package_id, "entity_id": design["location_id"], "entity_type": "location", "purpose": "环境关键帧与变体参考", "references": refs, "selected_reference_ids": [], "human_review": _review("REFERENCE_PACKAGE", package_id)}); reviews.append(packages[-1]["human_review"])
    for design in environment.get("prop_designs", []):
        refs = [{"id": f"REF-{state['id']}", "view": state["condition"], "asset_id": state["asset_id"], "version": current[state["asset_id"]], "role": "PROP", "status": "CANDIDATE", "continuity_signature": state["continuity_signature"]} for state in design["states"] if state["asset_id"] in current]
        if refs:
            package_id = f"REFPACK-{design['prop_id']}"; packages.append({"id": package_id, "entity_id": design["prop_id"], "entity_type": "prop", "purpose": "道具状态参考", "references": refs, "selected_reference_ids": [], "human_review": _review("REFERENCE_PACKAGE", package_id)}); reviews.append(packages[-1]["human_review"])
    return validate_asset_review(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "visual_bible_revision": visual["revision"], "environment_assets_revision": environment["revision"], "revision": 1, "created_at": now, "updated_at": now, "reference_packages": packages, "selection_records": [], "art_reviews": reviews})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelAssetReviewError(f"asset review schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_asset_review(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelAssetReviewError("asset review must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); visual = load_visual_bible(project_dir); environment = load_environment_assets(project_dir); current = _current_assets(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelAssetReviewError("asset review does not match project")
    if package["visual_bible_revision"] != visual["revision"] or package["environment_assets_revision"] != environment["revision"]: raise NovelAssetReviewError("asset review upstream revisions are stale")
    refs: dict[str, dict[str, Any]] = {}; ids = set()
    for item in package["reference_packages"]:
        if item["id"] in ids: raise NovelAssetReviewError("duplicate reference package")
        ids.add(item["id"]); review_ids = {r["id"] for r in package["art_reviews"]}
        if item["human_review"]["id"] not in review_ids: raise NovelAssetReviewError(f"{item['id']} lacks art review")
        for ref in item["references"]:
            if ref["id"] in refs: raise NovelAssetReviewError("duplicate reference ID")
            refs[ref["id"]] = ref
            if ref["status"] == "SELECTED" and current.get(ref["asset_id"]) != ref["version"]: raise NovelAssetReviewError(f"selected reference {ref['id']} is not the current registered asset version")
        if set(item["selected_reference_ids"]) - set(refs): raise NovelAssetReviewError(f"{item['id']} selects unknown reference")
    selection_ids = set()
    for record in package["selection_records"]:
        if record["id"] in selection_ids: raise NovelAssetReviewError("duplicate selection record")
        selection_ids.add(record["id"]); ref = refs.get(record["reference_id"])
        if not ref or record["asset_id"] != ref["asset_id"] or record["version"] != ref["version"]: raise NovelAssetReviewError(f"selection {record['id']} does not match reference")
        if record["status"] == "SELECTED" and current.get(record["asset_id"]) != record["version"]: raise NovelAssetReviewError(f"selection {record['id']} is stale")
    return package
def write_asset_review(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_asset_review(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelAssetReviewError(f"refusing to overwrite asset review: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".asset-review.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_asset_review(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelAssetReviewError(f"cannot read asset review: {e}") from e
    return validate_asset_review(project_dir, payload)
def readiness(project_dir: Path) -> dict[str, Any]:
    package = load_asset_review(project_dir); blockers = list(visual_readiness(project_dir)["blockers"])
    for item in package["reference_packages"]:
        if item["human_review"]["status"] != "APPROVED": blockers.append(f"{item['id']} lacks approved art review")
        if not item["selected_reference_ids"]: blockers.append(f"{item['id']} has no selected reference")
    return {"ready": not blockers, "blockers": blockers}
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_asset_review(project_dir); state = readiness(project_dir)
    except (NovelAssetReviewError, ValueError): return None
    return {"revision": package["revision"], "reference_package_count": len(package["reference_packages"]), "reference_count": sum(len(i["references"]) for i in package["reference_packages"]), "selected_reference_count": sum(len(i["selected_reference_ids"]) for i in package["reference_packages"]), "selection_count": len(package["selection_records"]), "approved_review_count": sum(1 for i in package["art_reviews"] if i["status"] == "APPROVED"), "ready": state["ready"], "blocker_count": len(state["blockers"])}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_asset_review(args.project_dir, build_asset_review(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelAssetReviewError, OSError, ValueError) as error: print(f"novel_asset_review: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
