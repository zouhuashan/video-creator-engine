#!/usr/bin/env python3
"""Create and validate novel source editions, chapter locators, and rights gates."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, NovelAnimeProjectError, load_project, utc_timestamp  # noqa: E402


SCHEMA_VERSION = 1
CATALOG_RELATIVE_PATH = Path("sources") / "source-catalog.json"
RIGHTS_STATUSES = {"UNASSESSED", "RESEARCHING", "PUBLIC_DOMAIN_VERIFIED", "LICENSED", "BLOCKED"}
EVIDENCE_TYPES = {"author_death_record", "publication_record", "statute", "license", "institution_catalog", "scan"}
CONTRIBUTION_TYPES = {"annotation", "translation", "illustration", "layout", "preface", "typesetting"}
CONTRIBUTION_RIGHTS = {"NOT_PRESENT", "UNASSESSED", "PUBLIC_DOMAIN_VERIFIED", "LICENSED", "EXCLUDED"}
IP_PATTERN = re.compile(r"IP-([A-Z0-9]{2,12})\Z")
EDITION_PATTERN = re.compile(r"SRC-([A-Z0-9]{2,12})-\d{3}\Z")
CHAPTER_PATTERN = re.compile(r"CH-([A-Z0-9]{2,12})-\d{4}\Z")
LOCATOR_PATTERN = re.compile(r"LOC-([A-Z0-9]{2,12})-\d{4}\Z")
EVIDENCE_PATTERN = re.compile(r"EVD-([A-Z0-9]{2,12})-\d{3}\Z")


class NovelSourceCatalogError(ValueError):
    """Raised when source provenance or rights metadata is unsafe or inconsistent."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def build_catalog(project_id: str, ip_id: str, title: str, *, target_regions: list[str] | None = None) -> dict[str, Any]:
    match = IP_PATTERN.fullmatch(ip_id.strip())
    if not match:
        raise NovelSourceCatalogError("ip_id must use IP-<CODE>")
    if not project_id.strip() or not title.strip():
        raise NovelSourceCatalogError("project_id and title must not be empty")
    regions = target_regions or ["CN"]
    if any(not re.fullmatch(r"[A-Z]{2}", region) for region in regions):
        raise NovelSourceCatalogError("target regions must use two-letter uppercase codes")
    now = utc_timestamp()
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id.strip(),
        "ip_id": ip_id.strip(),
        "title": title.strip(),
        "revision": 1,
        "status": "UNASSESSED",
        "created_at": now,
        "updated_at": now,
        "target_regions": list(dict.fromkeys(regions)),
        "rights_assessment": {
            "status": "UNASSESSED",
            "basis": "",
            "jurisdictions": [],
            "territories": [],
            "evidence": [],
            "publication_allowed": False,
            "human_review": _review(),
        },
        "adaptation_policy": {
            "local_technical_test_allowed": True,
            "script_adaptation_allowed": False,
            "publication_allowed": False,
            "allowed_transformations": [],
            "forbidden_material": ["modern_annotations", "modern_illustrations", "existing_screen_designs"],
            "requires_human_review": True,
        },
        "editions": [],
        "chapters": [],
        "locators": [],
    }
    return validate_catalog(catalog)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NovelSourceCatalogError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise NovelSourceCatalogError(f"{label} must be a list")
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False, maximum: int = 2000) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise NovelSourceCatalogError(f"{label} must be a valid string")
    return value.strip()


def _url(value: Any, label: str) -> str:
    text = _text(value, label, maximum=2000)
    parsed = urlsplit(text)
    remote = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    local_upload = parsed.scheme == "local" and parsed.hostname == "upload"
    if not (remote or local_upload) or parsed.username or parsed.password:
        raise NovelSourceCatalogError(f"{label} must be an absolute http(s) URL or local://upload URI without credentials")
    return text


def _date(value: Any, label: str) -> str:
    text = _text(value, label, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise NovelSourceCatalogError(f"{label} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise NovelSourceCatalogError(f"{label} must use YYYY-MM-DD")
    return text


def _unique_id(items: list[dict[str, Any]], pattern: re.Pattern[str], label: str, code: str) -> set[str]:
    ids: set[str] = set()
    for index, item in enumerate(items):
        entity_id = item.get("id")
        match = pattern.fullmatch(str(entity_id))
        if not match or match.group(1) != code:
            raise NovelSourceCatalogError(f"{label}[{index}].id must use the project IP code")
        if entity_id in ids:
            raise NovelSourceCatalogError(f"duplicate {label} ID: {entity_id}")
        ids.add(str(entity_id))
    return ids


def validate_catalog(payload: Any) -> dict[str, Any]:
    catalog = _object(payload, "catalog")
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise NovelSourceCatalogError("unsupported source catalog schema")
    ip_match = IP_PATTERN.fullmatch(str(catalog.get("ip_id") or ""))
    if not ip_match:
        raise NovelSourceCatalogError("catalog.ip_id is invalid")
    code = ip_match.group(1)
    for field in ("project_id", "title", "created_at", "updated_at"):
        _text(catalog.get(field), f"catalog.{field}")
    if type(catalog.get("revision")) is not int or catalog["revision"] < 1:
        raise NovelSourceCatalogError("catalog.revision must be a positive integer")
    if catalog.get("status") not in RIGHTS_STATUSES:
        raise NovelSourceCatalogError("catalog.status is invalid")
    regions = _list(catalog.get("target_regions"), "catalog.target_regions")
    if not regions or any(not isinstance(region, str) or not re.fullmatch(r"[A-Z]{2}", region) for region in regions):
        raise NovelSourceCatalogError("catalog.target_regions must contain two-letter region codes")

    rights = _object(catalog.get("rights_assessment"), "rights_assessment")
    if rights.get("status") not in RIGHTS_STATUSES:
        raise NovelSourceCatalogError("rights_assessment.status is invalid")
    if catalog.get("status") != rights.get("status"):
        raise NovelSourceCatalogError("catalog and rights assessment statuses must match")
    _text(rights.get("basis"), "rights_assessment.basis", allow_empty=True, maximum=4000)
    jurisdictions = _list(rights.get("jurisdictions"), "rights_assessment.jurisdictions")
    territories = _list(rights.get("territories"), "rights_assessment.territories")
    evidence = _list(rights.get("evidence"), "rights_assessment.evidence")
    review = _object(rights.get("human_review"), "rights_assessment.human_review")
    if review.get("required") is not True or review.get("status") not in {"PENDING", "APPROVED", "CHANGES_REQUESTED"}:
        raise NovelSourceCatalogError("rights assessment must require a valid human review")
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence):
        item = _object(item, f"evidence[{index}]")
        evidence_id = str(item.get("id") or "")
        evidence_match = EVIDENCE_PATTERN.fullmatch(evidence_id)
        if not evidence_match or evidence_match.group(1) != code or evidence_id in evidence_ids:
            raise NovelSourceCatalogError(f"evidence[{index}].id is invalid or duplicated")
        evidence_ids.add(evidence_id)
        if item.get("type") not in EVIDENCE_TYPES:
            raise NovelSourceCatalogError(f"evidence[{index}].type is invalid")
        _text(item.get("title"), f"evidence[{index}].title")
        _url(item.get("url"), f"evidence[{index}].url")
        _date(item.get("accessed_at"), f"evidence[{index}].accessed_at")
        _text(item.get("note"), f"evidence[{index}].note", allow_empty=True)

    policy = _object(catalog.get("adaptation_policy"), "adaptation_policy")
    for field in ("local_technical_test_allowed", "script_adaptation_allowed", "publication_allowed", "requires_human_review"):
        if type(policy.get(field)) is not bool:
            raise NovelSourceCatalogError(f"adaptation_policy.{field} must be boolean")
    _list(policy.get("allowed_transformations"), "adaptation_policy.allowed_transformations")
    _list(policy.get("forbidden_material"), "adaptation_policy.forbidden_material")
    if policy["requires_human_review"] is not True:
        raise NovelSourceCatalogError("adaptation policy must retain human review")

    editions = [_object(item, f"editions[{index}]") for index, item in enumerate(_list(catalog.get("editions"), "editions"))]
    chapters = [_object(item, f"chapters[{index}]") for index, item in enumerate(_list(catalog.get("chapters"), "chapters"))]
    locators = [_object(item, f"locators[{index}]") for index, item in enumerate(_list(catalog.get("locators"), "locators"))]
    edition_ids = _unique_id(editions, EDITION_PATTERN, "editions", code)
    chapter_ids = _unique_id(chapters, CHAPTER_PATTERN, "chapters", code)
    locator_ids = _unique_id(locators, LOCATOR_PATTERN, "locators", code)

    unresolved_contribution = False
    for index, edition in enumerate(editions):
        _text(edition.get("title"), f"editions[{index}].title")
        _text(edition.get("edition_label"), f"editions[{index}].edition_label")
        _text(edition.get("author"), f"editions[{index}].author")
        _text(edition.get("language"), f"editions[{index}].language")
        _url(edition.get("source_url"), f"editions[{index}].source_url")
        if edition.get("rights_status") not in RIGHTS_STATUSES:
            raise NovelSourceCatalogError(f"editions[{index}].rights_status is invalid")
        year = edition.get("publication_year")
        if year is not None and (type(year) is not int or not 1 <= year <= 9999):
            raise NovelSourceCatalogError(f"editions[{index}].publication_year is invalid")
        publisher = edition.get("publisher")
        if publisher is not None and not isinstance(publisher, str):
            raise NovelSourceCatalogError(f"editions[{index}].publisher is invalid")
        checksum = edition.get("file_checksum")
        if checksum is not None and not re.fullmatch(r"[a-f0-9]{64}", str(checksum)):
            raise NovelSourceCatalogError(f"editions[{index}].file_checksum is invalid")
        refs = _list(edition.get("chapter_ids"), f"editions[{index}].chapter_ids")
        if any(ref not in chapter_ids for ref in refs):
            raise NovelSourceCatalogError(f"editions[{index}].chapter_ids contains an unknown chapter")
        expected_chapters = {chapter["id"] for chapter in chapters if chapter.get("edition_id") == edition["id"]}
        if set(refs) != expected_chapters:
            raise NovelSourceCatalogError(f"editions[{index}].chapter_ids must match its chapter records")
        contributions = _list(edition.get("modern_contributions"), f"editions[{index}].modern_contributions")
        seen_types: set[str] = set()
        for contribution in contributions:
            contribution = _object(contribution, "modern_contribution")
            contribution_type = contribution.get("type")
            rights_status = contribution.get("rights_status")
            if contribution_type not in CONTRIBUTION_TYPES or contribution_type in seen_types:
                raise NovelSourceCatalogError("modern contribution type is invalid or duplicated")
            if rights_status not in CONTRIBUTION_RIGHTS:
                raise NovelSourceCatalogError("modern contribution rights status is invalid")
            seen_types.add(str(contribution_type))
            unresolved_contribution = unresolved_contribution or rights_status == "UNASSESSED"

    sequences: set[tuple[str, int]] = set()
    for index, chapter in enumerate(chapters):
        if chapter.get("edition_id") not in edition_ids:
            raise NovelSourceCatalogError(f"chapters[{index}].edition_id is unknown")
        sequence = chapter.get("sequence")
        if type(sequence) is not int or sequence < 1 or (chapter["edition_id"], sequence) in sequences:
            raise NovelSourceCatalogError(f"chapters[{index}].sequence is invalid or duplicated")
        sequences.add((chapter["edition_id"], sequence))
        _text(chapter.get("title"), f"chapters[{index}].title")
        volume = chapter.get("volume")
        if volume is not None and not isinstance(volume, str):
            raise NovelSourceCatalogError(f"chapters[{index}].volume is invalid")
        refs = _list(chapter.get("locator_ids"), f"chapters[{index}].locator_ids")
        if any(ref not in locator_ids for ref in refs):
            raise NovelSourceCatalogError(f"chapters[{index}].locator_ids contains an unknown locator")
        expected_locators = {locator["id"] for locator in locators if locator.get("chapter_id") == chapter["id"]}
        if set(refs) != expected_locators:
            raise NovelSourceCatalogError(f"chapters[{index}].locator_ids must match its locator records")

    for index, locator in enumerate(locators):
        if locator.get("chapter_id") not in chapter_ids:
            raise NovelSourceCatalogError(f"locators[{index}].chapter_id is unknown")
        _url(locator.get("source_url"), f"locators[{index}].source_url")
        location = _object(locator.get("location"), f"locators[{index}].location")
        page_start, page_end = location.get("page_start"), location.get("page_end")
        paragraph_start, paragraph_end = location.get("paragraph_start"), location.get("paragraph_end")
        for value, label in ((page_start, "page_start"), (page_end, "page_end"), (paragraph_start, "paragraph_start"), (paragraph_end, "paragraph_end")):
            if value is not None and (type(value) is not int or value < 1):
                raise NovelSourceCatalogError(f"locators[{index}].{label} is invalid")
        if page_start and page_end and page_end < page_start:
            raise NovelSourceCatalogError(f"locators[{index}] page range is reversed")
        if paragraph_start and paragraph_end and paragraph_end < paragraph_start:
            raise NovelSourceCatalogError(f"locators[{index}] paragraph range is reversed")
        _text(location.get("label"), f"locators[{index}].location.label", allow_empty=True)
        if not any(value is not None for value in (page_start, page_end, paragraph_start, paragraph_end)) and not str(location.get("label") or "").strip():
            raise NovelSourceCatalogError(f"locators[{index}] must include a range or label")
        if locator.get("text_storage_allowed") is not False:
            raise NovelSourceCatalogError("source locators must default to text_storage_allowed=false")
        excerpt_hash = locator.get("excerpt_sha256")
        if excerpt_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(excerpt_hash)):
            raise NovelSourceCatalogError(f"locators[{index}].excerpt_sha256 is invalid")

    publication_allowed = rights.get("publication_allowed") is True or policy.get("publication_allowed") is True
    if rights.get("publication_allowed") is not policy.get("publication_allowed"):
        raise NovelSourceCatalogError("rights and adaptation publication flags must match")
    if publication_allowed:
        if rights["status"] not in {"PUBLIC_DOMAIN_VERIFIED", "LICENSED"}:
            raise NovelSourceCatalogError("publication requires verified public-domain or licensed status")
        if not evidence or not jurisdictions or not territories or review.get("status") != "APPROVED":
            raise NovelSourceCatalogError("publication requires evidence, jurisdiction, territory, and approved human review")
        if not set(regions).issubset(set(territories)):
            raise NovelSourceCatalogError("publication territories must cover every target region")
        if unresolved_contribution:
            raise NovelSourceCatalogError("publication is blocked by unassessed modern contributions")
        if policy.get("script_adaptation_allowed") is not True:
            raise NovelSourceCatalogError("publication requires script adaptation permission")
    elif rights["status"] in {"UNASSESSED", "RESEARCHING", "BLOCKED"} and policy.get("script_adaptation_allowed") is True:
        raise NovelSourceCatalogError("unverified rights cannot enable script adaptation")
    return deepcopy(catalog)


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelSourceCatalogError(f"cannot read source catalog: {error}") from error
    return validate_catalog(payload)


def _save_catalog(project_dir: Path, catalog: dict[str, Any], *, overwrite: bool) -> Path:
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    normalized = validate_catalog(catalog)
    if normalized["project_id"] != project["project_id"] or normalized["ip_id"] != project["ip"]["id"]:
        raise NovelSourceCatalogError("source catalog does not match the novel-anime project")
    output = project_dir / CATALOG_RELATIVE_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise NovelSourceCatalogError(f"refusing to overwrite existing source catalog: {output}")
    descriptor, temp_name = tempfile.mkstemp(prefix=".source-catalog.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, output)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return output


def write_catalog(project_dir: Path, catalog: dict[str, Any]) -> Path:
    return _save_catalog(project_dir, catalog, overwrite=False)


def replace_catalog(project_dir: Path, catalog: dict[str, Any]) -> Path:
    output = Path(project_dir).expanduser().resolve() / CATALOG_RELATIVE_PATH
    if not output.is_file():
        raise NovelSourceCatalogError("cannot replace a source catalog that does not exist")
    return _save_catalog(project_dir, catalog, overwrite=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("project_dir", type=Path)
    create.add_argument("--region", action="append", default=[])
    validate = subparsers.add_parser("validate")
    validate.add_argument("catalog", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            project = load_project(args.project_dir / MANIFEST_NAME)
            catalog = build_catalog(project["project_id"], project["ip"]["id"], project["title"], target_regions=args.region or ["CN"])
            output = write_catalog(args.project_dir, catalog)
            result = {"catalog": str(output), "rights_status": catalog["rights_assessment"]["status"], "publication_allowed": False}
        else:
            catalog = load_catalog(args.catalog)
            result = {"project_id": catalog["project_id"], "editions": len(catalog["editions"]), "chapters": len(catalog["chapters"]), "publication_allowed": catalog["rights_assessment"]["publication_allowed"]}
    except (NovelSourceCatalogError, NovelAnimeProjectError, OSError) as error:
        print(f"novel_source_catalog: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
