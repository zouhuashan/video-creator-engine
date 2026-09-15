#!/usr/bin/env python3
"""Audit and enforce the V1 human-only publication boundary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .project_state import StateError, load_run_state, transition_project
except ImportError:
    from project_state import StateError, load_run_state, transition_project

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "publishing-policy.json"
APP_PATH = ROOT / "config" / "app.yaml"
PLATFORM_PATH = ROOT / "config" / "platforms.yaml"
PACKAGING_PATH = ROOT / "config" / "packaging.json"


class PublishPolicyError(ValueError):
    """Raised when publication policy is violated or incomplete."""


def _policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishPolicyError(f"invalid publishing policy: {error}") from error
    required = {"wechat_auto_upload", "simulate_publish_click", "automatic_originality_declaration", "automatic_commercial_label"}
    if (
        value.get("schema_version") != 1 or value.get("version") != "V1"
        or value.get("mode") != "human_only" or set(value.get("forbidden_actions", [])) != required
        or value.get("allowed_action") != "record_confirmed_manual_publication"
    ):
        raise PublishPolicyError("publishing policy does not enforce the complete V1 boundary")
    return value


def authorize_publish_action(action: str) -> bool:
    policy = _policy()
    if action in policy["forbidden_actions"]:
        raise PublishPolicyError(f"V1 forbids publication action: {action}")
    if action != policy["allowed_action"]:
        raise PublishPolicyError(f"unknown publication action: {action}")
    return True


def audit_publish_configuration() -> dict[str, Any]:
    policy = _policy()
    try:
        app = APP_PATH.read_text(encoding="utf-8")
        platforms = PLATFORM_PATH.read_text(encoding="utf-8")
        packaging = json.loads(PACKAGING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishPolicyError(f"cannot audit publication configuration: {error}") from error
    checks = {
        "app_auto_publish_disabled": "  auto_publish: false" in app,
        "app_human_confirmation_required": "  require_human_publish_confirmation: true" in app,
        "platform_publish_mode_human": "    publish_mode: human_confirmation" in platforms,
        "package_auto_publish_disabled": packaging.get("auto_publish") is False,
        "package_publish_mode_human": packaging.get("publish_mode") == "human_confirmation",
        "all_forbidden_actions_declared": len(policy["forbidden_actions"]) == 4,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise PublishPolicyError(f"publication configuration audit failed: {', '.join(failed)}")
    return {"schema_version": 1, "status": "PASS", "mode": "human_only", "checks": checks}


def record_confirmed_manual_publication(
    directory: Path, project_id: str, *, confirmed_by_user: bool, confirmation_note: str
) -> dict[str, Any]:
    authorize_publish_action("record_confirmed_manual_publication")
    audit_publish_configuration()
    state = load_run_state(directory, project_id)
    if state["status"] != "READY_FOR_REVIEW":
        raise StateError(f"manual publication record requires status READY_FOR_REVIEW; current status is {state['status']}")
    if confirmed_by_user is not True:
        raise PublishPolicyError("explicit user confirmation of completed manual publication is required")
    if not isinstance(confirmation_note, str) or not confirmation_note.strip():
        raise PublishPolicyError("manual publication confirmation requires a non-empty note")
    return transition_project(
        directory, project_id, "PUBLISHED_MANUALLY", note=confirmation_note.strip(),
        record_manual_publication=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    record = subparsers.add_parser("record-manual")
    record.add_argument("project_dir", type=Path)
    record.add_argument("project_id")
    record.add_argument("--confirmed-by-user", action="store_true")
    record.add_argument("--note", required=True)
    args = parser.parse_args()
    try:
        result = audit_publish_configuration() if args.command == "audit" else record_confirmed_manual_publication(
            args.project_dir, args.project_id, confirmed_by_user=args.confirmed_by_user, confirmation_note=args.note
        )
    except (PublishPolicyError, StateError) as error:
        print(f"publish_policy: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
