#!/usr/bin/env python3
"""VideoCreator command helpers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .project_state import DEFAULT_PROJECTS_DIR, StateError, project_dir, resume_plan
else:
    from project_state import DEFAULT_PROJECTS_DIR, StateError, project_dir, resume_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    resume_parser = subparsers.add_parser("resume", help="Find the next incomplete stage for a project")
    resume_parser.add_argument("project_id")
    resume_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        directory = project_dir(args.project_id, args.projects_dir)
        plan = resume_plan(directory, args.project_id)
    except (OSError, StateError) as error:
        print(f"video-creator: {error}", file=sys.stderr)
        return 1

    print(json.dumps(plan, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
