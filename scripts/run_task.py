#!/usr/bin/env python3
"""Run one task command with a compact terminal summary and a detailed log."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|"
    r"CLIENT[_-]?SECRET|SECRET|PASSWORD|PASSWD|TOKEN)\b\s*[:=]\s*)"
    r'("[^"]*"|\'[^\']*\'|[^\s,;}\]]+)'
)
BEARER_TOKEN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*")


def redact(text: str) -> str:
    def hide_assignment(match: re.Match[str]) -> str:
        value = match.group(2)
        if value.startswith(("\"", "'")) and len(value) >= 2:
            value = f"{value[0]}[REDACTED]{value[0]}"
        else:
            value = "[REDACTED]"
        return match.group(1) + value

    text = SECRET_ASSIGNMENT.sub(hide_assignment, text)
    return BEARER_TOKEN.sub(r"\1[REDACTED]", text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return slug or "task"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="Task identifier or short name")
    parser.add_argument("--next", dest="next_task", default="—", help="Next task identifier")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("provide a command after --")
    return args


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    prefix = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{safe_slug(args.task)}-"
    descriptor, filename = tempfile.mkstemp(prefix=prefix, suffix=".log", dir=log_dir)
    log_path = Path(filename)
    command_name = Path(args.command[0]).name or args.command[0]
    exit_code = 127

    with os.fdopen(descriptor, "w", encoding="utf-8") as log_file:
        log_file.write(f"{utc_now()} level=INFO task={args.task} event=start\n")
        log_file.write(f"{utc_now()} level=INFO command={command_name}\n")
        try:
            process = subprocess.Popen(
                args.command,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                content = redact(line.rstrip("\r\n"))
                log_file.write(f"{utc_now()} level=INFO {content}\n")
            exit_code = process.wait()
        except OSError as error:
            log_file.write(f"{utc_now()} level=ERROR {redact(str(error))}\n")
        except KeyboardInterrupt:
            if "process" in locals() and process.poll() is None:
                process.terminate()
                process.wait()
            exit_code = 130
            log_file.write(f"{utc_now()} level=ERROR interrupted\n")
        finally:
            result = "PASS" if exit_code == 0 else "FAIL"
            log_file.write(f"{utc_now()} level=INFO task={args.task} result={result} exit_code={exit_code}\n")

    relative_log = log_path.relative_to(root)
    print(f"RUN {args.task}")
    print("PASS" if exit_code == 0 else "FAIL")
    print(f"RESULT {relative_log.as_posix()}")
    print(f"NEXT {args.next_task}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
