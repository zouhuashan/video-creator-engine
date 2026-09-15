---
name: video-creator
description: Turn a topic into a structured short-video production brief and coordinate the configured VideoCreator workflow. Use for requests to plan or produce social short videos; do not use for unrelated video editing.
---

# VideoCreator

将用户的自然语言选题整理为可执行的短视频任务，并按仓库中已实现的模块编排制作。项目根目录以 `VIDEO-CREATOR-TASK.md` 为准；它是唯一任务事实源。

## 解析任务

先读取 `config/app.yaml`、`config/platforms.yaml`、`config/providers.yaml` 和 `config/brand.yaml`。按用户原意解析以下字段：

- `topic`：主题；这是必填项，缺少时只询问主题。
- `platform`：映射为配置中的平台 ID；“视频号”对应 `wechat_channels`。
- `duration_seconds`：把“60 秒”“1 分钟”等转成秒。
- `tone`：保留用户指定风格；未指定时采用通俗、务实、口语化表达。
- `target_audience`：优先使用用户指定人群；否则按品牌定位默认为关注 AI、数码工具和消费避坑的普通人。
- `source_mode`：使用 `automatic_research`、`user_materials_first`、`provided_sources_only` 或 `no_external_research`。未指定时依 `app.workflow.auto_research` 选择。
- `voice`：一个对象，包含 `provider`、`voice_id` 和 `speed`；优先遵循用户指定，否则读取 Provider 和品牌配置，未配置的值保留为 `null`。
- `asset_strategy`：优先遵循用户指定；否则使用 `real_media_first`，并按平台/品牌配置中的素材优先级路由。
- `project_id`：仅在用户要求开始实际制作时创建；只做策划时不创建项目目录。

默认值必须来自配置或以上规则。保留用户明确提出的选择，不静默替换平台、时长、配音或素材策略。若平台未启用、时长超出平台范围或 Provider 未配置，在需求单中保留原请求并说明限制；只在主题缺失或信息互相矛盾导致无法继续时提问。

## 输出需求单

开始制作前，先生成这份结构化需求单作为执行 brief；可以向用户简要展示解析结果，但除主题缺失、信息矛盾等阻断项外，不等待确认，继续处理可用阶段。

```yaml
topic: ""
project_id: null
platform: wechat_channels
duration_seconds: 60
tone: "通俗、务实、口语化"
target_audience: "关注 AI、数码工具和消费避坑的普通人"
source_mode: automatic_research
voice:
  provider: fish_audio
  voice_id: null
  speed: null
asset_strategy:
  mode: real_media_first
  priority:
    - real_screen_recording
    - real_screenshot
    - real_footage_or_product_image
    - licensed_media
    - hyperframes_infographic
    - ai_generated_image_or_video
assumptions: []
warnings: []
```

将示例值替换为解析结果。没有实质影响的默认值写入 `assumptions`；不可满足的要求写入 `warnings`。用户已明确提供的信息不标为假设。

用户要求实际制作时，从主题提炼简短、语义明确的 ASCII 英文 slug，并调用 `python3 scripts/project_id.py --topic <topic> --slug <slug>` 创建项目目录。ID 格式由配置固定为 `YYYYMMDD-slug`；若目录已存在，脚本会分配数字后缀，禁止覆盖旧目录。脚本同时创建 `run.json` 并将状态初始化为 `CREATED`。把返回的 ID 写入需求单。纯策划请求不分配 ID。

## 编排与边界

- 按 Research → Topic → Script → Storyboard → Assets → Voice → Edit/Motion → QC → Packaging 的顺序协调已有模块；读取相关模块说明和配置后再调用。
- Research 阶段先读取 `skill/video-creator/research/SKILL.md`，按 `source_mode` 和来源等级调查并整理带引用的 brief，然后运行 `./video-creator research <project-id> --input-file <JSON>` 生成三个研究产物。CLI 校验来源等级和引用、按优先级整理引用并推进至 `RESEARCHED`；未配置 Search Provider 时由 Codex 搜索能力完成采集，不得假装本地 CLI 已搜索网页。
- Research 完成后读取 `skill/video-creator/topic/SKILL.md`，依据研究结果为流量、商业价值、常青度、制作成本和原创性评分并给出理由，随后运行 `./video-creator score <project-id> --assessment-file <JSON>` 生成 `topic.json`。证据强度和风险分由程序从研究来源及风险条目计算；总分低于门槛或风险过滤未通过时，不得继续自动进入制作。
- Topic gate 通过后读取 `skill/video-creator/script/SKILL.md`，按微信视频号 `Hook → Problem → Evidence → Comparison → Conclusion → CTA` 顺序撰写自然口语稿，为事实性段落关联研究来源编号，并为 Hook 标记结论、反常识或冲突类型，再运行 `./video-creator script <project-id> --input-file <JSON>` 生成 `script.json` 和 `script.md`。校验成功后由命令推进 `RESEARCHED → SCRIPTED`；评分未通过、引用无效、口语规则未通过或脚本结构不完整时停止，不推进状态。
- 每个阶段产物成功写入并通过该阶段校验后，才用 `python3 scripts/project_state.py transition <project-id> --to <NEXT_STATUS> --note "..."` 推进 `run.json`；不要手工编辑状态文件或跳过阶段。
- 用户要求继续项目或执行 `resume <project-id>` 时，运行 `./video-creator resume <project-id>` 并以返回的 `resume_stage` 为唯一恢复点。跳过已完成阶段，检查对应产物后从恢复点继续；缺少阶段处理器或产物损坏时说明阻塞，不重置状态或伪造完成记录。
- 用户要求局部重跑时，运行 `./video-creator rerun <project-id> scene <SCENE_ID>`、`voice`、`cover` 或 `qc`，读取 JSON 计划并严格按 `preserve`、`rebuild`、`checkpoint` 和 `invalidated_stages_after_success` 限定范围。场景 ID 必须能在 `storyboard.json` 或 `storyboard.md` 中找到；项目必须已完成该目标所需阶段。`PUBLISHED_MANUALLY` 项目禁止重跑。
- 当前 rerun CLI 只生成计划（`action=plan_only`、`execution_ready=false`），不执行生成，也不更改 `run.json`。若目标执行器或下游处理器尚未实现，说明具体缺项并保留项目状态；不要声称已重跑。执行器可用后，只重建计划列出的目标和下游产物，不要重新研究、写脚本或生成无关场景。精确匹配 text、voice、speed、provider 时复用配音缓存。
- 若恢复动作是 `await_human_review`，展示发布包并等待用户在平台人工发布；若为 `complete`，报告项目已完成。不得将这两种状态当作继续制作的入口。
- 只报告实际完成的阶段和产物。若所需模块、Provider 或平台配置尚未实现，说明具体缺项，交付已解析的需求单，不伪造研究、素材、视频或质检结果。
- 使用 `automatic_research` 时为事实性主张保留可核验来源；使用 `provided_sources_only` 或 `no_external_research` 时，不把未核实内容写成事实。
- API 凭据只从环境变量读取；不要读取、回显或写入日志中的密钥值。
- `config/app.yaml` 中 `auto_publish` 必须保持关闭。最终发布包只能交给用户人工确认，不能自动上传或发布。
- 只有用户明确确认已在线下/平台界面完成发布后，才可将状态推进至 `PUBLISHED_MANUALLY`，并使用 `--record-manual-publication` 标记。`READY_FOR_REVIEW` 之后默认停住等待人工发布。
- 仅在对应能力真实可用时承诺 Resume、局部重跑或其他状态管理行为；修改单个镜头时避免无必要地重做已完成阶段。

## 局部重跑计划

```text
./video-creator rerun <project-id> scene SC007
./video-creator rerun <project-id> voice
./video-creator rerun <project-id> cover
./video-creator rerun <project-id> qc
```

命令返回机器可读的范围计划，不会自行触发付费 Provider 或修改项目文件。场景重跑保留其它场景、配音和字幕，只重建目标场景及最终渲染、QC、发布包；配音重跑保留视觉素材并重做配音、字幕、最终渲染及其下游；封面重跑只更新封面和发布包；QC 重跑保留成片和封面，只重做 QC 与发布包。若 `execution_ready` 为 `false`，先报告执行器尚未接入，不要把计划当作已完成工作。

## 示例

用户：“做一期：40 块钱随身 WiFi 到底是不是智商税？60 秒，视频号。”

应解析为 `topic=40 块钱随身 WiFi 到底是不是智商税`、`platform=wechat_channels`、`duration_seconds=60`，其余可选项按配置和默认规则补齐，并把任何尚未实现的制作阶段明确列入 `warnings`。
