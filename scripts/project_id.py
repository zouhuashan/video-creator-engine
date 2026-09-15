#!/usr/bin/env python3
"""Create a unique YYYYMMDD-slug project ID and its directory."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__:
    from .project_state import initialize_run_state
else:
    from project_state import initialize_run_state


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "app.yaml"
MAX_SLUG_LENGTH = 64


def config_scalar(section: str, key: str) -> str:
    """Read a simple scalar from a top-level config section, without dependencies."""
    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    in_section = False
    value_pattern = re.compile(r"^  ([A-Za-z0-9_]+):\s*(.*?)\s*(?:#.*)?$")

    for line in lines:
        if not line[:1].isspace():
            if in_section:
                break
            in_section = line.strip() == f"{section}:"
            continue
        if not in_section:
            continue
        match = value_pattern.match(line)
        if match and match.group(1) == key:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                return value
            break

    raise ValueError(f"missing config value {section}.{key} in {CONFIG_PATH}")


def normalize_slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-")


def slug_for(topic: str, slug_hint: str | None) -> str:
    candidate = normalize_slug(slug_hint or topic)
    if candidate and re.search(r"[a-z]", candidate):
        return candidate

    canonical_topic = " ".join(unicodedata.normalize("NFKC", topic).split())
    digest = hashlib.sha256(canonical_topic.encode("utf-8")).hexdigest()[:10]
    return f"topic-{digest}"


def date_prefix(date_override: str | None) -> str:
    date_format = config_scalar("project", "date_format")
    if date_override:
        if not re.fullmatch(r"\d{8}", date_override):
            raise ValueError("--date must be a valid date in YYYYMMDD format")
        try:
            parsed = datetime.strptime(date_override, "%Y%m%d")
        except ValueError as error:
            raise ValueError("--date must be a valid date in YYYYMMDD format") from error
        date_value = parsed.strftime(date_format)
    else:
        timezone_name = config_scalar("app", "timezone")
        try:
            now = datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"timezone data unavailable for configured timezone: {timezone_name}") from error
        date_value = now.strftime(date_format)

    if not re.fullmatch(r"\d{8}", date_value):
        raise ValueError("config project.date_format must produce an eight-digit date")
    return date_value


def reserve_project_id(
    topic: str,
    slug_hint: str | None,
    projects_dir: Path,
    date_override: str | None = None,
) -> str:
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty")

    date = date_prefix(date_override)
    slug = slug_for(topic, slug_hint)
    id_format = config_scalar("project", "id_format")
    base_id = id_format.format(date=date, slug=slug)
    if not re.fullmatch(r"\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*", base_id):
        raise ValueError("config project.id_format must produce YYYYMMDD-slug IDs")

    projects_dir.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        candidate = base_id if suffix == 1 else f"{base_id}-{suffix}"
        candidate_dir = projects_dir / candidate
        try:
            candidate_dir.mkdir()
        except FileExistsError:
            suffix += 1
            continue
        try:
            initialize_run_state(candidate_dir, candidate)
        except Exception:
            try:
                candidate_dir.rmdir()
            except OSError:
                pass
            raise
        return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="Video topic")
    parser.add_argument("--slug", help="Short ASCII slug; recommended for non-English topics")
    parser.add_argument("--date", help="Override local project date (YYYYMMDD), mainly for reproducible runs")
    parser.add_argument("--projects-dir", type=Path, default=ROOT / "projects", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        project_id = reserve_project_id(args.topic, args.slug, args.projects_dir, args.date)
    except (OSError, ValueError) as error:
        print(f"project_id: {error}", file=sys.stderr)
        return 1
    print(project_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
