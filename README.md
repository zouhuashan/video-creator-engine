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

Copy `.env.example` to `.env` when provider configuration is introduced. Keep real secrets out of Git.

## Project layout

The directories under `skill/`, `adapters/`, `templates/`, `brand/`, `config/`, and `projects/` reserve the boundaries described in the task specification. Empty directories are retained with `.gitkeep` until their corresponding task adds implementation files.
