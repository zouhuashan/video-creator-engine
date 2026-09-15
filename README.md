# VideoCreator Engine

Codex-driven semi-automated video production for WeChat Channels. The project produces a reviewable publishing package; a human always confirms final publication.

## Current status

The repository is being initialized according to [`VIDEO-CREATOR-TASK.md`](VIDEO-CREATOR-TASK.md). The task file is the source of truth; work proceeds in its listed order.

## Environment

Pinned local tool versions:

- Python 3.10.2 (`.python-version`)
- Node.js 22.23.1 (`.nvmrc`)
- FFmpeg 9.0 (`.ffmpeg-version`)
- Codex CLI must be installed and runnable

Check the environment with:

```bash
./scripts/check-env.sh
```

Copy `.env.example` to `.env` and enter credentials only for the providers selected in `config/providers.yaml`. Keep real secrets out of Git.

## Configuration

The YAML files in `config/` define application defaults, provider selection, platform output profiles, quality checks, and channel identity. The active profile targets WeChat Channels; other platform profiles remain planned until their specifications are defined.

Create a project directory with a date-prefixed ID:

```bash
python3 scripts/project_id.py --topic "ChatGPT Plus 一个月 20 美元值不值" --slug chatgpt-plus-worth-it
```

The command prints the ID and creates `projects/<project-id>/`. If that ID already exists, it appends a numeric suffix rather than reusing the directory. For Chinese-only topics, pass a short semantic English `--slug`; without one, the helper uses a stable topic hash.

New projects start at `CREATED` in `run.json`. Inspect or advance the state with:

```bash
python3 scripts/project_state.py status <project-id>
python3 scripts/project_state.py transition <project-id> --to RESEARCHED --note "Research validated"
```

Transitions must follow the configured lifecycle in order. Recording `PUBLISHED_MANUALLY` additionally requires `--record-manual-publication` after the user confirms publication.

## Logs

Run a task command through `scripts/run_task.py` to keep the terminal summary compact and capture detailed output under the ignored `logs/` directory:

```bash
python3 scripts/run_task.py --task P1-01 --next P1-02 -- <command> [arguments...]
```

The terminal prints `RUN`, `PASS` or `FAIL`, `RESULT`, and `NEXT`. Log lines use UTC timestamps; common credential assignments and Bearer tokens are redacted. Do not print secrets in command output.

## Project layout

The directories under `skill/`, `adapters/`, `templates/`, `brand/`, `config/`, and `projects/` reserve the boundaries described in the task specification. Empty directories are retained with `.gitkeep` until their corresponding task adds implementation files.
