#!/usr/bin/env python3
"""VideoCreator command helpers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .project_state import DEFAULT_PROJECTS_DIR, StateError, project_dir, resume_plan
    from .rerun_planner import rerun_plan
    from .research_module import write_research_artifacts
    from .script_module import write_script_artifacts
    from .storyboard_module import write_storyboard_artifacts
    from .topic_scoring import score_project
else:
    from project_state import DEFAULT_PROJECTS_DIR, StateError, project_dir, resume_plan
    from rerun_planner import rerun_plan
    from research_module import write_research_artifacts
    from script_module import write_script_artifacts
    from storyboard_module import write_storyboard_artifacts
    from topic_scoring import score_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    resume_parser = subparsers.add_parser("resume", help="Find the next incomplete stage for a project")
    resume_parser.add_argument("project_id")
    resume_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    rerun_parser = subparsers.add_parser("rerun", help="Plan a scoped project rerun without changing project state")
    rerun_parser.add_argument("project_id")
    rerun_targets = rerun_parser.add_subparsers(dest="target", required=True)
    scene_parser = rerun_targets.add_parser("scene", help="Rerun one storyboard scene")
    scene_parser.add_argument("scene_id")
    for target in ("voice", "cover", "qc"):
        rerun_targets.add_parser(target, help=f"Rerun {target}")
    rerun_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    research_parser = subparsers.add_parser("research", help="Validate sourced research input and create project reports")
    research_parser.add_argument("project_id")
    research_parser.add_argument("--input-file", type=Path, required=True, help="JSON research brief with source references")
    research_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    score_parser = subparsers.add_parser("score", help="Score a researched topic and write topic.json")
    score_parser.add_argument("project_id")
    score_parser.add_argument("--assessment-file", type=Path, required=True, help="JSON topic ratings with rationales")
    score_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    script_parser = subparsers.add_parser("script", help="Validate a six-section script and write project artifacts")
    script_parser.add_argument("project_id")
    script_parser.add_argument("--input-file", type=Path, required=True, help="JSON script draft following the WeChat Channels template")
    script_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    storyboard_parser = subparsers.add_parser("storyboard", help="Validate a timed storyboard and write project artifacts")
    storyboard_parser.add_argument("project_id")
    storyboard_parser.add_argument("--input-file", type=Path, required=True, help="JSON scene plan aligned to script narration")
    storyboard_parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        directory = project_dir(args.project_id, args.projects_dir)
        if args.command == "resume":
            plan = resume_plan(directory, args.project_id)
        elif args.command == "rerun":
            scene_id = args.scene_id if args.target == "scene" else None
            plan = rerun_plan(directory, args.project_id, args.target, scene_id)
        elif args.command == "research":
            payload = json.loads(args.input_file.read_text(encoding="utf-8"))
            plan = write_research_artifacts(directory, args.project_id, payload)
        elif args.command == "score":
            plan = score_project(args.project_id, args.assessment_file, args.projects_dir)
        elif args.command == "script":
            payload = json.loads(args.input_file.read_text(encoding="utf-8"))
            plan = write_script_artifacts(directory, args.project_id, payload)
        elif args.command == "storyboard":
            payload = json.loads(args.input_file.read_text(encoding="utf-8"))
            plan = write_storyboard_artifacts(directory, args.project_id, payload)
        else:  # pragma: no cover - argparse enforces the available commands
            raise StateError(f"unknown command: {args.command}")
    except (OSError, ValueError, StateError) as error:
        print(f"video-creator: {error}", file=sys.stderr)
        return 1

    print(json.dumps(plan, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
