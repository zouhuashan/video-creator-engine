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

生成剧情与跨集连续性审核报告：

```bash
python3 scripts/novel_story_review.py audit projects/jinghua-yuan-series
python3 scripts/novel_story_review.py validate projects/jinghua-yuan-series
python3 scripts/novel_story_review.py approve projects/jinghua-yuan-series --reviewer <name> --note <review-note>
```

审核覆盖因果链、节奏、人物动机、伏笔设置/回收、跨集状态和来源标记。含阻断项或警告的报告不能批准；报告输入修订过期后也不能批准。`WRITING_READY` 同时要求最新报告为 PASS、人工审核明确通过，并保留运行时 `season_plan` 审核门。

创建国风视觉方向、五集色彩脚本、构图规范和负面约束：

```bash
python3 scripts/novel_visual_bible.py create projects/jinghua-yuan-series
python3 scripts/novel_visual_bible.py validate projects/jinghua-yuan-series
```

视觉圣经默认采用 1080×1920、9:16、30 fps，并独立记录安全区和字幕区。READY 状态要求美术方向、线稿、渲染、材质、角色/环境/动作语言、提示词前缀、五集配色、构图规则和负面约束全部完成并同步审核；引用现成影视设计、未授权参考或现代插图会被禁止。

创建角色身份契约、转面、表情和服装资产目录：

```bash
python3 scripts/novel_character_designs.py create projects/jinghua-yuan-series
python3 scripts/novel_character_designs.py validate projects/jinghua-yuan-series
```

每名故事角色必须有唯一 CharacterDesign，并记录头身比、体型、脸型、肤色、发型、眼型、固定特征、禁改特征和固定配色。READY 角色至少需要正面、侧面、背面、近景以及中性、喜、怒、哀、惊五类已选表情，并具有已登记的默认服装资产；所有子资产携带同一 identity signature，结构化观察偏差会生成具体字段问题。

创建地点、机位、天气/昼夜/光线变体、道具状态和场景绑定：

```bash
python3 scripts/novel_environment_assets.py create projects/jinghua-yuan-series
python3 scripts/novel_environment_assets.py validate projects/jinghua-yuan-series
```

地点设计固定布局、地标和连续性签名；每个机位与环境变体必须引用同一签名。道具设计固定尺寸、材质、显著标记、交互规则和状态，选中的环境/道具资产必须先登记到项目资产库。每个带地点的剧本场景都要绑定天气、时间、光线和道具状态，Web 国漫项目卡片及 `/api/novel-anime/projects/<id>/environment-assets` 会显示覆盖与就绪情况。

创建关键帧参考包、资产版本选择和美术审核记录：

```bash
python3 scripts/novel_asset_review.py create projects/jinghua-yuan-series
python3 scripts/novel_asset_review.py validate projects/jinghua-yuan-series
```

参考包按角色、地点、道具、镜头或剧集组织视图；每次选择记录资产 ID、版本、选择人和理由。选中版本必须是 Repository 当前版本，并通过明确的人工美术审核后才能进入视觉就绪状态。Web 项目卡片及 `/api/novel-anime/projects/<id>/asset-review` 会显示参考包、版本选择和审核阻断项。

创建 Scene/Shot 分解与镜头语法骨架：

```bash
python3 scripts/novel_shot_breakdown.py create projects/jinghua-yuan-series
python3 scripts/novel_shot_breakdown.py validate projects/jinghua-yuan-series
```

每个剧本场对应稳定的 Scene ID 和 Shot ID；镜头记录景别、角度、运动、焦段、时长、首状态、尾状态和参考包引用，并对首尾状态生成连续性签名。剧本或参考包修订后旧分镜会失效，Web 项目卡片及 `/api/novel-anime/projects/<id>/shot-breakdown` 显示场/镜头覆盖与审核进度。

创建静态 storyboard 与首尾帧槽位：

```bash
python3 scripts/novel_storyboard.py create projects/jinghua-yuan-series
python3 scripts/novel_storyboard.py validate projects/jinghua-yuan-series
```

每个 Shot 必须对应首帧和尾帧，帧槽位记录状态、资产、参考包、连续性状态签名和备注；Storyboard 时长必须与 Shot 一致，剧本或参考包修订后会自动失效。Web 项目卡片及 `/api/novel-anime/projects/<id>/storyboard` 显示首尾帧选择和审核进度。

创建本地 Animatic 计划：

```bash
python3 scripts/novel_animatic.py create projects/jinghua-yuan-series
python3 scripts/novel_animatic.py validate projects/jinghua-yuan-series
```

Animatic 计划覆盖五集，把 Shot、临时配音、字幕轨和集级预览输出放在同一份可恢复数据中；剧本或 storyboard 修订后计划自动失效。READY 集必须有镜头、临时音频、字幕、预览文件和人工审核，Web 项目卡片及 `/api/novel-anime/projects/<id>/animatic` 显示制作进度。

执行 Animatic 审核：

```bash
python3 scripts/novel_animatic_review.py audit projects/jinghua-yuan-series
python3 scripts/novel_animatic_review.py validate projects/jinghua-yuan-series
```

审核报告检查节奏、动作可读性、角色/场景/道具连续性和集级输入；阻断项、上游修订过期或人工审核未通过时不能进入下一阶段。报告会显示在 Web 国漫项目卡片和 `/api/novel-anime/projects/<id>/animatic-review`。

创建角色 voice profile 和逐句配音计划：

```bash
python3 scripts/novel_voice_profiles.py create projects/jinghua-yuan-series
python3 scripts/novel_voice_profiles.py validate projects/jinghua-yuan-series
```

每个故事角色拥有独立音色、音高、语速和 Provider/voice ID；每句对白绑定角色 profile，旁白保持独立，情绪与发音备注保存在逐句记录中。脚本修订后旧配音计划自动失效，Web 项目卡片及 `/api/novel-anime/projects/<id>/voice-profiles` 显示角色与台词覆盖。

创建混音、响度和声画同步计划：

```bash
python3 scripts/novel_audio_mix.py create projects/jinghua-yuan-series
python3 scripts/novel_audio_mix.py validate projects/jinghua-yuan-series
```

每集混音计划固定引用音轨、配音和 Animatic 修订，记录目标响度、真峰值、对白 Cue、输出文件和同步偏移；同步偏移超过 100ms 或缺少人工审核时不能 READY。Web 项目卡片及 `/api/novel-anime/projects/<id>/audio-mix` 显示混音集数、输出和最大偏移。

创建动态镜头路由、队列、预算和审核计划：

```bash
python3 scripts/novel_dynamic_shots.py create projects/jinghua-yuan-series
python3 scripts/novel_dynamic_shots.py validate projects/jinghua-yuan-series
```

每个 Shot 可选择本地运镜、图生视频、首尾帧、口型同步或人工导入，并记录 Provider、回退策略、队列重试、预算、上传授权和角色/动作审核。可计费或上传素材的任务必须显式确认；Web 项目卡片及 `/api/novel-anime/projects/<id>/dynamic-shots` 显示队列与预算。

创建集级剪辑时间线和镜头级重渲染计划：

```bash
python3 scripts/novel_edit_timelines.py create projects/jinghua-yuan-series
python3 scripts/novel_edit_timelines.py validate projects/jinghua-yuan-series
```

剪辑时间线固定引用动态镜头和混音修订，按集保存镜头片段、对白/Cue、字幕状态、DIALOGUE/MUSIC/AMBIENCE/SFX 音频总线、转场、特效和调色字段。只有镜头、字幕、输出文件和人工审核齐备时才能进入 READY；`rerender_jobs` 可按镜头替换或整集重渲染，并通过输入修订号阻止过期任务。Web 项目卡片及 `/api/novel-anime/projects/<id>/edit-timelines` 显示集数、就绪集、片段和重渲染任务。

执行六类 QC 并保留批注、问题单和版本比较：

```bash
python3 scripts/novel_qc.py audit projects/jinghua-yuan-series
python3 scripts/novel_qc.py validate projects/jinghua-yuan-series
```

QC 报告覆盖来源权利、剧情、连续性、角色与视听、技术和发布六类质量门，固定引用来源目录、剧情审核、Animatic、资产、混音、动态镜头和剪辑时间线修订。当前项目会明确报告权利未评估、剧情/连续性阻断、空时间线和禁止发布，而不会把技术骨架误判为成片。报告、批注、问题单和历史修订保存在项目的 `qc/` 目录；Web 提供 `/api/novel-anime/projects/<id>/qc`、`/qc/compare`，并支持通过 POST 添加批注、创建问题单、更新问题单状态和关联局部重渲染任务。

打开国漫制作台：

```text
http://127.0.0.1:8877/
```

左侧“国漫制作台”提供十个工作区：项目总览、IP 与底本、故事圣经、编剧室、角色美术、分镜 Animatic、音频制作、渲染队列、审片与问题单、发布包。它们通过 `/api/novel-anime/projects/<id>/workspaces` 读取同一项目数据；`/backups` 展示快照和迁移记录，创建快照需要明确的本地操作，恢复仍保留人工确认。

运行《镜花缘》正式五集验收：

```bash
python3 scripts/novel_acceptance.py audit projects/jinghua-yuan-series
python3 scripts/novel_acceptance.py validate projects/jinghua-yuan-series
```

验收报告写入 `acceptance/acceptance-report.json`，逐集检查剧本、连续性、角色视觉、配音、字幕、Animatic、混音和剪辑；同时确认旧技术样片只能作为参考资产，并预留一集三个真实动作 Provider 测试位。当前项目会生成 `HOLD` 报告，不会在权利、QC、人工审核或动作测试未完成时误判为正式通过；Web 项目卡片和 `/api/novel-anime/projects/<id>/acceptance` 会显示验收状态。

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

The same adapters are available through a dependency-free local web console. The recommended macOS launcher is:

```bash
./start-web.command
```

Restart it safely with:

```bash
./restart-web.command
```

The scripts keep a PID under `cache/`, write background logs to `logs/web-server.log`, prevent duplicate instances, and refuse to kill unrelated services that happen to use the same port. The launcher uses native arm64 Python plus a project-private `.web-python/` dependency directory from `requirements-web.txt`, so it does not depend on `venv/ensurepip` and does not load mismatched packages from the user site. A small `support/web-python/sitecustomize.py` fallback supplies the real macOS version from `/usr/bin/sw_vers` only when Python reports an empty `platform.mac_ver()`, which keeps pip/packaging compatible on affected macOS 26 hosts. For Web dependencies, pip is used only to download compatible binary wheels; `support/web-python/install_wheels.py` extracts them into `.web-python/`, avoiding pip's broken wheel-install path on the affected Python 3.14 environment. On Apple Silicon, if no native arm64 Python is available but native Homebrew exists at `/opt/homebrew/bin/brew`, the launcher automatically bootstraps Homebrew Python before installing the private Web dependencies. See [docs/WEB-OPERATIONS.md](docs/WEB-OPERATIONS.md) for operations and environment overrides.

The direct development command remains available:

```bash
python3 scripts/web_server.py --port 18765
```

Open `http://127.0.0.1:18765`. The console lists projects and local reference frames, shows which Provider keys are configured, and the **生成 Provider** menu lets you enter a key for the current server session. Session keys are held in memory only; use `OPENAI_API_KEY`, `RUNWAY_API_KEY`, or `FAL_KEY` when persistent local configuration is preferred. The workspace has both single-shot generation and **生成完整本地分镜** (three scenes plus local voice and captions), plus clickable cards for the five rendered pilot episodes; remote generation still requires an explicit confirmation, and the console previews the generated MP4 without publishing content.

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


## Blender Anime final-image route

The deterministic animation stack now has two explicit roles:

- `LOCAL_CUTOUT_RIG`: Animatic, dialogue blocking and shot timing.
- `BLENDER_ANIME`: current final-image target using a real 3D character, Armature/IK, Toon/NPR, line art/Grease Pencil enhancement, camera, lighting and local FX.

Godot cutout work is preserved as an experiment but is no longer the current final-image target.

On Apple Silicon:

```bash
./install-blender.command
./check-blender.command
```

The production automation targets Blender 5.2 LTS and forces arm64 execution. The first quality milestone is a single 5–8 second Baihua Fairy shot; the pipeline must pass human visual review before it is expanded to more characters. See `docs/BLENDER-ANIME.md`.


### Reference dialogue blockout

After Blender passes the environment smoke, render the uploaded-reference composition blockout:

```bash
./render-reference-demo.command
```

Outputs:

```text
cache/reference-dialogue-blockout.mp4
cache/reference-dialogue-blockout.blend
```

This blockout intentionally uses proxy geometry. Judge only adult/child proportion contrast, eye-lines, staging, sunset key/fill, depth of field, camera push and six-second dialogue pacing. Final character quality begins only after this blockout is accepted.


### P28-02 Child LookDev

After the dialogue Blockout passes, generate the first formal child LookDev still:

```bash
./render-child-lookdev.command
```

Review `renders/lookdev/child-lookdev-v1.png`. Command success is technical only; the visual gate remains human PENDING.


### P28-02 MPFB child basemesh

P28-02 no longer uses procedural primitive stacks for the child body. Install/check MPFB once, then render the real child basemesh checkpoint:

```bash
./install-mpfb.command
./check-mpfb.command
./render-child-lookdev-v5.command
```

Review `renders/lookdev/child-lookdev-v5.png`. Human visual approval remains required before costume/hair/rig work continues.


### P28-02 native child checkpoint

After the MPFB adult-basemesh checkpoint, render the native child phenotype checkpoint:

```bash
./render-child-lookdev-v6.command
```

Review `renders/lookdev/child-lookdev-v6.png`. Technical PASS does not close P28-02; human visual approval remains required.


### Final child LookDev

Skip further nude-basemesh iterations and render the full visual target directly:

```bash
./render-final-child-lookdev.command
```

Review `renders/lookdev/final-child-lookdev-001.png`. Human visual approval remains required.
