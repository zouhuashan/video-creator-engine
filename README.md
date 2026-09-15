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

Inspect the resume checkpoint with:

```bash
./video-creator resume <project-id>
```

The command reads `run.json` and prints a machine-readable checkpoint. In a Codex `video-creator` session, the Skill uses that checkpoint to continue with the matching implemented stage; `READY_FOR_REVIEW` waits for a human, and `PUBLISHED_MANUALLY` is terminal.

Inspect the scope for a local rerun with:

```bash
./video-creator rerun <project-id> scene SC007
./video-creator rerun <project-id> voice
./video-creator rerun <project-id> cover
./video-creator rerun <project-id> qc
```

These commands validate the target and print a machine-readable plan with preserved outputs, rebuilt outputs, and the recovery checkpoint. They do not modify `run.json` or execute production stages; rerun executors are not wired yet.

Create research artifacts from a source-backed JSON brief with:

```bash
./video-creator research <project-id> --input-file <research-input.json>
```

The brief format is described by [`templates/research-input.schema.json`](templates/research-input.schema.json). The command validates each claim's source references and source tier, orders citations by `official > primary_document > authoritative_media > high_quality_community > search_summary`, writes `research.json`, `research.md`, and `sources.md`, then advances the project from `CREATED` to `RESEARCHED`. Search summaries are discovery leads only and cannot support factual claims by themselves. Search-provider adapters are not configured yet, so the VideoCreator Skill gathers and verifies source material before calling this command.

Score a researched topic with:

```bash
./video-creator score <project-id> --assessment-file <topic-assessment.json>
```

The assessment format is described by [`templates/topic-assessment.schema.json`](templates/topic-assessment.schema.json), and weights, evidence scores, risk levels, and gates are configured in [`config/topic-scoring.json`](config/topic-scoring.json). The command writes `topic.json` without advancing the project lifecycle. Low total scores and high risk scores independently block automatic production.

After the topic gate passes, write a six-section WeChat Channels script with:

```bash
./video-creator script <project-id> --input-file <script-input.json>
```

The input format is described by [`templates/script-input.schema.json`](templates/script-input.schema.json), with section guidance in [`templates/wechat-channel/script-template.md`](templates/wechat-channel/script-template.md). Style rules and duration estimates are configured in [`config/script-style.json`](config/script-style.json) and [`config/script-duration.json`](config/script-duration.json). The command reports `estimated_duration` in seconds, `word_count` (Han characters plus Latin/number tokens), and the assumed `speech_rate`. If the draft is over target, it removes explicitly marked optional sentences in order; if that is insufficient, the Script Skill rewrites the narration and retries. Only a script that fits the target and passes style and source checks advances the project to `SCRIPTED`.

Create a timed storyboard from a completed script with:

```bash
./video-creator storyboard <project-id> --input-file <storyboard-input.json>
```

The input format is described by [`templates/storyboard-input.schema.json`](templates/storyboard-input.schema.json). Each scene includes timing, spoken text, caption, visual direction, asset query, motion, transition, and source IDs. The command checks that scene timing is continuous, narration covers the script exactly, and cited sources have an evidence visual before writing `storyboard.json` and `storyboard.md` and advancing the project to `STORYBOARDED`.

Review the storyboard before asset work with `./video-creator review-storyboard <project-id>`. It writes `storyboard-review.json` and `storyboard-review.md` with checks for visual pacing, repeated visuals, text-only runs, evidence visuals, Hook matching, and conclusion emphasis. A failed review remains reviewable and does not advance project state.

Record resolved project assets with `./video-creator assets <project-id> --input-file <asset-manifest-input.json>`. The command validates scene IDs and project-local files, requires source/license/provider metadata, calculates SHA-256 checksums, and writes `asset-manifest.json`.

## Pinned dependencies

External rendering dependencies are declared in [`dependency-manifest.json`](dependency-manifest.json) with both an immutable Git tag and full commit SHA. Install and verify the pinned HyperFrames checkout with:

```bash
python3 scripts/dependency_manager.py install hyperframes
python3 scripts/dependency_manager.py verify hyperframes
```

The checkout lives under the ignored `.dependencies/` directory. Dependency upgrades are manual changes to the manifest and must update the tag and commit together.

HyperFrames motion defaults live in [`config/hyperframes-motion.json`](config/hyperframes-motion.json). They provide seekable GSAP patterns at 30 fps for titles, data, comparison tables, UI states, cards, prices, rankings, steps, flowcharts, and emphasis text. `scripts.hyperframes_motion.build_motion_plan` turns typed elements into a deterministic renderer plan and rejects unsupported element types.

Six HyperFrames style presets live under [`brand/motion/`](brand/motion/): `minimal`, `tech`, `review`, `warning`, `comparison`, and `tutorial`. Each preset fixes its palette, Chinese typography stack, surface treatment, motion timing scale, and scene transition. Apply one with `scripts.hyperframes_motion.apply_style_preset`; the function returns a styled copy and leaves the base motion plan unchanged.

## Voice providers

TTS adapters implement `synthesize(text, voice, speed, emotion)` from [`adapters/tts/base.py`](adapters/tts/base.py). Fish Audio is the primary provider; ElevenLabs, EdgeTTS, and local synthesis are the ordered fallbacks declared in `config/providers.yaml`. The Fish Audio adapter uses S2-Pro, MP3 output, provider voice IDs, speed controls, and inline emotion cues. It reads credentials only from `FISH_AUDIO_API_KEY` unless a credential is injected by the caller.

Wrap a provider with `adapters.tts.CachedTTS` to reuse generated voice audio. Cache keys include normalized text, voice, speed, provider, and the sound-affecting emotion variant. A per-key file lock and a second lookup after locking ensure concurrent requests cannot trigger duplicate billable synthesis. Audio and metadata checksums are verified on every hit; a corrupt entry fails explicitly instead of silently generating and charging again.

Chinese narration rules live in [`config/zh-voice.json`](config/zh-voice.json). `adapters.tts.optimize_chinese_speech` normalizes cardinal numbers, years, percentages, currency, English initials, product names, and Chinese/English boundaries. Authors can mark `{pause:short}`, `{pause:long}`, and `**emphasis**`; the optimizer emits Fish Audio S2-Pro cues or a punctuation-only fallback before the text reaches the voice cache.

## Logs

Run a task command through `scripts/run_task.py` to keep the terminal summary compact and capture detailed output under the ignored `logs/` directory:

```bash
python3 scripts/run_task.py --task P1-01 --next P1-02 -- <command> [arguments...]
```

The terminal prints `RUN`, `PASS` or `FAIL`, `RESULT`, and `NEXT`. Log lines use UTC timestamps; common credential assignments and Bearer tokens are redacted. Do not print secrets in command output.

## Project layout

The directories under `skill/`, `adapters/`, `templates/`, `brand/`, `config/`, and `projects/` reserve the boundaries described in the task specification. Empty directories are retained with `.gitkeep` until their corresponding task adds implementation files.
