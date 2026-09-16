# VideoCreator Engine

以小说 IP 为源头的国风动漫剧集生产系统。系统覆盖底本与权利、故事圣经、季度和单集编剧、角色与场景资产、分镜、配音、动态镜头、剪辑、质量检查和人工发布审核。

## Current status

当前正在从早期的单条知识短视频架构迁移到连续剧情国漫架构。任务状态与执行顺序以 [`VIDEO-CREATOR-TASK.md`](VIDEO-CREATOR-TASK.md) 为唯一依据，完整的系统分层、数据模型和 P18～P28 路线见 [`docs/NOVEL-ANIME-SYSTEM.md`](docs/NOVEL-ANIME-SYSTEM.md)。现有《镜花缘》五集是本地 animatic 技术样片，正式五集将在新数据模型和连续性工作流完成后重新验收。

P18 小说国漫项目使用稳定的 IP、剧集、季、集、场、镜头、资产和渲染 ID。创建并校验一季五集的项目骨架：

```bash
python3 scripts/novel_anime_project.py create projects/jinghua-yuan-series --project-id jinghua-yuan-series --ip-code JHY --title 镜花缘 --episodes 5
python3 scripts/novel_anime_project.py validate projects/jinghua-yuan-series/novel-anime-project.json
```

Web 控制台的“国漫项目”页面读取同一份 `novel-anime-project.json`，不维护独立副本。

初始化项目仓库、记录资产版本、保存里程碑并检查上游变更影响：

```bash
python3 scripts/novel_anime_repository.py init projects/jinghua-yuan-series
python3 scripts/novel_anime_repository.py register-asset projects/jinghua-yuan-series --asset-id AST-CHR-TXS-PORTRAIT --type character --path projects/jinghua-yuan-series/assets/characters/tang-xiaoshan/portrait-v1.png --source IP-JHY
python3 scripts/novel_anime_repository.py snapshot projects/jinghua-yuan-series --label p18-core-model
python3 scripts/novel_anime_repository.py impact projects/jinghua-yuan-series IP-JHY
```

SQLite 保存可查询实体、依赖和资产版本，JSON 快照保留可审阅里程碑；“国漫项目”页面显示仓库统计并能直接运行 IP 影响分析。

初始化持久化任务队列、执行一次本地任务、安排局部重跑或迁移旧技术样片：

```bash
python3 scripts/novel_anime_runtime.py init projects/jinghua-yuan-series
python3 scripts/novel_anime_runtime.py submit projects/jinghua-yuan-series --type VALIDATE_PROJECT --target jinghua-yuan-series --idempotency-key validate-v1
python3 scripts/novel_anime_runtime.py work-once projects/jinghua-yuan-series --worker local-worker
python3 scripts/novel_anime_runtime.py rerun projects/jinghua-yuan-series --root S01E001 --reason "episode outline changed"
python3 scripts/novel_anime_runtime.py migrate-legacy projects/jinghua-yuan-series --source projects/jinghua-yuan-local-pilot
```

任务队列使用实体锁防止同一目标并发写入，支持幂等提交、失败重试、取消和租约过期恢复。状态迁移必须按顺序并具有对应人工审核门；旧五集迁移后只登记为 `publication_allowed=false` 的参考资产。

创建和校验底本、章节定位与权利目录：

```bash
python3 scripts/novel_source_catalog.py create projects/jinghua-yuan-series --region CN
python3 scripts/novel_source_catalog.py validate projects/jinghua-yuan-series/sources/source-catalog.json
```

新目录默认 `UNASSESSED`，只允许本地技术测试，禁止正式剧本改编和发布。只有指定底本、目标地区、来源证据、现代校注/插图处理和人工审核同时通过，才允许进入 `SOURCE_READY`。

对已登记且通过权利审核的 UTF-8 底本执行章节切分和本地候选抽取：

```bash
python3 scripts/novel_source_ingest.py projects/jinghua-yuan-series --edition-id SRC-JHY-001 --source-file /path/to/authorized-source.txt --lexicon-file /path/to/lexicon.json --authorization-confirmed
```

导入产物只保留文件与章节哈希、行号、提及次数和待人工确认的事件候选，不复制小说全文。`--test-only` 只用于合成文本技术测试，不会把章节写入正式底本目录或核心项目；《镜花缘》当前尚未登记核验底本，因此正式原文保持未导入。

创建故事圣经、九类知识文件和连续性基线，并读取下一集写作所需的上一集结束状态：

```bash
python3 scripts/novel_story_bible.py create projects/jinghua-yuan-series
python3 scripts/novel_story_bible.py validate projects/jinghua-yuan-series
python3 scripts/novel_story_bible.py continuity-input projects/jinghua-yuan-series --episode-id S01E001
python3 scripts/novel_story_bible.py record-snapshot projects/jinghua-yuan-series --snapshot-file /path/to/S01E001-end.json
```

人物、关系、地点、道具、规则、时间线和伏笔必须指向已登记章节/定位，或明确标记为原创增补并说明原因。连续性快照记录位置、服装、携带物、伤势、知识、关系、道具归属和未回收伏笔；后续单集若缺少上一集结束快照，系统会阻止继续写作。

创建全剧、季度和角色成长弧规划骨架：

```bash
python3 scripts/novel_series_plan.py create projects/jinghua-yuan-series
python3 scripts/novel_series_plan.py validate projects/jinghua-yuan-series
```

规划文件固定引用当前故事圣经修订号；故事圣经变化后，旧规划会被标记为过期。全剧和季度规划必须覆盖项目中的全部季与集，主要转折和角色弧里程碑必须位于对应季度，并追溯到来源章节、故事圣经实体或明确的原创增补。

创建故事弧和每集一张的单集卡骨架：

```bash
python3 scripts/novel_episode_planning.py create projects/jinghua-yuan-series
python3 scripts/novel_episode_planning.py validate projects/jinghua-yuan-series
```

故事弧必须覆盖同一季度内连续规划的 3～8 集。就绪的单集卡必须包含开场钩子、目标、阻碍、转折、高潮和结尾钩子，并至少具有可追溯的 `HOOK` 与 `ENDING_HOOK` 节拍；故事弧与单集归属会同步到核心项目 manifest。

创建五集场景剧本和 continuity delta 文件，并预览某集结束状态：

```bash
python3 scripts/novel_episode_script.py create projects/jinghua-yuan-series
python3 scripts/novel_episode_script.py validate projects/jinghua-yuan-series
python3 scripts/novel_episode_script.py preview-delta projects/jinghua-yuan-series --episode-id S01E001
```

剧本单元明确区分动作、对白、旁白、声效和画面信息；对白必须绑定场内角色与表演情绪，旁白必须带情绪但不冒充角色，声效必须带触发时机和混音提示。continuity delta 记录位置、服装、携带物、伤势、知识、情绪、关系、道具、伏笔与时间线变化；前一集快照缺失时，后续剧本不能进入 READY。

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

## Novel adaptation pilot

The novel path is separate from the six-section factual explainer flow. Build a rights-aware candidate pool from a dated catalog with:

```bash
python3 scripts/novel_candidate_pool.py validation/novel-candidate-catalog.json --output-dir projects/novel-candidate-pool-20260916
```

The bundle contains the normalized trend snapshot, P16 topic pool, novel candidate JSON, and a human-readable review report. Rank positions are normalized only within their own chart; raw reader counts and ambiguous rankings remain evidence and do not enter the numeric pool. Unknown adaptation rights block the adaptation gate, and the tool never selects a main IP automatically.

The current catalog is refreshed from public pages as a reviewed JSON snapshot; the command automates normalization, ranking, and rights filtering after import. It does not crawl novel sites or claim live platform API access.

Compare the current P16 topic pool with the public-domain work catalog and current longitudinal snapshot inventory with:

```bash
python3 scripts/novel_ip_match.py projects/novel-candidate-pool-20260916/topic-pool.json --output-dir projects/p17-03
```

The report is a human decision aid only. It does not select or clear an IP for production. `validation/rank-snapshot-coverage.json` currently has three continuous Qidian monthly rank records, two adjacent but differently routed Fanqie daily pages, and one current Jinjiang month chart; P17-03 stays incomplete until the required same-chart three-period evidence is available. The classic-work catalog records the Mainland term basis and specific historic text-source evidence separately from modern annotations and later adaptations.

Run a test-only story adaptation through script, storyboard, cards, silent animatic, and rights review with:

```bash
python3 scripts/novel_adaptation.py validation/fiction-workflow-pilot.json --output-dir projects/fiction-workflow-pilot-20260916
```

The current fixture uses `聊斋志异·种梨` only to test the workflow. Its silent 540×960 output is a storyboard preview, not a finished animation; publication remains disabled and a human must review source rights and the adaptation.

Record resolved project assets with `./video-creator assets <project-id> --input-file <asset-manifest-input.json>`. The command validates scene IDs and project-local files, requires source/license/provider metadata, calculates SHA-256 checksums, and writes `asset-manifest.json`.

## Pinned dependencies

External dependencies are declared in [`dependency-manifest.json`](dependency-manifest.json) with an immutable full commit SHA and a release tag when one exists. Install and verify the pinned HyperFrames checkout with:

```bash
python3 scripts/dependency_manager.py install hyperframes
python3 scripts/dependency_manager.py verify hyperframes
```

The checkout lives under the ignored `.dependencies/` directory. Dependency upgrades are manual changes to the manifest and must update the tag and commit together.

Dependencies without a release tag declare their tracked branch for provenance and still install from the immutable full commit SHA. Install the pinned video-use checkout with `python3 scripts/dependency_manager.py install video-use`; its Python environment is managed inside that ignored checkout.

HyperFrames motion defaults live in [`config/hyperframes-motion.json`](config/hyperframes-motion.json). They provide seekable GSAP patterns at 30 fps for titles, data, comparison tables, UI states, cards, prices, rankings, steps, flowcharts, and emphasis text. `scripts.hyperframes_motion.build_motion_plan` turns typed elements into a deterministic renderer plan and rejects unsupported element types.

Six HyperFrames style presets live under [`brand/motion/`](brand/motion/): `minimal`, `tech`, `review`, `warning`, `comparison`, and `tutorial`. Each preset fixes its palette, Chinese typography stack, surface treatment, motion timing scale, and scene transition. Apply one with `scripts.hyperframes_motion.apply_style_preset`; the function returns a styled copy and leaves the base motion plan unchanged.

## Voice providers

TTS adapters implement `synthesize(text, voice, speed, emotion)` from [`adapters/tts/base.py`](adapters/tts/base.py). Fish Audio is the primary provider; ElevenLabs, EdgeTTS, and local synthesis are the ordered fallbacks declared in `config/providers.yaml`. The Fish Audio adapter uses S2-Pro, MP3 output, provider voice IDs, speed controls, and inline emotion cues. It reads credentials only from `FISH_AUDIO_API_KEY` unless a credential is injected by the caller.

Wrap a provider with `adapters.tts.CachedTTS` to reuse generated voice audio. Cache keys include normalized text, voice, speed, provider, and the sound-affecting emotion variant. A per-key file lock and a second lookup after locking ensure concurrent requests cannot trigger duplicate billable synthesis. Audio and metadata checksums are verified on every hit; a corrupt entry fails explicitly instead of silently generating and charging again.

Chinese narration rules live in [`config/zh-voice.json`](config/zh-voice.json). `adapters.tts.optimize_chinese_speech` normalizes cardinal numbers, years, percentages, currency, English initials, product names, and Chinese/English boundaries. Authors can mark `{pause:short}`, `{pause:long}`, and `**emphasis**`; the optimizer emits Fish Audio S2-Pro cues or a punctuation-only fallback before the text reaches the voice cache.

## Image-to-video providers

The provider-neutral image-to-video boundary is implemented in [`adapters/video_generation/`](adapters/video_generation/). OpenAI Sora (`sora-2`/`sora-2-pro`) is the selected remote route for the current pilot; Runway and fal.ai Wan remain replaceable paid routes, while `local_ken_burns` stays available for no-network workflow checks. Remote adapters require an explicit environment key and never upload a frame without one.

Use the local workflow without a key:

```bash
python3 scripts/video_generate.py <frame-1.png> <frame-2.png> --provider local_ken_burns --output /tmp/animatic.mp4
```

Run the current story pilot end to end with local keyframes, the local Tingting voice, and the SRT captions:

```bash
python3 scripts/local_storyboard_pipeline.py projects/jinghua-yuan-local-pilot --output /tmp/tang-xiaoshan-local-storyboard-final.mp4
```

This produces a 1080×1920 H.264/AAC MP4 without a network call. The local provider uses deterministic Ken Burns motion and crossfades; it validates story timing and audio/subtitle wiring, but it does not create new character movement.

Render the first five connected 《镜花缘》 pilot episodes with the shared 唐小山 character, local Chinese voice, SRT captions, and local storyboard motion:

```bash
python3 scripts/jinghua_yuan_episode_batch.py projects/jinghua-yuan-local-pilot --episode-count 5
```

Each episode is written under `projects/jinghua-yuan-local-pilot/episodes/episode-01` through `episode-05` with `script.md`, `storyboard.md`, `assets/scenes/`, `voice/narration.wav`, `subtitles.srt`, `episode.json`, and `final.mp4`. The web console exposes the five manifests as clickable local preview cards. The narration is original pilot text and the files remain local review material until a human completes source, rights, and publication checks.

Use OpenAI for an explicit image-to-video run after setting `OPENAI_API_KEY`:

```bash
python3 scripts/video_generate.py <frame.png> --provider openai_sora --model sora-2 --shot-duration 4 --output /tmp/sora.mp4 --prompt "国风动漫人物轻轻转身，衣袂随风，保持角色设计一致"
```

The OpenAI Videos API is currently documented for `sora-2` and `sora-2-pro`, but the official reference marks it deprecated and schedules shutdown for September 24, 2026. It is therefore used here for short-lived pilot validation behind an adapter, with Runway and Wan retained for later migration.

## Local web console

The same adapters are available through a dependency-free local web console. Start it with:

```bash
python3 scripts/web_server.py --port 8765
```

Open `http://127.0.0.1:8765`. The console lists projects and local reference frames, shows which Provider keys are configured, and the **生成 Provider** menu lets you enter a key for the current server session. Session keys are held in memory only; use `OPENAI_API_KEY`, `RUNWAY_API_KEY`, or `FAL_KEY` when persistent local configuration is preferred. The workspace has both single-shot generation and **生成完整本地分镜** (three scenes plus local voice and captions), plus clickable cards for the five rendered pilot episodes; remote generation still requires an explicit confirmation, and the console previews the generated MP4 without publishing content.

## video-use editing core

The pinned video-use checkout provides source inspection, transcript packing, EDL rendering, subtitles, overlays, grading, and timeline review. Install it with `python3 scripts/dependency_manager.py install video-use`, then create its isolated environment with `uv sync --project .dependencies/video-use`. If `ffprobe` is not already on `PATH`, `python3 scripts/install_media_tools.py install ffprobe` installs the version and archive checksum pinned in [`media-tool-manifest.json`](media-tool-manifest.json) under `.dependencies/bin/`. [`config/video-use.json`](config/video-use.json) records the nine required editing capabilities and production safeguards. The `adapters.video.video_use` boundary verifies the install, probes sources, validates EDL timing and files, builds render commands, and selects self-evaluation windows around every cut.

video-use transcription is routed through the provider-neutral [`adapters/asr/`](adapters/asr/) boundary. ElevenLabs, Whisper API, Local Whisper, and custom providers normalize to the same verbatim word-timestamp format consumed by video-use. Cloud providers expose `uploads_media=true` and the bridge refuses to call them without explicit media-upload authorization. Transcript caches bind the source checksum, provider, language, and speaker count so a changed source cannot reuse stale timestamps.

Traceable edit decisions are stored at `edit/edit-decision-list.json` by [`scripts/edit_decision_list.py`](scripts/edit_decision_list.py). Every kept range has a stable decision ID and reason; source checksums and a render fingerprint bind decisions to their inputs. Each create, range update, and rollback writes an immutable numbered snapshot under `edit/edl-history/`. Updates use an expected revision to reject stale changes, and rollback restores old content as a new revision so the audit trail remains complete.

```bash
python3 scripts/edit_decision_list.py --edit-dir <project>/edit <project-id> create --input-file <edl-input.json>
python3 scripts/edit_decision_list.py --edit-dir <project>/edit <project-id> update-range EDL002 --patch-file <patch.json> --expected-revision 1
python3 scripts/edit_decision_list.py --edit-dir <project>/edit <project-id> rollback 1 --expected-revision 2
python3 scripts/edit_decision_list.py --edit-dir <project>/edit <project-id> rerender-plan
```

The FFmpeg final merge boundary is implemented in [`adapters/video/ffmpeg_finalizer.py`](adapters/video/ffmpeg_finalizer.py). A `FinalMergeSpec` explicitly declares video inputs, audio tracks with volume and delay, transition, geometry, frame rate, codecs, bitrates, container, and output path. The command builder scales and pads each video, concatenates or crossfades clips, mixes delayed tracks, normalizes to -14 LUFS, encodes, and writes a fast-start MP4 without invoking a shell.

The default delivery standard in [`config/ffmpeg-finalizer.json`](config/ffmpeg-finalizer.json) is 1080×1920 at 30 fps with H.264 video, AAC audio, and an MP4 container. `default_final_merge_spec` creates this exact specification, while `run_standard_final_merge` probes the rendered file and verifies its real streams, geometry, frame rate, container, duration, and size before reporting PASS.

## Quality control

Run `python3 scripts/technical_qc.py <project-dir>` after rendering. It probes the real video and audio streams, fully decodes the file while detecting black and frozen frames, silence, and clipping, compares audio/video timing, and validates normalized subtitle boxes against the configured safe area and WeChat UI zones. Evidence is stored in `qc/technical-qc.json`; missing layout evidence and failed checks remain explicit failures.

Run content review with `python3 scripts/content_qc.py <project-dir> --assessment-file <content-qc-input.json>`. The assessment must provide a decision and evidence for every required criterion, with known research source IDs for cited facts. Deterministic checks can still reject duplicate narration, unsupported absolute claims, sensitive phrases, or missing Hook, conclusion, and CTA. The report is written to `qc/content-qc.json`.

Run visual review with `python3 scripts/visual_qc.py <project-dir> --analysis-file <visual-qc-analysis.json>`. The analysis must cover every rendered scene with a visual fingerprint, empty-space ratio, crop result, minimum text contrast, and normalized key-information boxes. The report combines that evidence with storyboard timing and captions to detect all seven configured visual defects.

`scripts/auto_fix.py` enforces the automatic-fix boundary before dispatch. Low-risk presentation fixes can reach a replaceable executor; fact, conclusion, recommendation, and sensitive-content changes route the whole batch back to script review. Any applied fix invalidates prior QC. Finalization aggregates the three fresh PASS reports into `qc.json` and `qc-report.md`, then advances an `EDITED` project to `QC_PASS`.

## Publishing package

`./video-creator package <project-id>` accepts only a `QC_PASS` project with a passing aggregate report. It validates and copies the seven required deliverables into `publish-package/`, verifies every copied SHA-256, writes `package.json`, and advances the project to `PACKAGED`. Packaging never uploads or publishes content.

Cover input contains two or three short question-led candidates. `scripts/cover_candidates.py create` renders 1080×1920 PNG previews with a minimum mobile-readable core font size and rejects dense supporting copy. `select` verifies the candidate checksum before copying the chosen image to `cover.png`.

`scripts/publication_copy.py` requires at least one search, conflict, and result title. It validates type-specific wording, blocks unsupported hype, scores every candidate, records one recommended title with reasons, and writes `title.md`, `caption.md`, `hashtags.md`, and `publication-copy.json`.

## Human review gate

`python3 scripts/review_gate.py <project-dir> <project-id>` re-hashes all seven packaged deliverables, confirms aggregate QC PASS and the human-only publish mode, writes `review-gate.json`, and advances `PACKAGED` to `READY_FOR_REVIEW`. The command then displays the final checklist and stops at `WAITING FOR HUMAN PUBLISH`.

`python3 scripts/publish_policy.py audit` verifies the V1 human-only policy across application, platform, and package configuration. Uploading to WeChat, simulating a publish click, and setting originality or commercial labels are denied capabilities. The manual-record command changes state only after explicit user confirmation that publication already happened outside VideoCreator.

## Pilot production validation

P14 pilot videos can use the credential-free `MacOSSayTTS` adapter with the local `Tingting` voice. `python3 scripts/pilot_producer.py` renders the declared five-topic batch through real FFmpeg output, all three QC layers, cover and copy generation, packaging, and the human review gate without publishing. `python3 scripts/pilot_validation.py` then independently reopens all five projects, media streams, checksums, QC reports, and packages before accepting the milestone.

## Logs

Run a task command through `scripts/run_task.py` to keep the terminal summary compact and capture detailed output under the ignored `logs/` directory:

```bash
python3 scripts/run_task.py --task P1-01 --next P1-02 -- <command> [arguments...]
```

The terminal prints `RUN`, `PASS` or `FAIL`, `RESULT`, and `NEXT`. Log lines use UTC timestamps; common credential assignments and Bearer tokens are redacted. Do not print secrets in command output.

## Project layout

The directories under `skill/`, `adapters/`, `templates/`, `brand/`, `config/`, and `projects/` reserve the boundaries described in the task specification. Empty directories are retained with `.gitkeep` until their corresponding task adds implementation files.
