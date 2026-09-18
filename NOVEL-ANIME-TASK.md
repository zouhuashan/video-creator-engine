# Novel Anime Task

> 低成本国风小说动态漫执行规划（规划版）

**状态：** `IN_PROGRESS`
**版本：** `0.1.0`
**建议首个执行任务：** `N0-01`
**适用项目：** VideoCreator Engine
**当前说明：** 本文件是小说动态漫路线的专项任务计划。现有 `VIDEO-CREATOR-TASK.md` 仍然是当前生产链路的单一事实来源；本轮已按 N7 Web 增量执行制作台完善，不改变现有 P28 验收状态、不安装新依赖、不触发远程生成和发布。

## 1. 目标与边界

### 1.1 目标

建立一条可以低成本连载、可局部重跑、可持续升级的“小说 → 国风动态漫”生产链路：

```text
小说/IP
  ↓
故事圣经与连续性
  ↓
剧本与分镜
  ↓
Scene JSON / Shot JSON
  ↓
角色、场景、道具、特效资产解析
  ↓
Canvas / SVG / HyperFrames / Remotion 程序化动画
  ↓
FFmpeg 合成
  ↓
TTS、字幕、BGM、音效
  ↓
QC 与发布包
```

第一阶段的产品形态是 **国风动态漫 / 小说漫剧**：固定立绘和场景拥有轻微运动、镜头推拉、景深、表情、嘴型、粒子和转场，服务于旁白和连续剧情。它不以高成本逐帧动画、复杂打斗或全程 AI 图生视频为目标。

### 1.2 非目标

- 不把 Runway、Wan、Sora 或其他远程视频模型作为主链路依赖。
- 不在本阶段安装大型渲染环境或重写已有生产系统。
- 不为了“看起来像完整动画”而重复生成同一角色和场景。
- 不自动发布到任何平台；发布必须经过人工确认。

## 2. 成本原则

1. **资产一次制作、长期复用。** 角色、场景、道具和特效均有稳定 ID、版本和变体。
2. **本地确定性渲染优先。** 默认使用现有运行时、Canvas/SVG、HyperFrames/Remotion 和 FFmpeg；相同输入、版本和 seed 应能得到可比较的结果。
3. **远程 AI 按镜头可选。** AI 图片/视频只作为角色初稿、特殊镜头或后期增强 Provider；未显式启用时不得发起付费请求。
4. **先完成五集可连贯样片，再提高单镜头质量。** 用复用率、渲染时间、失败率和人工修改时间判断路线是否成立。
5. **预算可见且可阻断。** 每次运行产生 manifest、Provider、预计/实际成本；超过预算时进入 `blocked`，不静默切换到收费服务。

## 3. 与现有 VideoCreator Engine 的兼容关系

| 现有能力 | 本专项的复用方式 |
| --- | --- |
| IP、source、series、season、arc、episode、scene、shot 层级 | 保持对象层级和稳定 ID，增加动态漫专用字段 |
| Story Bible、Continuity、Character/Location 资料 | 作为角色、场景和连续性约束的上游输入 |
| Scene/Shot 时间线与编辑清单 | 继续使用，新增 `render_plan`、`asset_refs`、`motion_preset` |
| Provider/Adapter 抽象 | 所有渲染、TTS、音频、可选 AI 能力均通过 Adapter 注入 |
| QC、人工确认、五集验收 | 复用状态机；增加资产一致性、帧率、字幕安全区和音频峰值检查 |
| Web 工作台 | 复用项目、分镜、运行记录和预览页面；后续增加资产库与重跑入口 |

兼容原则是“在现有接口后面增加低成本实现”，而不是把当前系统改造成某个具体商业模型的客户端。

## 4. 核心领域模型与目录约定

### 4.1 核心对象

- `NovelProject`：小说/IP、版权状态、改编范围、风格配置和成本预算。
- `StoryBible`：世界观、人物关系、术语、时间线、禁用表达和连续性规则。
- `Episode`：集标题、剧情摘要、旁白稿、时长目标、发布比例。
- `Scene`：地点、时间、天气、情绪、连续性上下文和镜头列表。
- `Shot`：镜头时长、相机、角色动作、字幕/音频引用、特效和渲染 Provider。
- `Asset`：角色、场景、道具、背景层、特效预设、音频和字体等可复用资源。
- `RenderRun`：输入快照、版本、seed、Provider、缓存键、产物和错误信息。
- `Review`：自动 QC、人工意见、阻断项和确认记录。
- `PublishPackage`：视频、封面、字幕、文案、元数据和人工发布确认。

### 4.2 稳定 ID 与版本

所有对象使用稳定的业务 ID，例如 `char_jinghua_01`、`loc_bamboo_forest_01`、`ep_001_scene_003_shot_002`。修改资产不覆盖历史版本，而是生成 `asset_version`；Scene JSON 引用具体版本或明确的 `latest_approved` 解析策略。

建议目录：

```text
projects/<project_id>/
  project.json
  story/bible.json
  episodes/<episode_id>/script.json
  episodes/<episode_id>/storyboard.json
  episodes/<episode_id>/scenes/<scene_id>.json
  assets/characters/<character_id>/<version>/
  assets/locations/<location_id>/<version>/
  assets/props/<prop_id>/<version>/
  assets/effects/<effect_id>/<version>/
  runs/<run_id>/manifest.json
  outputs/<episode_id>/
  publish/<episode_id>/
```

## 5. 资产层设计

### 5.1 角色资产层

首个试播项目建议先制作 3–5 个核心角色。每个角色至少包含：

- 正面/三分之四/侧面基准图或 SVG；
- 身体部件和可动锚点：头、身体、手臂、武器、衣摆、发束、配饰；
- 表情：平静、惊讶、愤怒、悲伤、冷笑；
- 嘴型：闭合、半开、张开、圆口；
- 姿势：站立、持物、行走、受伤或坐姿；
- 服装、发色、瞳色、身高比例、禁用变化；
- 声音档案：音色、语速、情绪和 TTS Provider 配置。

角色资产必须附带锚点、画布尺寸、透明区域、裁切规则和授权来源，避免动画阶段凭视觉猜测位置。

### 5.2 场景、道具与构图层

第一阶段准备 10–15 个可复用地点：山门、大殿、房间、竹林、山路、城镇、客栈、森林、山洞、秘境、悬崖和夜景。每个地点支持远景/中景/前景分层，并通过程序控制时间、光线、雾、雨雪和色调。

道具独立注册，例如剑、卷轴、灯笼、符咒、茶盏。道具可被多个角色和镜头引用，不复制进角色图片。

### 5.3 特效层

特效以可参数化 preset 保存，第一批包括：水墨晕染、雾、雪、花瓣、尘埃、剑气、符咒、雷电、光尘、书页/墨迹转场。每个 preset 规定输入参数、性能上限、透明混合方式、可访问性降级和预览缩略图。

## 6. Scene JSON / Shot JSON 约定

Scene JSON 是渲染器和 Web 工作台之间的稳定契约。它只描述“要什么”，不把具体 Canvas、Remotion 或 FFmpeg 代码写进剧情数据。

示例：

```json
{
  "schema_version": "scene.v1",
  "scene_id": "ep_001_scene_003",
  "episode_id": "ep_001",
  "format": { "width": 1080, "height": 1920, "fps": 24 },
  "continuity": { "location_id": "loc_bamboo_forest_01", "time": "night", "weather": "fog" },
  "shots": [
    {
      "shot_id": "ep_001_scene_003_shot_001",
      "duration_ms": 5200,
      "camera": { "scale_from": 1.0, "scale_to": 1.08, "pan": "left_to_right", "focus": "hero" },
      "layers": [
        { "asset_ref": "loc_bamboo_forest_01@approved", "motion": "parallax_background" },
        { "asset_ref": "char_hero_01@v3", "pose": "standing", "expression": "alert", "motion": "breathing" },
        { "asset_ref": "prop_sword_01@v1", "motion": "subtle_glint" }
      ],
      "effects": [{ "preset": "ink_fog", "intensity": 0.35 }, { "preset": "petals", "count": 12 }],
      "audio_refs": ["voice.ep001.narration.003", "sfx.forest_night"],
      "subtitle_ref": "sub.ep001.003",
      "render": { "provider": "local.cutout", "seed": 18302 }
    }
  ]
}
```

Schema 必须校验：时长、帧率、画布比例、资产版本、锚点、音频时基、字幕安全区、Provider 能力和预算。缺失资产时应在渲染前失败并给出可操作错误。

## 7. Provider / Adapter 设计

所有外部或可替换能力都通过接口访问：

| Adapter | 默认实现 | 可选实现 |
| --- | --- | --- |
| `RenderProvider` | 本地 Canvas/SVG cutout | HyperFrames、Remotion、可选 AI 视频镜头 |
| `ImageProvider` | 本地已有资产 | 可选图片生成服务 |
| `VideoProvider` | 空实现/人工跳过 | Runway、Wan、Sora 等，按镜头启用 |
| `TTSProvider` | 已接入或本地 TTS | 其他商业/开源语音服务 |
| `MusicProvider` | 本地授权 BGM 库 | 可选音乐生成或素材服务 |
| `MuxProvider` | FFmpeg | 其他封装器 |

Provider 返回统一的 `artifact_ref`、`provider_run_id`、成本、时长、日志摘要和可重试错误。禁止在业务层直接调用某个厂商 SDK。远程 Provider 默认关闭；启用前需有项目级开关、镜头级开关和预算上限。

## 8. 分阶段任务

任务状态使用 `TODO / IN_PROGRESS / BLOCKED / DONE / HOLD`。每项任务都必须有交付物、验收标准和依赖；任务完成后才能推进依赖它的下一项。

### N0：范围冻结与基线（不安装）

#### N0-01 冻结低成本路线与状态机

- **交付物：** 本文件、成本规则、任务状态和人工发布门。
- **验收：** 明确本地主链路、远程 AI 可选、发布必须人工确认；无默认付费调用。
- **依赖：** 无。

#### N0-02 盘点现有模块和可复用接口

- **交付物：** 现有 Schema、Provider、Web、QC、渲染脚本与本方案的映射表。
- **验收：** 只读检查，不安装依赖、不改变现有生产任务。
- **依赖：** N0-01。

#### N0-03 建立试播项目骨架

- **交付物：** `NovelProject`、目录、版本和 manifest 示例。
- **验收：** 能创建空项目、读取配置、生成可恢复的 run manifest。
- **依赖：** N0-02。

### N1：小说与连续性

#### N1-01 小说导入与章节切片

- **交付物：** 章节、人物、地点、事件和术语的结构化输入。
- **验收：** 原文来源、改编范围、版权备注和章节定位可追溯。

#### N1-02 Story Bible 与 Continuity 检查

- **交付物：** 世界观、人物关系、时间线、禁用变化和术语表。
- **验收：** 剧本和 Scene JSON 能引用稳定的连续性 ID。

### N2：角色与场景资产库

#### N2-01 角色资产规范和注册表

- **交付物：** 3–5 个角色的基准图、部件、表情、嘴型、姿势、声音档案。
- **验收：** 角色跨五集使用时 ID、比例、服装和色彩稳定。

#### N2-02 地点、道具与背景分层

- **交付物：** 10–15 个可复用地点和首批道具。
- **验收：** 每个地点至少有远景/中景/前景或明确降级策略。

#### N2-03 国风特效 preset 库

- **交付物：** 水墨、雾、雪、花瓣、剑气、符咒等参数化 preset。
- **验收：** preset 能由 Scene JSON 引用，且有性能上限和静态降级。

### N3：剧本、分镜与编译

#### N3-01 剧本到镜头的编排规则

- **交付物：** 旁白节奏、镜头时长、情绪、景别、转场和字幕规则。
- **验收：** 一集 45–90 秒能编译为完整 Scene/Shot JSON。

#### N3-02 Scene JSON / Shot JSON Schema

- **交付物：** Schema、校验器、示例和错误码。
- **验收：** 资产缺失、时基不一致、无效 Provider 和超预算在渲染前被拦截。

### N4：本地程序化动画

#### N4-01 Cutout 渲染器

- **交付物：** Canvas/SVG 或现有 HyperFrames/Remotion 适配器。
- **验收：** 支持图层、锚点、透明度、缩放、平移、旋转、景深和 9:16 输出。

#### N4-02 低成本角色动作

- **交付物：** 呼吸、眨眼、嘴型切换、头发/衣摆摆动、持物微动和基础表情插值。
- **验收：** 同一角色在连续镜头中不重新生成，动作由参数驱动。

#### N4-03 镜头与转场

- **交付物：** 推拉、摇移、景别切换、水墨/书页/淡入淡出转场。
- **验收：** 可按 shot 局部渲染，并能替换单个镜头而不重跑整集。

### N5：音频、字幕与合成

#### N5-01 TTS、对白、音效和 BGM 编排

- **交付物：** 音频轨道清单、音量、淡入淡出、ducking 和授权信息。
- **验收：** 旁白、对白、音效和 BGM 的时间线可复现且不削波。

#### N5-02 字幕生成与安全区

- **交付物：** 逐句字幕、样式、断句、时间码和 SRT/VTT 导出。
- **验收：** 竖屏安全区内可读，字幕时间与旁白误差在项目阈值内。

#### N5-03 FFmpeg 合成与发布文件

- **交付物：** MP4、封面帧、字幕文件、音频、缩略图和元数据。
- **验收：** 本地播放器和 Web 预览均可播放，编码参数符合目标平台约定。

### N6：运行、QC 与长期升级

#### N6-01 Resume、局部重跑与缓存

- **交付物：** run manifest、输入哈希、缓存键、失败重试、shot/scene/episode 级重跑。
- **验收：** 中断后可从最后成功产物继续；输入未变时不重复渲染。

#### N6-02 自动 QC 与人工 Review

- **交付物：** Schema、资产、黑帧、时长、帧率、字幕安全区、音频峰值、重复帧和文件完整性检查。
- **验收：** QC 输出结构化报告；阻断项不能进入发布包。

#### N6-03 Provider 版本和迁移

- **交付物：** Provider 能力声明、版本锁定、迁移脚本和回滚说明。
- **验收：** 替换渲染器/TTS 不改变业务 JSON；旧 run 可复验。

#### N6-04 五集试播验收

- **交付物：** 连续五集样片、发布包、成本和质量报告。
- **验收：** 至少 3 个角色、10 个地点资产可复用；每集 45–90 秒；主链路不调用付费 AI；人工确认后才可发布。

### N7：Web 工作台

#### N7-01 资产库与连续性面板

- **交付物：** 角色、地点、道具、特效版本浏览和审核入口。
- **验收：** 能查看引用关系、预览变体、锁定 approved 版本。

#### N7-02 分镜编辑与 Scene JSON 预览

- **交付物：** 镜头时间线、资产选择、参数编辑、静态预览和校验错误提示。
- **验收：** 修改一个镜头不影响其他镜头，保存后可恢复。

#### N7-03 运行队列、日志与发布门

- **交付物：** 运行状态、局部重跑、QC 报告、产物下载和人工确认按钮。
- **验收：** 远程 Provider、发布动作均有显式开关和审计记录。

## 9. 运行与可恢复性要求

每次运行都创建不可变的 `run manifest`，至少记录：项目/集/场/镜头 ID、Schema 版本、资产版本、Provider 版本、输入哈希、seed、命令摘要、预算、开始/结束时间、产物和错误。

缓存键建议由以下字段组成：

```text
schema_version + scene_json_hash + asset_versions + provider_version + seed + output_profile
```

支持四级运行范围：`shot`、`scene`、`episode`、`publish_package`。只有受影响的下游产物需要失效；修改角色资产时应能列出所有受影响镜头。

## 10. 阶段门与衡量指标

### Gate A：能跑通

- 一集示例可以从 Scene JSON 本地渲染到 MP4。
- 不需要远程 AI、人工逐帧绘制或不可追踪的手工步骤。

### Gate B：能连贯

- 五集使用相同角色和地点资产，角色比例、服装、色彩和声音保持稳定。
- 旁白、字幕、镜头节奏和剧情顺序经过人工确认。

### Gate C：值得扩展

- 新增一集主要是编写剧本、选择资产和调整参数，而不是重复制作资产。
- 能统计单集渲染耗时、失败率、人工修改时长、资产复用率和预计成本。
- 远程 AI 镜头可作为独立 Provider 接入，不改变主链路。

首个试播期建议记录：单集总耗时、每个镜头平均重跑次数、资产复用率、TTS/音频成本、人工 QC 时长、黑帧/字幕/音频错误数量。

## 11. 首次执行顺序

在用户明确把本文件设为当前任务源后，按以下顺序执行：

1. `N0-01` 冻结路线、状态和预算门；
2. `N0-02` 只读盘点现有模块；
3. `N0-03` 创建试播项目骨架；
4. `N1-01`、`N1-02` 固化小说和连续性输入；
5. `N2-01` 至 `N2-03` 建立可复用资产；
6. `N3-01`、`N3-02` 编译首集；
7. `N4-01` 至 `N5-03` 跑通本地动态漫成片；
8. `N6-01` 至 `N6-04` 完成恢复、QC 和五集试播；
9. `N7-01` 至 `N7-03` 将生产能力完整接入 Web 工作台。

## 12. 当前未执行事项

- 未安装 HyperFrames、Remotion、Canvas、SVG 或任何新依赖；FFmpeg 仍使用现有环境能力。
- 未接入 Runway、Wan、Sora 或其他收费 Provider。
- 已生成首批百花仙子角色锚点、昆仑瑶池场景锚点与 6 秒本地动态样片；它们仍处于人工审核前的试制状态。尚未生成正式配音或发布视频。
- 未修改 `VIDEO-CREATOR-TASK.md` 的当前 `NEXT` 任务。
- 未创建或发布任何外部平台内容。

## 13. Web 增量执行记录

**执行状态：** `N7_WEB_INCREMENT_DONE`
**范围：** 制作台可见性、工作区详情、阶段门、项目切换、快照和 QC 问题单入口。

- 后端新增 readiness 聚合接口：`/api/novel-anime/projects/<id>/readiness`，从现有项目摘要派生 7 个阶段门，不维护第二套项目状态。
- Web 总览新增 `HOLD · x/7` 阶段门、下一步阻断提示和阶段详情；当前《镜花缘》会明确显示权利、故事、资产、分镜、音频、渲染和 QC 阻断。
- 制作台支持切换国漫项目、刷新工作区、查看资源详情 JSON、创建本地快照，并在审片工作区创建 QC 问题单。
- 保留人工发布门、Provider/Adapter、局部重跑和现有 P28 正式验收规则；没有自动调用 Runway、Wan、Sora 或其他收费服务。
- 验证结果：Web 专项与验收测试通过；全量测试 `306 passed, 6 subtests passed`。

## 14. P28-01 复验增量记录（2026-09-17）

- 将维基文库《镜花缘》前五回导入 `sources/input/jinghua-yuan-first-five-wikisource.txt`，建立 `SRC-JHY-001` 来源目录和 5 个章节定位；导入标记为 `test_only=true`，权利状态保持 `UNASSESSED`，未宣称可发布或可改编。
- 生成故事圣经草稿并扩展到前五回所需范围：14 个角色、8 个地点、6 个道具、12 个时间线事件、2 个伏笔和 6 个连续性快照；所有角色/地点/道具仍等待人工审核。
- 按“女魁星与玉碑 → 瑶池誓约 → 兵败血书 → 醉笔催花 → 牡丹受贬”完成 S01E001–S01E005 五集草稿，共 15 场、48 个表演单元，并重建 Shot、Storyboard、Animatic、声音配置、音频、动态镜头和剪辑时间线包。
- 刷新故事审查、QC 与正式验收报告。当前验收仍为 `HOLD`：0/5 集 READY，QC `BLOCKED`，12 个开放阻断项，人工审核 `PENDING`，动作测试 0/3。
- 未调用 Runway、Wan、Sora 或其他远程 Provider；Web 工作台会读取以上本地数据并显示最新数量与阻断原因。
- Web 项目摘要增加按项目 JSON/数据库修订自动失效的进程内缓存，避免项目列表、阶段门和工作区并发重复校验五集数据；实测缓存命中请求由约 21 秒降至约 0.02 秒。
- 验证结果：Web 专项 `10 passed`；全量测试 `306 passed, 6 subtests passed`；JavaScript、Python 编译和差异格式检查通过。

下一步继续执行前，应先完成来源权利核验、五集剧情与连续性人工审核，再制作并审核角色/场景资产；P28 正式验收仍保持 `HOLD`。

## 15. 单一试点与首批视觉样片（2026-09-17）

- 项目目录只保留 `projects/jinghua-yuan-series`；其余 27 个旧试制与示例项目移入 `/Users/zouhuashan/.Trash/video-projects-backup-20260917`，保留可恢复性。
- 视觉方向锁定为“绢本设色·轻水墨国风动态漫”，完成百花仙子透明角色锚点和昆仑瑶池月夜场景锚点，并登记角色身份、默认服装、场景布局与夜景变体。
- 资产审核现在同时覆盖角色、服装、场景，并读取仓库中的当前资产版本；首批 2 个参考包、3 个参考项保持 `PENDING`，等待人工选择与批准。
- 新增 `scripts/render_local_motion_test.py`，通过本地程序化背景移动、人物呼吸、薄雾与花瓣合成 6 秒 1080×1920 / 24fps 样片；结果登记为 `AST-KEYFRAME-JHY-LOOKDEV-001` 与 `AST-VIDEO-JHY-LOOKDEV-001`，费用为 0，未上传素材。
- Web 首页只展示《镜花缘》试点，并自动播放最近的本地样片；角色锚点、场景锚点与样片首帧可直接作为本地镜头输入。

下一步：先由人工确认百花仙子与瑶池的风格方向；确认后补齐百花仙子正/侧/背/近景与基础表情，再沿相同资产规范推进牡丹仙子、嫦娥和武则天，并接入正式配音与字幕。

## 16. 百花仙子角色包与 ArcReel 可选工作台（2026-09-17）

- 百花仙子新增正面、左侧面、背面三张 1024×1536 透明角色转面图，连同原 3/4 锚点组成 4 个已选择的角色参考；资产、版本和生成提示均已登记，近景与基础表情仍待生成及人工审核。
- 资产审核包已重建为 2 个参考包、6 个参考项；所有正式选择与审核继续保持 `PENDING`，没有绕过人工阶段门。
- 新增 ArcReel HTTP Workspace Adapter。ArcReel 作为独立部署的可选侧车，用于任务队列、Provider 调度、成本统计、恢复和剪映草稿导出；VideoCreator 继续保存主数据和验收状态。
- Web 设置页新增 ArcReel 地址、可选访问令牌和连接检测；敏感值只存在当前进程，界面保留 `Powered by ArcReel` 署名与仓库链接。
- 本增量不复制 ArcReel 源码、不安装其依赖、不自动同步素材、不发起收费生成，也不改变当前 `P28-01` 复验顺序；部署和首次项目镜像在下一增量中单独执行。

## 17. ArcReel 本地侧车部署（2026-09-17）

- 已部署 ArcReel `0.30.0` 官方容器，镜像固定到摘要 `sha256:d56db7fdbebc8a8c13b46a44956707e5bbb0b6052fa324061ac3bc3769aedd63`。
- 服务仅绑定 `127.0.0.1:1241`，运行数据隔离在 `integrations/arcreel/data/`；Web 可自动发现本地侧车并显示连接与镜像项目状态。
- 已建立 `jinghua-yuan-series` 镜像项目，规格为 `drama + novel + storyboard + 9:16`；本地公开底本已复制到本机侧车，工作流进入 `ASSET_INVENTORY`，任务数 0。
- 新增 `scripts/arcreel_mirror.py`，可重复核对五集和 15 个稳定镜头 ID，并以显式 `--sync-source` 复制底本。未复制图片或声音，没有配置 Provider，也没有触发生成费用。

## 18. 暂停 ArcReel 与自有角色预览链路（2026-09-17）

- ArcReel 容器已停止，镜像项目和本地数据保留；`integrations/arcreel/PAUSED` 记录暂停策略，Web 显示“已暂停”且不进行连接探测。
- 自有 Web 的“角色美术”工作区新增本地角色资产画廊，展示角色视图、资产 ID 和当前图片，可直接选择任一已登记透明角色图。
- 新增零成本角色动作预览接口：使用本地背景、角色呼吸、镜头移动、薄雾与花瓣生成 1080×1920 / 24fps MP4，不上传素材，不调用外部模型。
- 预览输出会自动登记为 `video` 和 `keyframe` 资产版本，并记录角色图与场景图依赖；已完成百花仙子正面 2 秒链路实测。

## 19. 本地角色 Rig 分层链路（2026-09-17）

- 新增 `scripts/build_character_rig.py`，把已审核前的透明角色图按原画布对齐拆成 `full/head/torso/lower` 四层 PNG；层资产通过仓库登记并保留来源依赖，重复执行可复用当前版本。
- 百花仙子正面图已生成 `RIG-CHR-JHY-BAIHUA-FRONT-V1`，画布保持 1024×1536，支持呼吸、眨眼、嘴型、头发、衣袖和飘带等后续本地动作通道；人工审核状态仍为 `PENDING`。
- Web 角色美术工作区新增 Rig 摘要，显示层数、来源、动作通道和审核状态；新增 `/api/novel-anime/projects/<id>/character-rigs` 只读接口。
- 本增量仍不安装 HyperFrames/Remotion、不调用 Runway/Wan/Sora，也不改变 `P28-01` 的验收门。

## 20. Rig 分层动作预览（2026-09-17）

- 新增 `scripts/render_character_rig_preview.py`，使用 `head/torso/lower` 三层透明资产进行本地 Pillow/FFmpeg 合成；角色分层会随呼吸和镜头轻微摆动，背景、雾和花瓣继续复用本地特效。
- Web 角色美术工作区新增“生成 Rig 动作预览”按钮，结果自动登记视频与首帧资产，并保留所有 Rig 层与场景依赖。
- 本地 Rig 预览已完成 2 秒链路实测，仍处于人工审核前的 `PENDING` 状态；远程视频 Provider 与 ArcReel 继续暂停。

## 21. Rig 资产校验（2026-09-17）

- Rig 清单接口现在同时返回画布尺寸、RGBA、透明内容和层文件存在性校验；校验失败只标记为“需检查”，不会自动通过人工审核。
- Web 角色工作区会显示 Rig 校验结果，便于局部替换层文件后快速确认是否仍可渲染。

## 22. 表情、嘴型与分镜级 Rig 调用（2026-09-17）

- 新增 `visual-bible/character-expression-channels.json`，定义平静、浅笑、担忧、惊讶四种表情，以及 `rest/smile/o/wide` 嘴型和基础音素映射；状态仍为 `PENDING`。
- Rig 渲染器支持 `expression` 与 `mouth_cues`，在本地分层预览中绘制轻量嘴型和眉形变化，不依赖远程图像或视频模型。
- 新增 `/api/novel-anime/projects/<id>/storyboard-rig-preview`，按现有 storyboard 的 `shot_id` 读取镜头时长并调用 Rig；已用 `SHOT-S01E002-SC002-001` 完成测试。
- Web 角色工作区提供表情选择和“按分镜预览”入口，仍保留人工审核门。

## 23. 对白到嘴型自动编译（2026-09-17）

- 新增 `scripts/compile_mouth_cues.py`，从 `audio/voice-profiles.json` 的本地台词分配生成镜头级 `dynamic/mouth-cues.json`。
- 分镜 Rig 预览在未显式传入 `mouth_cues` 时自动读取该文件，台词变更后重新编译即可局部更新嘴型节奏。
- 当前已覆盖 16 条带说话角色的试播台词；生成文件仍标记为 `PENDING`，不代表正式配音或最终口型审核通过。

## 24. 字幕、音频与嘴型统一时间轴（2026-09-17）

- `dynamic/mouth-cues.json` 现在同时包含 `subtitle`、`audio`、`mouth_cues` 和镜头起止时间，形成统一的本地时间轴来源。
- 新增 `/api/novel-anime/projects/<id>/timeline-cues` 只读接口，Web 或后续音频模块可读取同一组 cue。
- 分镜 Rig 预览响应会返回对应 `timeline_cue`，当前音频资产为空、字幕和音频状态为 `PLANNED`，不会伪装成正式配音已完成。

## 25. 本地 TTS、字幕与对白混音（2026-09-17）

- 新增 `scripts/generate_local_tts.py`，调用 macOS 内置 `say` 的中文 `Tingting` 声线生成 16 条本地 WAV，并登记为 `audio` 资产。
- 新增 `scripts/render_timeline_outputs.py`，根据同一时间轴生成每个镜头的对白混音 WAV 和 SRT 字幕，并登记混音与字幕资产。
- `dynamic/mouth-cues.json` 的 `audio.asset_id`、`audio.mix_asset_id` 和 `subtitle_asset_id` 已回写；所有音频仍需人工听审，项目审核状态不自动变更。

## 26. 镜头级最终成片预览（2026-09-17）

- 新增 `scripts/mux_timeline_shot.py`，将 Rig 视频与统一时间轴中的对白混音合成为带音频的 MP4；SRT 作为已登记字幕资产保留。
- 新增 `/api/novel-anime/projects/<id>/storyboard-final-preview`，Web 角色工作区可直接生成“最终镜头”。
- 已完成 `SHOT-S01E002-SC002-001` 合成测试，输出视频资产已记录 Rig、音频、混音、字幕和场景依赖；正式发布仍需人工审片。

## 27. 最终镜头人工审片门（2026-09-17）

- Web 新增最终镜头审片状态，分别记录声音、字幕、嘴型三项检查和审片备注；默认保持 `PENDING`。
- 新增 `/api/novel-anime/projects/<id>/final-shot-review` 读写接口；只有三项均为 `PASS` 才能标记 `APPROVED`。
- 新增批量预览入口 `/api/novel-anime/projects/<id>/storyboard-final-batch-preview`，审片未通过时返回阻断，不会提前批量渲染。
- 新增 `scripts/batch_render_final_shots.py`；批准后只批量生成与当前百花仙子 Rig 匹配的 4 个对白镜头，其余角色镜头返回 `blocked_character_ids`，等待各自 Rig，禁止错用角色形象。

## 28. Rig 覆盖率与角色安全批量（2026-09-17）

- 新增 `/api/novel-anime/projects/<id>/rig-coverage`，按统一对白时间轴统计各角色镜头数与 Rig 覆盖状态。
- 当前覆盖率为 4/16（25%），仅百花仙子镜头可安全批量生成；武则天、嫦娥、太平公主等角色保持阻断。
- Web 显示覆盖率和缺失角色清单；下一位建议优先制作武则天 Rig。内置图片生成服务本次连接失败，未切换到需要 API Key 的付费方案。

## 29. 百花仙子首批批量成片（2026-09-17）

- 根据用户授权完成自动技术审片：视频可解码、音轨非静音、SRT 文本有效、嘴型 cue 均在镜头时长内；审核记录明确标注为技术审核，发布前仍建议人工试听观感。
- 批量生成百花仙子可覆盖的 4 个对白镜头，全部完成解码检查并登记视频资产。
- 新增 `dynamic/final-batch.json` 和 `/api/novel-anime/projects/<id>/final-batch`，用于 Resume、批次状态和 Web 展示。

## 30. 多角色 Rig 与场景路由（2026-09-18）

- `scripts/build_character_rig.py` 支持任意角色 ID、角色名和 Rig ID，并以 upsert 方式保留已有 Rig；角色层资产 ID 不再硬编码百花仙子。
- 新增武则天、嫦娥、太平公主、百草仙子、麻姑、骆宾王、牡丹仙子和上官婉儿正面角色锚点，连同百花仙子共 9 套基础 Rig。
- 新增暖阁、上林苑、小蓬莱、麻姑洞、败军战场和红岩洞场景锚点。镜头渲染按场景引用选择背景，并把实际背景资产写入视频依赖。
- 场景效果按背景选择：昆仑、小蓬莱、上林苑和红岩洞可使用花瓣；暖阁、麻姑洞和战场关闭花瓣。

## 31. 前五集对白镜头本地成片全覆盖（2026-09-18）

- `dynamic/final-batch.json` 从单一角色批次升级为跨 Rig 合并清单，按 `shot_id` upsert，局部重跑不会丢失其他角色结果。
- 前五集 16 条说话角色镜头全部生成 1080×1920 / 24fps 本地动态成片，覆盖率为 16/16（100%），涉及 9 个角色 Rig 和 7 个场景锚点。
- 修复短 TTS 触发 `-shortest` 提前截断视频的问题；混音现在对音频补静音，以视频时间轴决定最终时长。
- 16 个 MP4 均完成逐帧解码检查，实际时长与 cue 目标误差不超过 0.02 秒。角色图、场景图和成片继续保持人工审核 `PENDING`，发布门未解除。
- 当前下一步仍属于 `P28-01`：把对白镜头与动作、视觉、旁白、音效单元组装成五集完整本地试播母版，再进行逐集人审；真实动作 Provider 对比仍作为可选增强保留。

## 32. 前五集完整本地母版与逐集人审（2026-09-18）

- 统一语音时间轴现有 28 个单元：16 条角色对白和 12 条旁白；旁白使用空嘴型序列，避免错误驱动角色 Rig。
- `scripts/assemble_local_episodes.py` 依据五集剧本顺序组装 48 个表演单元：已有对白成片直接复用，旁白单元使用场景动态与本地 TTS，其余动作/视觉/音效单元使用场景动态和静音 AAC，以便无损拼接及局部重跑。
- 输出 `renders/episodes/s01e001-local-pilot-v1.mp4` 至 `s01e005-local-pilot-v1.mp4`，总时长约 284.31 秒；每集同时保留无字幕母版和 SRT，视频与字幕均登记为仓库资产。
- 竖屏字幕固定使用左右安全区、底部安全边距、15 字主动换行和最多两行；35 字长句自动拆成连续 cue。五集代表帧已复检，不再出现左右裁切。
- Web“渲染队列”提供五集内嵌播放器、字幕文件、时长/片段数和剧情、画面、声音、字幕四项逐集人审。人审 API 自动计算单集与整批状态，所有状态默认 `PENDING`，没有绕过最终发布确认。
- `scripts/qc_episode_masters.py` 对五集执行完整解码、编码/分辨率/帧率、音轨、时长、字幕安全区和烧录差异检查；五集全部 `PASS`，报告写入 `renders/episodes/episode-technical-qc.json` 并可从 Web 查看。
- 三个 Provider 测试包已准备：Runway 小蓬莱开场、Wan 百草仙子微动作、OpenAI Sora 嫦娥衣袂与花瓣；均保留为本地输入和提示词，状态为 `BLOCKED_PENDING_AUTHORIZATION`，没有上传素材、调用远程接口或产生费用。
- 当前成果已存为快照 `SNP-20260918T004726396Z-P28-FIVE-EPISODE-LOCAL-MASTERS`；首页与渲染队列均正确呈现五集试播状态。
- 当前 `P28-01` 仍为 `IN_PROGRESS`：本地完整链路和客观技术 QC 已跑通，下一步是逐集人工审片；远程上传和计费调用继续受显式确认约束。
