#!/usr/bin/env python3
"""Validate content-review evidence and deterministic script quality rules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "content-qc.json"


class ContentQCError(ValueError):
    """Raised when content QC inputs cannot support a result."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContentQCError(f"invalid {label}: {error}") from error
    if not isinstance(payload, dict):
        raise ContentQCError(f"{label} must be a JSON object")
    return payload


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = _load_json(path, "content QC config")
    if config.get("schema_version") != 1 or len(config.get("required_checks", [])) != 10:
        raise ContentQCError("unsupported or incomplete content QC config")
    return config


def _known_source_ids(research: dict[str, Any]) -> set[str]:
    sources = research.get("sources", [])
    if not isinstance(sources, list):
        raise ContentQCError("research sources must be a list")
    return {item.get("source_id") for item in sources if isinstance(item, dict) and isinstance(item.get("source_id"), str)}


def _assessment_map(assessment: dict[str, Any], required: list[str], sources: set[str]) -> dict[str, dict[str, Any]]:
    if assessment.get("schema_version") != 1 or not isinstance(assessment.get("assessments"), list):
        raise ContentQCError("content assessment must contain schema_version 1 and assessments")
    result: dict[str, dict[str, Any]] = {}
    for item in assessment["assessments"]:
        if not isinstance(item, dict) or set(item) - {"check", "status", "evidence", "source_ids"}:
            raise ContentQCError("each content assessment must contain only supported fields")
        check, status, evidence = item.get("check"), item.get("status"), item.get("evidence")
        if check not in required or check in result:
            raise ContentQCError(f"unknown or duplicate content check: {check}")
        if status not in {"PASS", "FAIL"} or not isinstance(evidence, str) or not evidence.strip():
            raise ContentQCError(f"content check {check} requires PASS/FAIL and evidence")
        source_ids = item.get("source_ids", [])
        if not isinstance(source_ids, list) or any(value not in sources for value in source_ids):
            raise ContentQCError(f"content check {check} cites an unknown source")
        result[check] = {"status": status, "evidence": evidence.strip(), "source_ids": source_ids}
    missing = [name for name in required if name not in result]
    if missing:
        raise ContentQCError(f"content assessment is missing checks: {', '.join(missing)}")
    return result


def _sections(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = script.get("sections")
    if not isinstance(raw, list):
        raise ContentQCError("script sections must be a list")
    sections: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("section"), str):
            raise ContentQCError("script contains an invalid section")
        sections[item["section"]] = item
    return sections


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def evaluate_content_qc(
    script: dict[str, Any], research: dict[str, Any], assessment: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = config or load_config()
    required = active["required_checks"]
    sources = _known_source_ids(research)
    reviews = _assessment_map(assessment, required, sources)
    sections = _sections(script)
    narrations = [str(item.get("narration", "")).strip() for item in script["sections"]]
    normalized = [_normalized(text) for text in narrations if text]
    duplicates = sorted({text for text in normalized if normalized.count(text) > 1})
    absolute_hits = [
        {"section": item.get("section"), "term": term}
        for item in script["sections"] for term in active["absolute_claim_patterns"]
        if term.casefold() in str(item.get("narration", "")).casefold() and not item.get("source_ids")
    ]
    sensitive_hits = [
        {"section": item.get("section"), "term": term}
        for item in script["sections"] for term in active["platform_sensitive_patterns"]
        if term.casefold() in str(item.get("narration", "")).casefold()
    ]
    hook = sections.get("hook", {})
    conclusion = sections.get("conclusion", {})
    cta = sections.get("cta", {})
    deterministic = {
        "duplicate_content": not duplicates,
        "unsupported_absolute_claims": not absolute_hits,
        "first_three_seconds_hook": bool(str(hook.get("narration", "")).strip()),
        "conclusion_clarity": bool(str(conclusion.get("narration", "")).strip()),
        "call_to_action": bool(str(cta.get("narration", "")).strip()),
        "platform_sensitive_language": not sensitive_hits,
    }
    checks = {
        name: reviews[name]["status"] == "PASS" and deterministic.get(name, True)
        for name in required
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "review_evidence": reviews,
        "automated_evidence": {
            "duplicate_narrations": duplicates,
            "unsupported_absolute_claims": absolute_hits,
            "platform_sensitive_language_hits": sensitive_hits,
            "hook_text": str(hook.get("narration", "")).strip(),
            "conclusion_text": str(conclusion.get("narration", "")).strip(),
            "cta_text": str(cta.get("narration", "")).strip(),
        },
    }


def run_project_content_qc(project_dir: Path, assessment_file: Path) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    report = evaluate_content_qc(
        _load_json(directory / "script.json", "script.json"),
        _load_json(directory / "research.json", "research.json"),
        _load_json(assessment_file, "content QC assessment"),
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    output = directory / "qc" / "content-qc.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["output"] = str(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--assessment-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_project_content_qc(args.project_dir, args.assessment_file)
    except ContentQCError as error:
        print(f"content_qc: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
