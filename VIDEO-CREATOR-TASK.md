# VIDEO-CREATOR-TASK.md

> Project: VideoCreator Engine  
> Purpose: Codex 驱动的半自动自媒体视频生产线（首发平台：微信视频号）  
> Status: ACTIVE  
> Version: V1.0  
> Updated: 2026-09-15  
> Execution model: Codex First / Human Final Publish  
> Single Source of Truth: **本文件是项目唯一任务事实源**
>
> 核心目标：用户只需输入一个选题，系统自动完成研究、脚本、分镜、素材路由、配音、剪辑、动效、字幕、质检、封面、标题、文案和标签，最终输出可直接人工发布的视频号“发布包”。
>
> 强制原则：**最终发布必须人工确认。**

---

# 0. 项目目标与边界

## 0.1 V1 最终目标

输入示例：

```text
做一期：
ChatGPT Plus 一个月 20 美元到底值不值？
60 秒，微信视频号。
```

系统自动输出：

```text
projects/<project-id>/
├── final.mp4
├── cover.png
├── title.md
├── caption.md
├── hashtags.md
├── script.md
├── storyboard.md
├── research.md
├── sources.md
├── asset-manifest.json
├── qc-report.md
└── run.json
```

验收标准：

- 能从一个自然语言选题生成完整项目。
- 能输出 9:16、1080×1920 成片。
- 默认视频长度 45～90 秒。
- 能自动生成脚本和逐秒分镜。
- 能处理已有视频、录屏、截图、图片。
- 能生成信息图、文字动效和 UI 动画。
- 能完成字幕、配音、BGM、混音。
- 能执行视频技术 QC 和内容 QC。
- 能生成标题、封面、描述、标签。
- 出错时支持局部重跑，不需要整条视频重新生成。
- 不自动发布微信视频号。
- 所有外部服务均通过 Provider/Adapter 层接入，禁止核心流程绑定单一 API。

---

# 1. 总体架构

```text
                    USER
                      │
                      ▼
                  Codex CLI
                      │
                      ▼
             video-creator Skill
                      │
      ┌───────────────┼────────────────┐
      │               │                │
      ▼               ▼                ▼
   Research         Script         Storyboard
      │               │                │
      └───────────────┼────────────────┘
                      ▼
                 Asset Router
          ┌───────────┼─────────────┐
          │           │             │
          ▼           ▼             ▼
     Real Media   HyperFrames   Generative Media
          │           │             │
          └───────────┼─────────────┘
                      ▼
               Voice Provider
                      ▼
                 video-use
                      ▼
                  FFmpeg
                      ▼
               QC / Auto Fix
                      ▼
                 Packaging
                      ▼
             微信视频号发布包
                      ▼
                人工确认发布
```

---

# 2. 技术栈锁定

## 2.1 V1 核心依赖

| 模块 | 选择 | 定位 | V1 |
|---|---|---|---|
| 总调度 | Codex | 任务理解、决策、编排 | REQUIRED |
| 总编排 | 自建 `video-creator` Skill | 项目主入口 | REQUIRED |
| 视频剪辑 | `video-use` | 原素材理解、剪辑、字幕、自检 | REQUIRED |
| 动效 | `HyperFrames` | 文字、图表、UI、信息图、动态包装 | REQUIRED |
| 底层媒体 | FFmpeg | 转码、合成、音视频处理 | REQUIRED |
| 配音 | Provider 模式，首选 Fish Audio | 中文 TTS | REQUIRED |
| 高级动画 | Remotion Skills | 复杂程序化视频 | OPTIONAL |
| AI 素材 | Generative Media Skills | 缺失素材补全 | OPTIONAL |
| 中文流程参考 | video-recap-skills | 借鉴，不强绑定 | REFERENCE |
| 快速实验 | MoneyPrinterTurbo | 题材验证，不进核心 | REFERENCE |

## 2.2 禁止项

- 不把 MoneyPrinterTurbo 作为主生产引擎。
- 不依赖名称不明确的 `System 2 Skills`。
- 不使用来源不明的 `Video Cut Skill` 作为核心。
- 不默认使用 AI 数字人。
- 不把所有视频都强制经过 HyperFrames + Remotion。
- 不把 ASR / TTS / LLM / 图像模型写死。
- 不在 V1 自动发布平台内容。

---

# 3. 工程目录

```text
video-creator/
├── AGENTS.md
├── VIDEO-CREATOR-TASK.md
├── README.md
├── .env.example
├── config/
│   ├── app.yaml
│   ├── providers.yaml
│   ├── platforms.yaml
│   ├── quality.yaml
│   └── brand.yaml
├── skill/
│   └── video-creator/
│       ├── SKILL.md
│       ├── research/
│       ├── topic/
│       ├── script/
│       ├── storyboard/
│       ├── assets/
│       ├── voice/
│       ├── edit/
│       ├── motion/
│       ├── qc/
│       └── packaging/
├── adapters/
│   ├── llm/
│   ├── search/
│   ├── asr/
│   ├── tts/
│   ├── image/
│   ├── video/
│   ├── motion/
│   └── publish/
├── templates/
│   ├── wechat-channel/
│   ├── douyin/
│   ├── xiaohongshu/
│   └── youtube-shorts/
├── brand/
│   ├── fonts/
│   ├── intro/
│   ├── outro/
│   ├── subtitle/
│   ├── cover/
│   └── audio/
├── scripts/
├── tests/
├── logs/
├── cache/
├── archive/
└── projects/
```

---

# 4. 核心设计原则

## 4.1 编排器只负责编排

`video-creator` 不直接承担全部具体能力。

它只负责：

```text
理解任务
→ 创建项目
→ 生成执行计划
→ 调用子模块
→ 校验阶段输出
→ 决定是否重试
→ 决定是否降级
→ 生成最终发布包
```

外部工具必须通过 Adapter 接入。

---

## 4.2 Provider 可替换

统一接口：

```text
ASRProvider
TTSProvider
LLMProvider
ImageProvider
VideoProvider
SearchProvider
MotionProvider
PublishProvider
```

示例：

```text
TTSProvider
├── FishAudio
├── ElevenLabs
├── EdgeTTS
└── LocalTTS
```

未来替换供应商不能修改主工作流。

---

## 4.3 阶段产物可复用

每一步必须落盘。

```text
research.json
topic.json
script.json
storyboard.json
assets.json
voice.json
edit.json
motion.json
qc.json
package.json
```

后续可以：

```text
rerun storyboard
rerun scene 07
rerun voice
rerun cover
rerun qc
```

禁止每次从头执行。

---

## 4.4 每个镜头具有唯一 ID

格式：

```text
SC001
SC002
SC003
...
```

每个镜头必须包含：

```json
{
  "scene_id": "SC007",
  "start": 18.2,
  "end": 23.6,
  "spoken_text": "",
  "caption": "",
  "visual_type": "",
  "asset_refs": [],
  "motion": "",
  "status": ""
}
```

支持：

```text
只重做 SC007
```

---

# 5. 平台 V1 规格：微信视频号

## 5.1 默认成片

```text
aspect_ratio: 9:16
resolution: 1080x1920
duration_target: 45-90s
fps: 30
codec: H.264
audio: AAC
```

## 5.2 标准 60 秒结构

```text
0～3 秒      Hook
3～10 秒     问题/冲突
10～35 秒    实测/演示/证据
35～50 秒    对比/真相
50～60 秒    结论/CTA
```

## 5.3 视觉策略

优先级：

```text
1. 真实录屏
2. 真实截图
3. 实拍/真实产品图
4. 授权素材
5. HyperFrames 信息图
6. AI 图片/AI 视频
```

避免全程 AI 生成画面。

---

# 6. 内容定位

V1 主方向：

> **普通人的 AI + 数码工具避坑**

内容比例：

```text
50% AI 实测
30% 实用教程
20% 消费避坑
```

暂不混入：

- 情感
- 育儿
- 旅游
- 泛汽车
- 新闻搬运
- 纯 AI 资讯

第一阶段先形成清晰账号标签。

---

# 7. 选题评分系统

每个选题生成：

```json
{
  "traffic_value": 0,
  "commercial_value": 0,
  "evergreen_score": 0,
  "production_cost": 0,
  "evidence_strength": 0,
  "originality": 0,
  "risk_score": 0,
  "total_score": 0
}
```

V1 推荐权重：

```text
traffic_value       20%
commercial_value    20%
evergreen_score     20%
evidence_strength   15%
originality         15%
production_cost     10%
```

风险单独作为过滤条件。

所有分数为 0～100；`production_cost` 原始分越高代表制作代价越高，总分按 `100 - production_cost` 计入。风险分不参与加权总分，默认达到 70 时单独拦截。权重和门槛配置在 `config/topic-scoring.json`。

默认：

```text
total_score < 60
→ 不自动进入制作
```

---

# 8. P0 — 项目初始化

## P0-01 创建项目骨架
Status: PASS

执行记录（2026-09-15）：

- Git commit: `821f58a`（项目骨架）
- 环境检查：Python 3.10.2、Node.js 22.23.1、FFmpeg 9.0、Codex CLI 0.153.4 全部通过。
- 结果：PASS；下一任务：P0-02。

任务：

- 创建工程目录。
- 初始化 Git。
- 创建 `.gitignore`。
- 创建 `.env.example`。
- 创建 `logs/ cache/ archive/ projects/`。
- 创建基础 README。
- 固定 Python / Node / FFmpeg 版本检查。

验收：

```text
PASS: project structure valid
PASS: git initialized
PASS: ffmpeg available
PASS: node available
PASS: codex available
```

---

## P0-02 创建统一配置系统
Status: PASS

执行记录（2026-09-15）：

- Git commit: `610df09`（统一 YAML 配置）
- 五份配置均通过 YAML 解析及字段一致性检查；凭据仅以环境变量名引用，`.env.example` 不含真实密钥。
- 微信视频号默认规格、Provider 切换和人工发布确认已配置；未定义的品牌及其他平台细节保持待定。
- 结果：PASS；下一任务：P0-03。

创建：

```text
config/app.yaml
config/providers.yaml
config/platforms.yaml
config/quality.yaml
config/brand.yaml
```

要求：

- 密钥不能写入 Git。
- Provider 可切换。
- 平台参数配置化。
- 视频规格配置化。

---

## P0-03 建立日志规范
Status: PASS

执行记录（2026-09-15）：

- Git commit: `cc7937d`（安静终端与详细日志 runner）
- 已验证成功/失败摘要、详细日志落盘、常见凭据脱敏、退出码传递及日志文件 Git 忽略规则。
- 结果：PASS；下一任务：P1-01。

目录：

```text
logs/
```

终端默认安静模式：

```text
RUN <TASK>
PASS / FAIL
RESULT
NEXT
```

详细日志写文件。

---

# 9. P1 — video-creator 总编排 Skill

## P1-01 创建 SKILL.md
Status: PASS

执行记录（2026-09-15）：

- Git commit: `b4f85c7`（video-creator 主编排 Skill）
- `skill-creator` quick validator 通过；Skill 覆盖 topic、platform、duration、tone、target_audience、source_mode、voice、asset_strategy 八个必需字段。
- 结果：PASS；下一任务：P1-02。

Skill 入口：

```text
/video-creator
```

支持自然语言：

```text
做一期：
40 块钱随身 WiFi 到底是不是智商税？
60 秒，视频号。
```

必须解析：

```text
topic
platform
duration
tone
target_audience
source_mode
voice
asset_strategy
```

---

## P1-02 创建项目 ID
Status: PASS

执行记录（2026-09-15）：

- Git commit: `b46f7cd`（项目 ID 生成器）
- 已验证 `YYYYMMDD-slug`、Asia/Shanghai 日期、目录原子创建、同 ID 数字后缀、中文回退 slug、输入清洗和无效日期拒绝。
- 结果：PASS；下一任务：P1-03。

格式：

```text
YYYYMMDD-slug
```

示例：

```text
20260915-chatgpt-plus-worth-it
```

---

## P1-03 创建状态机
Status: PASS

执行记录（2026-09-15）：

- Git commit: `63c3a16`（项目生命周期状态机）
- 新项目会在 `run.json` 初始化为 `CREATED`；状态只能按定义顺序推进，转换历史以 UTC 时间记录。
- 已验证阶段顺序、持久化、人工发布确认门禁及项目 ID 创建集成；单元测试 3 项通过。
- 结果：PASS；下一任务：P1-04。

阶段：

```text
CREATED
RESEARCHED
SCRIPTED
STORYBOARDED
ASSETS_READY
VOICE_READY
EDITED
QC_PASS
PACKAGED
READY_FOR_REVIEW
PUBLISHED_MANUALLY
```

---

## P1-04 支持 Resume
Status: PASS

执行记录（2026-09-15）：

- Git commit: `7f7c556`（项目恢复点命令）
- Resume 读取 `run.json`，跳过已完成阶段并返回首个未完成阶段；`READY_FOR_REVIEW` 停在人审，`PUBLISHED_MANUALLY` 返回完成状态。
- 已验证恢复点计算、终态处理、命令行读取及状态不被 Resume 修改；单元测试 6 项通过。
- 结果：PASS；下一任务：P1-05。

例如：

```text
video-creator resume <project-id>
```

读取 `run.json`，从未完成阶段继续。

---

## P1-05 支持局部重跑
Status: PASS

执行记录（2026-09-15）：

- Git commit: `88c79ff`（局部重跑范围规划）
- CLI 支持 scene、voice、cover、QC 四类计划；校验目标阶段、场景 ID 和人工发布终态，并列出保留产物、重建产物及恢复检查点。计划不修改 `run.json`，单镜头计划保留其它场景和配音。
- 已验证 11 项单元测试、Python 编译检查和 Skill quick validator。
- 当前阶段执行器尚未接入，命令只输出计划，不会声称已生成新产物；下一任务：P2-01。

示例：

```text
video-creator rerun <project-id> scene SC007
video-creator rerun <project-id> voice
video-creator rerun <project-id> cover
video-creator rerun <project-id> qc
```

核心验收：

```text
修改 SC007 不得重新生成完整视频项目
```

---

# 10. P2 — Research / Topic

## P2-01 Research 模块
Status: PASS

执行记录（2026-09-15）：

- Git commit: `5e0a5a7`（带来源引用的研究产物生成）
- 新增 Research 输入 Schema 和 CLI；校验来源 URL、核心事实、证据摘要及 source reference，生成 `research.json`、`research.md`、`sources.md`，成功后推进状态至 `RESEARCHED`。
- 内容覆盖核心事实、FAQ、正反观点、价格/规格/版本、素材方向和风险；不接受没有来源支持的核心事实。
- 已验证 16 项单元测试、Schema 与样例一致性、Python 编译检查和 Skill quick validator。
- 当前 Search Provider 尚未配置，采集由 VideoCreator Skill/Codex 搜索能力完成，再交给模块校验和落盘；下一任务：P2-02。

输入：

```text
topic
```

输出：

```text
research.md
sources.md
research.json
```

内容：

- 核心事实
- 可验证数据
- 用户常见问题
- 正反观点
- 价格/规格/版本
- 可用素材方向
- 风险信息

---

## P2-02 事实来源策略
Status: PASS

执行记录（2026-09-15）：

- Git commit: `8f13d05`（研究来源优先级校验）
- 输入 Schema 与 Research 模块现在要求来源分级，并按“官方来源 > 原始文档 > 权威媒体 > 高质量社区 > 搜索摘要”排序来源和事实引用。
- 每个事实条目继续强制引用已登记的 source ID；搜索摘要只保留为检索线索，不可单独支撑事实、FAQ、观点、价格/规格/版本或风险。
- Research Skill 补充来源分类标准和直达页面核验要求。已验证 18 项单元测试、Schema 校验、编译检查和 Skill quick validator。
- 结果：PASS；下一任务：P2-03。

优先：

```text
官方来源
> 原始文档
> 权威媒体
> 高质量社区
> 搜索摘要
```

每个关键事实保存 source reference。

---

## P2-03 Topic Scoring
Status: PASS

执行记录（2026-09-15）：

- Git commit: `8043f4b`（主题评分与风险过滤）
- 新增 `video-creator score`，读取已完成的 `research.json` 和带理由的五项 Skill 评估，生成 `topic.json`；证据强度按事实来源等级及不同发布方交叉支持情况计算，风险分按已记录风险严重度计算。
- 总分使用本节权重，制作成本反向计入；总分低于 60 或风险分达到 70 时分别触发制作门禁和风险过滤。评分不推进项目生命周期。
- 已验证 23 项单元测试、输入 Schema、编译检查和 Skill quick validator。
- 结果：PASS；下一任务：P3-01。

自动计算：

```text
traffic_value
commercial_value
evergreen_score
production_cost
evidence_strength
originality
risk_score
```

---

# 11. P3 — Script

## P3-01 视频号脚本模板
Status: PASS

执行记录（2026-09-15）：

- Git commit: `0d80805`（微信视频号六段脚本模板）
- 新增 `video-creator script`，按 Hook、Problem、Evidence、Comparison、Conclusion、CTA 固定顺序校验输入，要求 Evidence 至少引用一条已核验的非搜索摘要来源。
- 脚本命令校验项目评分门槛和来源编号，生成 `script.json`、`script.md`，成功后将状态从 `RESEARCHED` 推进到 `SCRIPTED`；校验失败或已有产物时不覆盖、不推进状态。
- 已验证 31 项单元测试、Draft 2020-12 输入 Schema、Python 编译、CLI 帮助和 Skill quick validator。
- 结果：PASS；下一任务：P3-02。

默认：

```text
Hook
Problem
Evidence
Comparison
Conclusion
CTA
```

---

## P3-02 口语化
Status: PASS

执行记录（2026-09-15）：

- Git commit: `174fd3a`（口语化脚本规则与校验）
- 脚本输入现在要求 Hook 标记结论、反常识或冲突类型，并校验开场第一句与标记相符；Hook 模板明确对应开头 3 秒。
- 新增可配置的脚本风格规则，拦截论文式表达、机械连接词、超长句和逗号过多的复合句；Skill 补充自然中文口播和朗读检查要求。
- 已验证 35 项单元测试、Draft 2020-12 输入 Schema、Python 编译、JSON 配置和 Skill quick validator。
- 结果：PASS；下一任务：P3-03。

要求：

- 禁止论文式语言。
- 禁止过长句子。
- 一句话一个信息点。
- 中文口播自然。
- 避免“首先、其次、最后”机械结构。
- 开头 3 秒必须给结论、反常识或明确冲突。

---

## P3-03 时长估算
Status: PASS

执行记录（2026-09-15）：

- Git commit: `e467926`（脚本时长估算与自动压缩）
- `script.json` 和 `script.md` 输出 `estimated_duration`、`word_count`、`speech_rate` 与目标时长；字数按汉字逐字计数、连续非汉字字母/数字串按一个单位计，估算语速默认为每分钟 220 个口播单位。
- 默认目标为 60 秒，支持视频号 45～90 秒目标；Hook 估算不得超过开头 3 秒。
- 超时后按配置顺序自动删除 Problem、Comparison、Conclusion 中明确标记为可删的完整补充句，保留 Hook、Evidence 和 CTA；删减后仍超时则拒绝落盘和状态推进，交由 Script Skill 精简重试。
- 已验证 39 项单元测试、Draft 2020-12 输入 Schema、Python 编译、JSON 配置和 Skill quick validator。
- 结果：PASS；下一任务：P4-01。

脚本输出：

```text
estimated_duration
word_count
speech_rate
```

若超出目标时长：

自动压缩。

---

# 12. P4 — Storyboard

## P4-01 逐镜头分镜
Status: PASS

执行记录（2026-09-15）：

- Git commit: `1da673c`（逐镜头分镜生成与校验）
- 新增 `video-creator storyboard`，将完成脚本拆为带时间、口播、字幕、画面说明、画面类型、素材查询、运镜、转场和来源的 `storyboard.json`、`storyboard.md`。
- 校验镜头从 `SC001` 连续编号、时间从 0 秒无缝衔接到脚本目标时长、口播完整覆盖已审定脚本；已引用来源必须出现在至少一个证据画面中。通过后状态从 `SCRIPTED` 推进到 `STORYBOARDED`。
- 已验证 45 项单元测试、Draft 2020-12 输入 Schema、Python 编译、CLI 和 Skill quick validator。
- 结果：PASS；下一任务：P4-02。

每个镜头：

```text
scene_id
start
end
spoken_text
caption
visual_description
visual_type
asset_query
motion
transition
source
```

---

## P4-02 Visual Type
Status: PASS

执行记录（2026-09-15）：

- Git commit: `0efc2ef`（分镜画面类型枚举校验）
- `visual_type` 现在只接受 screen_recording、screenshot、real_video、real_image、stock、hyperframes、remotion、ai_image、ai_video、text_only、chart、comparison。
- 命令、输入 Schema、模板与 Storyboard Skill 一致校验，阻止资产路由无法处理的画面类型。
- 已验证 46 项单元测试、Draft 2020-12 输入 Schema、Python 编译和 Skill quick validator。
- 结果：PASS；下一任务：P4-03。

允许：

```text
screen_recording
screenshot
real_video
real_image
stock
hyperframes
remotion
ai_image
ai_video
text_only
chart
comparison
```

---

## P4-03 Storyboard Review
Status: PASS

执行记录（2026-09-15）：

- Git commit: `f3baead`（自动分镜视觉审查）
- 新增 `video-creator review-storyboard`，输出可复跑的 `storyboard-review.json`、`storyboard-review.md`，不改变项目状态。
- 自动检查连续 8 秒以上无视觉变化、重复画面、连续纯字幕堆叠、来源证据画面、前三秒 Hook 视觉和关键结论视觉强化；失败项以 `NEEDS_REVISION` 留在审查报告中。
- 已验证 49 项单元测试、Python 编译和 Skill quick validator。
- 结果：PASS；下一任务：P5-01。

自动检查：

- 是否连续 8 秒以上无视觉变化。
- 是否存在重复画面。
- 是否存在纯字幕堆叠。
- 是否有足够证据画面。
- Hook 是否视觉匹配。
- 关键结论是否有视觉强化。

---

# 13. P5 — Asset Router

## P5-01 素材优先级
Status: PASS

执行记录（2026-09-15）：

- Git commit: `1927241`（素材优先级路由）
- 新增可校验的素材路由配置和选择器，按真实素材、授权素材、HyperFrames、生成式媒体固定顺序选择首个可用路由。
- 路由不能跳过高优先级的可用素材；没有可用候选时返回 `MISSING_ASSET`，由后续缺失素材流程处理。
- 已验证 52 项单元测试、Python 编译和 Skill quick validator。
- 结果：PASS；下一任务：P5-02。

必须按照：

```text
真实素材
→ 授权素材
→ HyperFrames
→ Generative Media
```

---

## P5-02 Asset Manifest
Status: PASS

执行记录（2026-09-15）：

- Git commit: `6e06222`（可追溯资产清单）
- 新增 `video-creator assets`，校验项目内真实文件及分镜编号，记录素材类型、路径、来源、授权、生成标记和 Provider，并计算 SHA-256 校验和。
- 生成 `asset-manifest.json`；拒绝目录穿越、缺失文件、重复资产编号和缺失生成 Provider。
- 已验证 53 项单元测试、Draft 2020-12 输入 Schema 和 Python 编译。
- 结果：PASS；下一任务：P5-03。

创建：

```text
asset-manifest.json
```

记录：

```text
asset_id
scene_id
type
path
source
license
generated
provider
checksum
```

---

## P5-03 Missing Asset
Status: PASS

执行记录（2026-09-15）：

- Git commit: `cdf28cc`（缺失素材恢复路由）
- 素材缺失统一返回 `MISSING_ASSET`，按搜索、生成、信息图替代、请求用户材料选择首个可用恢复动作。
- 没有自动恢复能力时回退到请求用户材料，保留项目而不报废任务。
- 已验证 54 项单元测试和 Python 编译。
- 结果：PASS；下一任务：P6-01。

缺失素材不得直接报废任务。

返回：

```text
MISSING_ASSET
```

系统选择：

```text
search
→ generate
→ replace with infographic
→ request user material
```

---

# 14. P6 — HyperFrames

## P6-01 安装与固定版本
Status: PASS

执行记录（2026-09-15）：
- Git commit: `5012a10`
- HyperFrames 固定为 `v0.8.40` / `cfe5dcfad310ced2a5844998628daa2b8a0f53d7`，安装到忽略提交的 `.dependencies/hyperframes`。
- 新增 `dependency-manifest.json` 和依赖安装/校验脚本，升级策略固定为手动更新 tag 与 commit。
- 验证：实际安装与来源校验通过；全量 57 项测试通过。
- 结果：PASS；下一任务：P6-02。

要求：

- 固定 Git commit/tag。
- 不直接追 latest。
- 写入 dependency manifest。

---

## P6-02 默认动效
Status: PASS

执行记录（2026-09-15）：
- Git commit: `bc28923`
- 新增 `config/hyperframes-motion.json`，为标题、数据、比较表、UI、卡片、价格、排行榜、步骤、流程图和强调文字定义独立默认动效。
- 新增可校验的动效计划构建器，输出 30 fps、可 seek 的 GSAP 计划，并拒绝未知内容类型与重复元素。
- 验证：全量 61 项测试通过。
- 结果：PASS；下一任务：P6-03。

用于：

- 标题
- 数据
- 比较表
- UI
- 卡片
- 价格
- 排行榜
- 步骤
- 流程图
- 强调文字

---

## P6-03 Style Presets
Status: PASS

执行记录（2026-09-15）：
- Git commit: `ccfa9f8`
- 在 `brand/motion/` 新增 `minimal`、`tech`、`review`、`warning`、`comparison`、`tutorial` 六套预设。
- 每套预设固定调色板、中文字体、表面样式、动效节奏与转场；预设应用器在不修改基础计划的前提下生成风格化计划。
- 验证：六套 JSON 均通过解析与结构校验；全量 64 项测试通过。
- 结果：PASS；下一任务：P8-01（P7 为 V1 OPTIONAL，本轮未触发）。

创建：

```text
minimal
tech
review
warning
comparison
tutorial
```

---

# 15. P7 — Remotion

## P7-01 安装 Remotion Skills
Status: TODO

仅用于：

```text
复杂时间线
复杂字幕
组件化动画
地图
高级数据动画
重复模板批量渲染
```

---

## P7-02 Motion Router
Status: TODO

规则：

```text
普通动效
→ HyperFrames

高级动效
→ Remotion
```

禁止无理由双引擎执行。

---

# 16. P8 — Voice

## P8-01 TTS Provider
Status: PASS

执行记录（2026-09-15）：
- Git commit: `0d82bf6`
- 新增统一 `synthesize(text, voice, speed, emotion)` 接口和 Fish Audio S2-Pro 适配器，支持 Provider voice ID、语速与情绪提示。
- Provider 顺序固定为 Fish Audio → ElevenLabs → EdgeTTS → Local；未配置可用 Provider 时明确失败，不进行隐藏计费回退。
- 验证：模拟请求覆盖鉴权、请求体、输入校验和路由优先级；全量 67 项测试通过。
- 结果：PASS；下一任务：P8-02。

接口：

```text
synthesize(text, voice, speed, emotion)
```

首选：

```text
Fish Audio
```

备选：

```text
ElevenLabs
EdgeTTS
Local
```

---

## P8-02 Voice Cache
Status: PASS

执行记录（2026-09-15）：
- Git commit: `ed2ab72`
- 新增内容寻址 Voice Cache，以 `text + voice + speed + provider` 为核心身份，并将影响声音的 emotion 作为缓存变体。
- 每个缓存键使用文件锁并在锁内二次检查，避免并发重复计费；缓存音频与元数据均校验 SHA-256。
- 损坏或不一致的缓存明确失败，不自动重新生成；命中结果标记 `billable_generation=false`。
- 验证：全量 71 项测试通过。
- 结果：PASS；下一任务：P8-03。

相同：

```text
text + voice + speed + provider
```

命中缓存时不得重复计费生成。

---

## P8-03 中文口播优化
Status: PASS

执行记录（2026-09-15）：
- Git commit: `f12e736`
- 新增配置化中文口播优化器，覆盖整数、年份、百分比、金额、网络代际、英文缩写、产品名和中英文边界。
- 支持 `{pause:short}`、`{pause:long}`、`**强调**` 与情绪参数；Fish Audio 输出 S2-Pro 控制提示，其它 Provider 使用中文标点回退。
- 新增 Voice Skill，固定“先优化、后缓存、再合成”的调用顺序。
- 验证：全量 78 项测试通过。
- 结果：PASS；下一任务：P9-01。

支持：

- 数字读法
- 英文缩写
- 产品名
- 停顿
- 情绪
- 强调
- 中英文混读

---

# 17. P9 — video-use 剪辑核心

## P9-01 集成 video-use
Status: PASS

执行记录（2026-09-15）：
- Git commit: `122356a`
- video-use 固定到官方仓库提交 `9575612f066aa517354790a645fd90f9f95a743b`，使用隔离 Python 环境；项目本地 `ffprobe 9.0.1` 固定下载地址与 SHA-256。
- 新增配置和 Adapter，覆盖原始视频理解、停顿删除、口癖删除、裁切、字幕、音频同步、B-roll、Overlay 与基础自评。
- 固定字幕最后叠加、词边界剪切、30–200ms 剪点边距、30ms 音频淡入淡出、Overlay 时间偏移、转录缓存和最多三轮自评规则。
- 真实媒体验证：2 秒 H.264/AAC 测试素材经 EDL 裁为约 1.5 秒，成功生成预览与时间线检查图；未调用付费转录。
- 验证：依赖提交、媒体工具、隔离环境和 helpers 全部通过；全量 85 项测试通过。
- 结果：PASS；下一任务：P9-02。

负责：

- 原始视频理解
- 删除停顿
- 删除口癖
- 裁切
- 字幕
- 音频同步
- B-roll
- Overlay
- 基础自评

---

## P9-02 禁止强耦合 ElevenLabs
Status: PASS

执行记录（2026-09-15）：
- Git commit: `cf7059d`
- 新增统一 ASRProvider 契约，ElevenLabs、Whisper API、Local Whisper 与自定义 Provider 均输出 video-use 可用的逐词时间戳。
- 云端 Provider 在接口层强制要求媒体上传授权；Local Whisper 明确不上传媒体。
- 转录缓存绑定源文件 SHA-256、Provider、语言和说话人数，元数据不进入 video-use 的转录 JSON 扫描范围。
- 验证：ASR 契约、路由、授权、缓存和逐词格式通过；全量 91 项测试通过。
- 结果：PASS；下一任务：P9-03。

如果 video-use 默认依赖特定 ASR：

封装 Adapter。

最终支持：

```text
ASRProvider
├── ElevenLabs
├── Whisper
└── Other
```

---

## P9-03 EDL
Status: PASS

执行记录（2026-09-15）：
- Git commit: `e775e5e`
- 新增 `edit/edit-decision-list.json` 管理器，每个保留区间包含稳定 `decision_id` 和非空决策理由。
- 记录源文件 SHA-256、渲染指纹、revision 与 parent_revision；源文件变化时阻止使用旧决策重渲染。
- 创建、局部修改和回滚均保存不可覆盖的编号历史；修改和回滚使用 expected_revision 防止并发覆盖。
- 验证：创建、局部修改、旧版本拒绝、回滚、源变化检测与重复创建拒绝通过；全量 97 项测试通过。
- 结果：PASS；下一任务：P10-01。

剪辑必须输出可追踪 EDL：

```text
edit-decision-list.json
```

方便：

```text
回滚
局部修改
重渲染
```

---

# 18. P10 — FFmpeg Finalizer

## P10-01 Final Merge
Status: PASS

执行记录（2026-09-15）：
- Git commit: `3efd9c6`
- 新增独立 FFmpeg Finalizer，统一处理视频合并、转场、音轨延迟与混音、-14 LUFS 音量标准化、尺寸、FPS、码率、编码和 faststart MP4 封装。
- 使用结构化 FinalMergeSpec 构建参数列表，不执行未校验的 shell 字符串；限制受支持的编码器、容器和转场。
- 真实媒体验证：两段不同尺寸视频与两条音轨成功输出 360×640、30fps、H.264/AAC、2.2 秒 MP4，并生成文件 SHA-256。
- 验证：全量 102 项测试通过。
- 结果：PASS；下一任务：P10-02。

FFmpeg 负责：

- 视频合并
- 音轨混合
- 音量标准化
- 转场
- 编码
- 尺寸
- FPS
- 码率
- 封装

---

## P10-02 输出标准
Status: PASS

执行记录（2026-09-15）：
- Git commit: `9f20275`
- 默认交付规格固定为 1080×1920、30fps、H.264、AAC、48kHz 音频和 MP4；正式成片必须包含视频流和音频流。
- 标准规格由统一工厂创建；渲染后使用 ffprobe 读取实际媒体流，校验分辨率、FPS、编码、采样率、容器、时长和文件大小，参数或实际输出不符合时返回明确失败项。
- 真实媒体验证：成功渲染并探测 1080×1920、30fps、H.264/AAC、48kHz MP4；环境检查与全量 108 项测试通过。
- 结果：PASS；下一任务：P11-01。

默认：

```text
1080x1920
30 fps
H.264
AAC
.mp4
```

---

# 19. P11 — QC

## P11-01 Technical QC
Status: PASS

执行记录（2026-09-15）：
- Git commit: `047b947`
- 新增真实媒体技术质检：ffprobe 校验媒体流，FFmpeg 完整解码并扫描黑帧、冻结帧、静音和音频峰值，同时检查分辨率、宽高比、FPS、编码、时长及音画起止偏差。
- 字幕布局使用 0～1 归一化坐标，逐条检查安全区和视频号 UI 保留区；缺少字幕布局证据不会宣告通过。
- 真实 1080×1920、30fps、H.264/AAC 媒体冒烟验证通过；全量 113 项测试通过。
- 结果：PASS；下一任务：P11-02。

检查：

```text
分辨率
宽高比
FPS
Codec
总时长
黑帧
冻结帧
静音
爆音
音画不同步
字幕越界
字幕遮挡
编码失败
文件损坏
```

---

## P11-02 Content QC
Status: PASS

执行记录（2026-09-15）：
- Git commit: `d0421c1`
- 内容审查输入必须逐项记录十项检查的 PASS/FAIL、证据和已知研究来源编号，拒绝缺项、重复项及未知来源。
- 程序独立检查重复口播、无来源绝对化表述、平台敏感词、首 3 秒 Hook、结论和 CTA；结构化规则不能被乐观的人工结论覆盖。
- 全量 118 项测试通过。
- 结果：PASS；下一任务：P11-03。

检查：

```text
错别字
事实错误
数字错误
品牌名称
平台敏感表述
重复内容
无依据绝对化表述
首 3 秒 Hook
结论清晰度
CTA
```

---

## P11-03 Visual QC
Status: PASS

执行记录（2026-09-15）：
- Git commit: `4a7c45a`
- 视觉分析要求逐镜头提供画面指纹、留白占比、裁切结论、最低文字对比度和关键信息框，缺失、重复或未知镜头均拒绝。
- 结合分镜时长和字幕计算单镜头过长、相邻重复画面、字幕过密、异常留白、裁切错误、视频号 UI 遮挡及文字背景对比不足。
- 全量 122 项测试通过。
- 结果：PASS；下一任务：P11-04。

检查：

```text
单镜头过长
画面重复
字幕过密
留白异常
画面裁切错误
关键信息被 UI 遮挡
背景与文字对比不足
```

---

## P11-04 Auto Fix
Status: PASS

执行记录（2026-09-15）：
- Git commit: `2ed5e37`
- 自动修复策略只允许字幕位置、音量、空镜、转码、轻微时长和字幕断句，并通过可替换执行器派发；未知类别直接拒绝。
- 核心事实、结论、商业推荐或敏感内容会阻止整批自动执行并转回脚本审核；修复后强制重跑全部 QC，旧报告不能用于放行。
- 汇总器严格核验技术、内容和视觉检查全集，生成 `qc.json`、`qc-report.md`，仅在三类报告全部通过时推进到 `QC_PASS`。
- 环境检查与全量 127 项测试通过。
- 结果：PASS；下一任务：P12-01。

允许自动修复：

```text
字幕位置
音量
空镜
转码
轻微时长
字幕断句
```

不允许自动修改：

```text
核心事实
结论
商业推荐
敏感内容
```

这些必须重新进入脚本审核。

---

# 20. P12 — Packaging

## P12-01 视频号发布包
Status: PASS

执行记录（2026-09-15）：
- Git commit: `beb7ad9`
- 新增视频号发布包构建器，只接受 `QC_PASS` 且汇总质检通过的项目；七个必需产物缺失、空白、符号链接或封面格式错误时中止。
- 产物复制到独立 `publish-package/`，逐文件校验复制前后 SHA-256，并生成 `package.json`；成功后推进到 `PACKAGED`。
- 发布模式固定为人工确认，构建器不包含上传或发布动作；全量 131 项测试通过。
- 结果：PASS；下一任务：P12-02。

输出：

```text
final.mp4
cover.png
title.md
caption.md
hashtags.md
sources.md
qc-report.md
```

---

## P12-02 封面
Status: PASS

执行记录（2026-09-15）：
- Git commit: `e8c49db`
- 封面输入严格要求 2～3 个候选，每个核心文案含 3～10 个可见字符并明确表达问题，辅助文字限制为一行短句。
- 使用固定 Pillow 版本和中文字体生成 1080×1920 PNG，核心字号不低于 120px；候选清单记录尺寸、字号和 SHA-256，选择时重新校验文件后写入 `cover.png`。
- 实际渲染并目视检查深色竖屏候选，移动端层级与文字可读性通过；环境检查与全量 135 项测试通过。
- 结果：PASS；下一任务：P12-03。

要求：

- 3～10 个核心字。
- 移动端可读。
- 一眼知道问题。
- 禁止密集小字。
- 支持 2～3 个候选封面。

---

## P12-03 标题候选
Status: PASS

执行记录（2026-09-15）：
- Git commit: `f9ad13f`
- 发布文案输入至少包含搜索型、冲突型和结果型标题各一个，并校验关键词、类型语义、移动端长度、唯一性和无依据营销词。
- 程序按关键词、长度和类型表达自动评分，输出唯一推荐及评分理由；同时生成发布包需要的 `title.md`、`caption.md`、`hashtags.md` 和追溯文件 `publication-copy.json`。
- 环境检查与全量 140 项测试通过。
- 结果：PASS；下一任务：P13-01。

至少生成：

```text
A: 搜索型
B: 冲突型
C: 结果型
```

最终推荐一个。

---

# 21. P13 — Human Review

## P13-01 Review Gate
Status: PASS

执行记录（2026-09-15）：
- Git commit: `2cf5843`
- 人工审核门禁重新计算发布包七个文件的大小和 SHA-256，并核对项目、平台、QC PASS、清单及人工发布配置；文件被修改或缺失时不推进状态。
- 验证通过后写入 `review-gate.json`，推进到 `READY_FOR_REVIEW`，终端完整显示交付清单和 `WAITING FOR HUMAN PUBLISH`。
- 环境检查与全量 144 项测试通过。
- 结果：PASS；下一任务：P13-02。

最终状态：

```text
READY_FOR_REVIEW
```

终端显示：

```text
FINAL READY

✓ final.mp4
✓ cover.png
✓ title
✓ caption
✓ hashtags
✓ sources
✓ QC PASS

WAITING FOR HUMAN PUBLISH
```

---

## P13-02 禁止 V1 自动发布
Status: PASS

执行记录（2026-09-15）：
- Git commit: `3461277`
- V1 策略永久拒绝微信自动上传、模拟点击发布、自动原创声明和自动商业标签，未知发布能力同样默认拒绝。
- 配置审计核对应用、平台和发布包均为人工确认；人工发布记录只在项目处于 `READY_FOR_REVIEW` 且用户明确确认已经发布后写入状态，不执行任何平台操作。
- 环境检查与全量 148 项测试通过。
- 结果：PASS；下一任务：P14-01。

V1 不调用：

- 微信自动发视频
- 模拟点击发布
- 自动原创声明
- 自动商业标签

发布由人工执行。

---

# 22. P14 — 第一阶段内容验证

目标：

```text
20 条视频
```

阶段内不做复杂平台扩张。

## P14-01 生产 5 条
Status: PASS

执行记录（2026-09-16）：
- Git commit: `6783027`
- 实际生成 5 个本地项目：`20260916-chatgpt-plus-worth-it`、`20260916-chatgpt-projects-guide`、`20260916-temporary-chat-privacy`、`20260916-chatgpt-search-guide`、`20260916-deep-research-use-cases`。
- 每条均为 56 秒、1080×1920、30fps、H.264/AAC/48kHz MP4，使用 OpenAI 官方来源、本地非计费中文语音、7 个动态信息卡镜头，并完成封面、标题文案和七文件发布包。
- 五条全部通过技术、内容、视觉 QC，稳定生成、风格、时长、字幕、语音和 Hook 六项均为 PASS；成片 SHA-256 已记录在 `validation/p14-first-five-report.json`。
- 独立验证器重新读取媒体流、项目状态、QC、发布包和成片哈希，确认 5 个项目均处于 `READY_FOR_REVIEW`；全部保持未发布。
- 目视抽检发现并修复首轮字幕断句问题后重新生成整批；环境检查、发布策略审计及全量 153 项测试通过。
- 结果：PASS；下一任务：P14-02。

验证：

- 稳定生成
- 风格
- 时长
- 字幕
- 语音
- Hook

---

## P14-02 生产 10 条
Status: PASS（平台观察待人工发布）

执行记录（2026-09-16）：
- 第二批五个主题：ChatGPT 记忆、自定义指令、文件上传、数据控制、语音模式；研究资料均引用 OpenAI 官方帮助中心，分批记录见 `validation/p14-second-five-report.json`。
- 两批合计十条真实成片，均为 56 秒、1080×1920、30fps、H.264/AAC，技术、内容、视觉 QC 和发布包均通过；独立验证报告见 `validation/p14-ten-report.json`，SHA-256 与项目内评估记录一致。
- 十个项目均处于 `READY_FOR_REVIEW`，尚未发布。按人工发布原则，当前没有可真实记录的平台数据；`validation/p14-metrics.json` 已建立十条空观察记录，均等待人工发布，不填造播放指标。
- `scripts/pilot_metrics.py record` 仅接受 `PUBLISHED_MANUALLY` 项目，要求平台来源、带时区的观察时间、播放量、完播率、3 秒和 5 秒留存及点赞、评论、收藏、转发、关注数；每次观察保留来源并追加记录。
- `scripts/check-env.sh`、`scripts/publish_policy.py audit` 均通过；全量测试 158 项通过。
- 结果：PASS；下一任务：P14-03。

开始观察：

```text
完播率
3 秒留存
5 秒留存
点赞
评论
收藏
转发
关注
```

发布前在 `validation/p14-metrics.json` 中保留空记录；人工发布并将项目状态推进至 `PUBLISHED_MANUALLY` 后，按平台后台数据录入带来源的观察值。

---

## P14-03 完成 20 条
Status: PASS

执行记录（2026-09-16）：
- 新增十条主题：学习模式、定时任务、Canvas、Images 2.5、应用权限、聊天记录搜索、分享链接、归档与删除、数据导出、提示词写法。对应官方来源与分批生产记录见 `validation/pilot-third-five.json`、`validation/pilot-fourth-five.json` 及两个批次报告。
- 四批二十条成片全部独立验证通过，均为 56 秒、1080×1920、30fps、H.264/AAC，处于 `READY_FOR_REVIEW`；汇总报告：`validation/p14-twenty-report.json`。
- 二十条从项目创建至待审核平均 18.112 秒，最长 19.147 秒。将“平均制作时间可接受”量化为不超过 30 秒/条，时间来自 `run.json` 的 `created_at` 到 `READY_FOR_REVIEW`。
- 工程修复口径：因项目缺陷而需要的项目级代码、时间线或渲染媒体更改；共 0/20 条，未修复比例 100%，逐条评估见 `validation/p14-repair-assessment.json`。公共生产器校准在最终验收运行前完成，文案和封面输入修改不计为工程修复。
- 局部重跑实测通过：对 `20260916-chatgpt-memory-management` 选择另一版封面，只更新封面及发布包校验和，成片和其余六个发布文件哈希不变，项目状态仍为 `READY_FOR_REVIEW`；运行记录在该项目的 `cover-rerun.json`，通过门槛报告 `validation/p14-milestone-report.json`。
- 指标台账从十条扩展至二十条，真实平台观察仍为零；二十个项目未发布，记录入口见 `validation/p14-metrics.json`。
- 全量 164 项测试、环境检查与人工发布策略审计通过。
- 结果：PASS；按路线进入下一阶段前，用户提到的 P15-01 尚未出现在本任务文档，范围待补充。

只有满足：

```text
20 条成功生成
≥ 90% 不需要工程级人工修复
局部重跑有效
平均制作时间可接受
```

才进入 V2。

验证口径：平均从 `CREATED` 到 `READY_FOR_REVIEW` 不超过 30 秒；工程修复按项目级修复记录逐条统计；局部重跑须实际更新目标产物并证明其他发布资产未改变。

---

# 23. V2 — 自动选题与数据闭环

状态：PAUSED（产品方向调整；不执行 V2-03 / V2-04）

目标：

```text
热点发现
→ 候选选题
→ 自动评分
→ 排期
→ 制作
→ 发布后数据
→ 回流
→ 优化下一条
```

## V2-01 Trend Discovery
- 微信生态可用信号
- 搜索趋势
- AI/数码新闻
- 社区热点
- 用户评论

### P15-01 验收范围：趋势发现框架
- 定义统一的 TrendSource/Adapter 接口和版本化信号格式，覆盖以上五类来源；各来源必须保留来源名称、采集时间、原始标题/主题、强度和可选来源链接。
- 先提供本地 JSON 文件适配器，支持用户提供或后续连接器提供的信号；不在核心流程中绑定平台 API，不抓取或上传私有内容，不要求凭据。
- 校验来源类型、时间、强度及链接；拒绝重复信号 ID；按主题和来源去重，并保留来源可追溯性。
- 输出 `topics/trends/YYYY-MM-DD.json`，通过测试覆盖五类来源、无效数据和重复数据。
- 趋势信号仅用于发现和排序，不视为事实核验、研究结果或制作准入。

状态：PASS（2026-09-16）

执行结果：
- 新增 `scripts/trend_discovery.py`：提供 `TrendSource` 可替换接口和五类来源的本地 JSON 导入适配器。
- 统一时间、链接、强度、来源类型和信号 ID 校验；相同来源重复主题保留最新/最强信号，输出保留来源归属。
- CLI 输出 `topics/trends/YYYY-MM-DD.json`，已验证重复 ID、错误时区/强度、私密作者字段和输出覆盖保护。
- 当前没有绑定微信、搜索、社区或评论平台的实时连接器；通过后续适配器接入，不要求核心流程改动。

## V2-02 自动选题池
输出：

```text
topics/YYYY-MM-DD.json
```

### P16-01 验收范围：自动选题池
- 从 P15 趋势信号按规范化主题聚合候选，按跨来源覆盖度、信号强度和时效性生成可解释的发现优先级。
- 输出日期化选题池，包含候选主题、引用信号、各项分值、总发现分和排序理由；相同输入与基准日期产生稳定排序。
- 选题池只产生待研究候选。进入制作仍须完成 `research.json` 核验和现有选题评分流程，不得把发现分当作 `topic_scoring` 制作准入分。
- 输出已存在时拒绝覆盖，避免无意丢失人工审核；不接入发布后数据回流（V2-03）。

状态：PASS（2026-09-16）

执行结果：
- 新增 `scripts/topic_pool.py` 和 `config/topic-pool.json`：按来源覆盖度（40%）、信号强度（40%）及 7 天半衰期时效性（20%）聚合排序。
- 输出 `topics/YYYY-MM-DD.json`，包含候选排名、评分依据和趋势来源记录；同一输入与基准日期产生稳定排序。
- 所有候选均标为待人工审核且不可直接制作；须先完成研究核验和 `topic_scoring`。
- 当前以本地测试输入贯通 P15→P16；没有真实来源输入时不生成虚构的当日候选文件。

运行示例：

```bash
python3 scripts/trend_discovery.py \
  --source wechat_ecosystem=/path/to/wechat.json \
  --source search_trend=/path/to/search.json \
  --source ai_digital_news=/path/to/news.json \
  --source community=/path/to/community.json \
  --source user_comment=/path/to/comments.json
python3 scripts/topic_pool.py topics/trends/YYYY-MM-DD.json
```

每个导入文件为 JSON 数组或 `{ "schema_version": 1, "signals": [...] }`；信号字段为 `signal_id`、`topic`、`title`、`source_name`、`observed_at`（含时区）、`strength`（0–100），并可选 `url`、`summary`。评论适配器不接受作者字段。

## V2-03 数据回流
记录：

```text
views
3s_retention
5s_retention
completion_rate
likes
comments
shares
follows
```

## V2-04 内容模型
分析：

```text
什么 Hook 有效
什么时长有效
什么题材有效
什么封面有效
什么 CTA 有效
```

## 小说 → 国风动漫视频号（新方向）

产品顺序：

```text
公开榜单与趋势信号
→ 小说候选库（热度记录 + 版本来源 + 权利状态）
→ 权利准入筛选
→ 小说剧情改编脚本
→ 分镜与临时视觉素材
→ 粗剪视频与人工审核
→ 后续再由自动选题池确定主 IP
```

边界：

- V2-01/V2-02 的基础趋势接口与候选排序代码保留，但不继续做 V2-03 数据回流或 V2-04 内容模型；自动选题池接入小说库排在工作流验证之后。
- “无版权”按原作相关财产权利期限已届满且具体底本可核验，或已取得明确改编授权处理。免费阅读不代表可改编；现代点校本、译本、插画和既有影视/动画表达要另行核验。
- 工作流试跑可用公版短篇，但只作为技术试件，不预定主 IP。先验证输入到可审核粗剪，暂不优化画面质量。
- 现有六段式脚本是知识讲解流程；小说方向需独立的故事脚本形态，保留原有讲解流程及其事实核验门槛。

### P17-01 小说工作流验证

状态：PASS

验收范围：
- 为小说来源、热度证据、底本版本与权利状态建立可追溯候选记录。
- 选一篇已核验的公版短篇作为测试输入，生成改编说明、连续剧情脚本、分镜和临时画面；测试故事不得被标记为主 IP。
- 从原文来源到可人工审核的粗剪包走通；画面精致度不计入本阶段验收，不能跳过来源、权利和人工审核门槛。
- 保留每个改编场景与原作章节/段落的对应关系；明确标出新增、删减和顺序调整。
- 不执行 V2-03/V2-04，也不下载或保存未授权整本小说。

已完成的方向研究：
- 初步热度样本与公版测试短篇记录见 `research/novel-candidates/2026-09-16.md`。
- 样本作品均标记为改编权未核验；《聊斋志异·种梨》只作为建议的公版工作流试件。
- 代码检查发现当前 `script` CLI 固定六段式讲解稿，不能直接承载小说剧情；P17-01 需要先建立独立故事改编通道。

执行记录（2026-09-16）：
- 新增 `scripts/novel_adaptation.py` 与输入 `validation/fiction-workflow-pilot.json`；从来源、版本与权利元数据生成改编计划、剧情脚本、逐镜分镜、临时文字卡、静音粗剪和人工复核清单。
- 输出位于 `projects/fiction-workflow-pilot-20260916/`；45 秒、6 场、540×960。故事场景都关联原作段落，并逐项标记改编变化。
- 权利状态未知或缺少证据链接会被拦截；通过仅表示元数据门槛通过。程序不访问/核验链接，发布权限为 false，必须人工复核。
- 小说流程专项测试 5 项通过；全量测试 179 项通过；环境检查与人工发布边界审计通过。
- 视频效果优化、正式角色资产、配音、音乐和主 IP 选择均不在本阶段。
- 代码 Git commit：`6a2fce6`（小说改编流程试点）。

### P17-02 小说候选库接入自动选题池

状态：PASS

目标：将公开平台的作品榜单快照和权利状态整理为候选记录，复用 P15/P16 形成可审阅的小说候选池。原始榜单指标必须留存，异构绝对值不能直接相加。

执行记录（2026-09-16）：
- 新增 `scripts/novel_candidate_pool.py` 与 `validation/novel-candidate-catalog.json`；通过榜单内名次百分位生成 P15 trend artifact 和 P16 自动选题池，再关联底本/版本、热度证据和权利状态。
- 本轮榜单来自公开页面的人工采样 JSON；导入后的归一、排序和权利拦截自动执行。平台抓取/官方 API Provider 尚未接入。
- 采样覆盖起点、番茄、晋江 3 个平台，5 部热门作品；4 部有明确榜单名次进入 P16，番茄在读人数与起点 8 月冲突名次只保留原始值，不伪造成可比得分。
- 当前样本中 5 部热门连载作品权利未核验，全部被改编门拦截；《聊斋志异·种梨》作为独立流程试件，不放入热门候选池。没有自动选择主 IP。
- 输出位于 `projects/novel-candidate-pool-20260916/`，包括原始趋势快照、P16 选题池、小说候选 JSON 与可读审核报告。
- 小说候选池专项测试 5 项通过；全量测试 184 项通过（含 P17-01）；未知权利、名次缺少榜单规模、重复快照和缺失来源均有拦截测试。
- Git commit：`233038a`（小说候选池接入 P16）。

### P17-03 公版原作与热门题材匹配、形成主 IP 建议

状态：PAUSED（研究成果保留；后续并入 P19 IP 来源与权利模型）

当前优先级（用户指示，2026-09-16）：
- 暂缓把小说 IP 可行性作为本地视频试制的前置条件；先以《镜花缘》作为临时试制 IP，验证角色设定图、中文配音和本地 MP4 生成链路。
- 该选择只用于本地工作流验证，不代表完成版权核验、正式锁定主 IP、授权制作或允许公开发布。
- 本地角色、配音和样片完成后，后续继续方向以用户指示为准；原连续榜单快照与权利证据验收暂缓。

目标：补足候选热榜的连续快照，并在自动池暴露的题材信号基础上，另行筛选原作版权期已届满或明确获授权的来源，形成可人工决策的短名单。不能把热门连载作品的角色、具体情节或表达改写后当作公版内容。

后续研究验收（本地试制后恢复）：
- 为每个公版候选核对作者、原作文本/版本、作者死亡年份或授权文件、目标发布地区与既有改编风险。
- 为起点、番茄、晋江至少取得连续三期榜单快照；优先使用官方数据入口或可替换 Provider，若入口受限则明确保留人工采样步骤。
- 将当前池的高位题材信号与经典作品的类型、叙事结构、连续角色弧和拆集潜力逐项匹配，并明确哪些是研究推断而非直接热度证据。
- 只有权利门通过且有来源证据的作品进入主 IP 人工决策短名单；不自动定稿或发布。

执行记录（2026-09-16）：
- 新增 `scripts/novel_ip_match.py`、`validation/classic-ip-catalog.json` 与 `validation/rank-snapshot-coverage.json`；按大陆著作权期限、作者/底本/来源证据筛选，再以透明的人工作题材标签和剧集适配维度排序。
- 可供人工定 IP 讨论的初步短名单为《镜花缘》《牡丹亭还魂记》《聊斋志异》；当时仅建议先讨论《镜花缘》，尚未完成主 IP 定稿。入正式制作前仍需核验指定古籍扫描卷册并排除现代校注、插图及后世视听表达。
- 《西游记》因本轮未取得可逐页核对的指定历史底本，且作者归属/版本层次需复核，留在权利复核区，不进入短名单。
- 起点官方荣誉页取得 2026-06 至 2026-08 连续三期《夜无疆》月票名次；番茄仅有 09-14、09-15 两个不同细分路由的日榜页面；晋江只取得当前 09 月古代言情月榜，未找到此前同口径月榜归档。三平台连续榜单要求未通过，跨期稳定性不作结论，P17-03 保持 IN_PROGRESS。
- 题材匹配分是编辑优先级启发式，不是热度预测或法律结论；短名单始终标记 `production_allowed=false`、`publication_allowed=false`。
- 新增 P17-03 专项测试 6 项；全量测试结果与下一步记录见本次执行日志。
- 验证：Provider 接入前全量测试 190 项通过；Web 控制台首版接入后 205 项通过；本地动态分镜联调后 207 项通过；`scripts/check-env.sh` 与 `python3 scripts/publish_policy.py audit` 均通过。
- Git commit：`61e539c`（公版原作与热门题材匹配框架及证据短名单）。

本地试制执行记录（2026-09-16）：
- 按用户最新指示，暂以《镜花缘》作为本地试制 IP，完成唐小山原创角色设定板：`projects/jinghua-yuan-local-pilot/assets/characters/tang-xiaoshan-model-sheet.png`。
- 从设定板制作竖屏全身角色图：`projects/jinghua-yuan-local-pilot/assets/characters/tang-xiaoshan-portrait.png`。
- 使用项目 `MacOSSayTTS` 本地适配器和系统中文女声 Tingting 合成 8.34 秒样音，无云端调用、无计费生成；音频位于 `projects/jinghua-yuan-local-pilot/voice/`。
- 合成 9:16、1080×1920、30fps 的 H.264/AAC MP4：`projects/jinghua-yuan-local-pilot/tang-xiaoshan-voice-test.mp4`。该样片是静态角色图配旁白，用于验证素材到视频的本地链路，不代表已完成角色动画。
- 根据用户提出的“场景 + 角色 + 剧情连贯”方向，新增三张连续场景关键帧和镜头节奏表；生成 `tang-xiaoshan-story-animatic.mp4`，约 8.34 秒，含轻推镜、两次淡化转场、配音和中文字幕。该动态分镜验证故事连续性，尚无逐帧角色动作或口型同步；当前尚未配置专用 AI 图生视频 Provider。
- 用户要求选定并接入视频生成能力；已选择本地优先的 `local_ken_burns` Provider，新增 `adapters/video_generation/`、`scripts/video_generate.py` 和 Provider 路由。它通过 FFmpeg 从有序关键帧生成带推镜和淡化转场的无声 MP4；`tang-xiaoshan-provider-generated.mp4` 已实际生成并通过解码检查。Runway 作为远程替换位预留但未启用、未上传素材。
- 用户要求继续接入真正的 AI 图生视频动作模型；已新增 `RunwayImageToVideo` 适配器，按 Runway Gen‑4.5 官方 REST API 创建任务、轮询状态并下载 5 秒结果。适配器仅在显式提供 `RUNWAY_API_KEY` 时上传单张关键帧，默认保持关闭；当前未执行远程生成。
- 用户要求优先使用 OpenAI 视频能力，同时保留 Runway 与 Wan 作为后续可替换的收费 Provider；新增 `OpenAISoraVideo`（`sora-2`/`sora-2-pro`）和 `WanImageToVideo`（fal.ai Wan 2.1）适配器，统一支持单张参考图、提示词、任务轮询和 MP4 下载。三类远程 Provider 都只在显式提供对应密钥时上传素材；没有密钥时会在本地失败并保持零调用。
- `scripts/video_generate.py` 已支持 `local_ken_burns`、`openai_sora`、`runway`、`wan` 四条路由，并将提示词与模型参数传入 Provider；本地三场景动态分镜回归成功，OpenAI/Wan/Runway 的创建、轮询、下载链路使用模拟响应验证通过。
- 用户补充要求整套系统提供 Web 端；新增依赖无关的本地控制台 `scripts/web_server.py` 与 `web/` 静态前端。页面可选择项目、预览角色/场景图、切换 Provider、填写镜头描述、显式确认远程计费调用并预览生成 MP4；接口复用同一组 Provider，不读取或回显密钥，也不提供发布动作。
- Web 端已通过本地服务启动、`/api/health`、`/api/projects`、本地生成 POST 和媒体预览接口检查；前端 JavaScript 语法检查通过。根据使用反馈，左侧菜单已改为真正的工作台/项目资产/Provider 设置视图，Provider 设置页支持把密钥临时写入当前服务进程内存并只返回配置状态，绝不落盘或回显密钥。
- 为先把零成本路线跑稳，修正了 `local_ken_burns` 多镜头交叉淡化的累计 offset；新增 `scripts/local_storyboard_pipeline.py`，把三张关键帧、本地 Tingting 配音和 `subtitles.srt` 一次合成为 `generated/tang-xiaoshan-local-storyboard-final.mp4`。本次联调结果为 8.34 秒、1080×1920、30fps、H.264/AAC，视频可完整解码。
- Web 工作台新增“生成完整本地分镜”按钮，调用同一 `run_local_storyboard` 流程，已通过浏览器点击联调并在页面内显示生成的 8.3 秒 MP4；本地 CLI 与 Web 不再是两条独立实现。
- 按用户要求完成前五集连贯本地试播：新增 `scripts/jinghua_yuan_episode_batch.py`，为 `episode-01` 至 `episode-05` 生成原创连续剧情、统一唐小山关键帧、Tingting 配音、SRT 字幕和 1080×1920 H.264/AAC MP4；五集均约 8.5 秒并通过 `ffprobe` 检查。Web 项目详情新增 `episodes` 清单和工作台可点击预览卡片，仍只走本地 Provider。
- 新增五集脚本、分镜和 Web 清单测试；本次新增专项测试 4 项通过，全量测试 211 项通过。后续接入动作模型时可复用每集的 `assets/scenes` 与 `episode.json`，不改变现有人工审核和发布边界。
- OpenAI 官方 API 文档当前仍列出 `sora-2` 与 `sora-2-pro`，但 Videos API 页面标记为 Deprecated，并计划于 2026-09-24 永久关闭；因此本阶段只把它作为短期试制 Provider，核心流程保持可替换。
- 试制说明和音频台词见 `projects/jinghua-yuan-local-pilot/README.md`。所有素材只用于本地验证；未完成指定古籍版本的权利核验，也没有公开发布。
- 两个 MP4 均可完整解码，动态分镜抽帧检查通过；本地故事连续性子目标完成。视频 Provider 接入与本地回退链路完成，P17-03 总状态保持 IN_PROGRESS，原榜单连续快照和权利证据研究按当前方向暂缓。

---

# 24. V3 — 多平台

状态：PLANNED

支持：

```text
微信视频号
抖音
小红书
YouTube Shorts
```

原则：

**同一内容，不直接复制同一成片。**

平台 Adapter 调整：

```text
duration
hook
caption
cover
safe-area
CTA
hashtags
```

---

# 25. V4 — 半自动发布

状态：PLANNED

允许：

```text
生成草稿
自动填写标题
自动填写文案
自动上传视频
```

仍然保持：

```text
最终点击发布 = HUMAN
```

---

# 26. V5 — 商业化模块

状态：PLANNED

增加：

```text
affiliate matching
product matching
brand matching
sponsor slot
CTA optimization
commercial score
```

输出：

```text
commercial-plan.json
```

---

# 27. V6 — 多账号 / 多栏目

状态：PLANNED

支持：

```text
account-a
account-b
account-c
```

不同：

```text
brand
voice
topic
visual
platform
monetization
```

共享底层引擎。

---

# 28. V7 — 本地 / 云端混合执行

状态：PLANNED

Provider：

```text
local
cloud
hybrid
```

高成本任务可路由。

示例：

```text
FFmpeg → local
Whisper → local
LLM → cloud
Video Generation → cloud
```

---

# 29. V8 — 成本控制

状态：PLANNED

每个项目记录：

```json
{
  "llm_cost": 0,
  "tts_cost": 0,
  "asr_cost": 0,
  "image_cost": 0,
  "video_cost": 0,
  "total_cost": 0
}
```

设置：

```text
max_cost_per_video
```

超过预算：

```text
STOP / DOWNGRADE
```

---

# 30. V9 — 内容记忆与复用

状态：PLANNED

建立：

```text
knowledge/
├── claims/
├── products/
├── scripts/
├── hooks/
├── footage/
├── charts/
└── references/
```

避免：

- 重复搜索
- 重复生成素材
- 重复配音
- 重复制作动画

---

# 31. V10 — Workflow Optimizer

状态：PLANNED

记录每次：

```text
input
execution_plan
provider
duration
cost
error
retry
final_quality
human_feedback
performance
```

自动寻找：

```text
最省钱 Provider
最快路径
最稳定路径
高表现脚本结构
高表现 Hook
```

---

# 32. 扩展规范

任何新功能必须满足：

## 32.1 Plugin First

禁止直接侵入主工作流。

新增能力：

```text
adapter/
plugin/
provider/
```

---

## 32.2 Capability Registry

建立：

```text
capabilities.json
```

示例：

```json
{
  "tts": ["fish", "elevenlabs", "edge"],
  "motion": ["hyperframes", "remotion"],
  "asr": ["whisper", "elevenlabs"],
  "video_generation": ["provider-a", "provider-b"]
}
```

---

## 32.3 Feature Flags

```text
ENABLE_REMOTION=false
ENABLE_AI_VIDEO=false
ENABLE_AUTO_RESEARCH=true
ENABLE_AUTO_FIX=true
ENABLE_AUTO_PUBLISH=false
```

---

## 32.4 Version Migration

每次升级：

```text
migration/
V1_to_V2.md
V2_to_V3.md
```

不得直接破坏老项目。

---

# 33. 安全规则

- API Key 只放环境变量。
- 不输出 Token。
- 不自动上传用户私有素材。
- 不执行未知脚本。
- 安装 GitHub 项目前固定 commit。
- 新依赖先做代码审查。
- 禁止自动发布。
- 禁止自动购买素材/API。
- 超预算必须停止。
- 商业/事实类结论必须保留来源。

---

# 34. GitHub 依赖管理

建立：

```text
DEPENDENCIES.md
```

字段：

```text
name
repository
version
commit
license
purpose
status
last_checked
```

核心依赖升级流程：

```text
discover
→ review
→ sandbox test
→ regression test
→ upgrade
→ rollback ready
```

禁止：

```text
直接 git pull latest 到生产环境
```

---

# 35. 测试体系

## 单元测试

```text
script validator
storyboard validator
asset manifest
provider fallback
subtitle safe area
duration estimator
```

## 集成测试

```text
topic → package
```

## 回归测试

固定测试题：

```text
ChatGPT Plus 一个月 20 美元到底值不值？
```

每次核心升级必须重新生成并对比：

```text
duration
render
subtitle
audio
scene count
QC
cost
```

---

# 36. 故障降级

示例：

```text
Fish Audio 失败
→ Edge TTS

HyperFrames 失败
→ static infographic

AI Video 失败
→ stock / screenshot / image pan

Remote LLM 失败
→ 保存状态 / resume

Render 失败
→ retry scene
→ retry finalizer
```

禁止因为单一 Provider 故障导致整个项目丢失。

---

# 37. 运行入口规划

最终只保留一个用户级入口：

```bash
videorun
```

示例：

```bash
videorun "ChatGPT Plus 一个月 20 美元到底值不值？"
```

后续：

```bash
videorun status
videorun resume <id>
videorun rerun <id> SC007
videorun open <id>
```

终端输出必须简洁。

---

# 38. 第一批 20 条候选选题

1. ChatGPT Plus 一个月 20 美元到底值不值？
2. Codex 到底能不能自动剪视频？
3. 普通人用 ChatGPT 最实用的 5 个功能。
4. ChatGPT、豆包、千问，到底怎么选？
5. Claude Code 和 Codex 有什么区别？
6. 为什么很多人用了 AI 反而更浪费时间？
7. Codex 能不能自己给自己安装视频 Skill？
8. 40 块钱的随身 WiFi 到底是不是智商税？
9. 车机到底有没有必要单独办流量卡？
10. Clash 和公司 VPN 为什么经常冲突？
11. 普通人现在有没有必要买 NAS？
12. 学 AI 最容易踩的 5 个坑。
13. AI 到底能不能自动做自媒体？
14. 我搭了一套 AI 短视频生产线。
15. 这条视频其实 80% 都是 AI 做的。
16. AI 生成视频最大的问题根本不是画质。
17. 为什么我不建议一开始做 AI 数字人？
18. 免费 AI 和付费 AI 真正差在哪里？
19. AI 自动化到底适不适合普通人？
20. 做自媒体最值得自动化的是哪一步？

---

# 39. V1 完成定义（Definition of Done）

只有以下全部满足，V1 才算完成：

```text
[ ] 一句话创建项目
[ ] 自动 Research
[ ] 自动 Script
[ ] 自动 Storyboard
[ ] 自动 Asset Routing
[ ] HyperFrames 可用
[ ] TTS 可用
[ ] video-use 可用
[ ] FFmpeg Finalizer 可用
[ ] Technical QC 可用
[ ] Content QC 可用
[ ] 自动封面
[ ] 自动标题
[ ] 自动 Caption
[ ] 自动 Hashtags
[ ] Resume 可用
[ ] Scene rerun 可用
[ ] 失败可降级
[ ] 成本可记录
[ ] 发布包完整
[ ] 最终发布人工确认
[ ] 连续生产 20 条完成验证
```

---

# 40. 当前执行顺序

P0～P17 保留为早期通用短视频系统与小说试制历史。当前产品路线按小说 IP 国风动漫重构顺序执行：

```text
P18 架构与数据底座
→ P19 IP 来源与故事知识库
→ P20 改编与编剧室
→ P21 视觉圣经与资产系统
→ P22 分镜与 Animatic
→ P23 音频制作
→ P24 动态镜头
→ P25 剪辑与后期
→ P26 六类 QC 与人工审核
→ P27 Web 制作台
→ P28 《镜花缘》正式五集验收
```

实现期间只推进当前 `NEXT`。已经完成的 Provider、TTS、FFmpeg、EDL、QC、发布人工确认和 Web 基础作为可复用能力接入新数据模型，不按旧阶段重新开发。

---

# 41. 当前方向与下一任务

```text
NEXT: P28-01 复验（补齐正式五集素材与人工确认后）
```

任务：

> 用户确认重新规划“小说 IP 剧情国漫”整套系统。现有《镜花缘》五集只作为本地 animatic 技术样片保留，不再以旧的单条知识视频结构继续扩展。新系统以 IP、底本、剧集、季、故事弧、集、场、镜头、资产和渲染为核心层级；先建设故事与连续性底座，再扩展动态视频效果。

规划主文档：`docs/NOVEL-ANIME-SYSTEM.md`。本 TASK 继续作为任务状态和执行顺序的唯一来源。

## 41.1 小说 IP 国风动漫重构路线

```text
P18 架构与数据底座
→ P19 IP 来源与故事知识库
→ P20 改编与编剧室
→ P21 视觉圣经与资产系统
→ P22 分镜与 Animatic
→ P23 音频制作
→ P24 动态镜头
→ P25 剪辑与后期
→ P26 六类 QC 与人工审核
→ P27 Web 制作台
→ P28 《镜花缘》正式五集验收
```

### P18 架构与数据底座

状态：PASS

- P18-01：PASS。定义 IP、SourceEdition、Series、Season、Arc、Episode、Scene、Shot、Asset、Render Schema 与稳定 ID。
- P18-02：PASS。建立 SQLite Repository、JSON 里程碑快照、资产注册表、版本、输入引用、来源引用、依赖关系和变更影响分析。
- P18-03：PASS。建立持久化作业队列、并发锁、重试、取消、剧集状态机、审核门、局部重跑、失败恢复和旧样片迁移器。

验收：能够建立一个空白小说动漫项目，保存一季五集结构；所有集、场、镜头和资产通过 ID 关联；修改上游对象后能列出需要重做的下游产物。

P18-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-anime-project.schema.json` 和 `scripts/novel_anime_project.py`，覆盖十类核心实体、统一审核字段、版本字段、状态和稳定 ID。
- 创建本地项目 `projects/jinghua-yuan-series/novel-anime-project.json`，层级为 `IP-JHY → SER-JHY-01 → S01 → S01E001…S01E005`，默认保持 `publication_allowed=false`。
- 新增 `/api/novel-anime/projects` 与详情 API；Web 左侧新增“国漫项目”页面并实际显示一季五集层级。
- 新增 6 项专项测试，JSON Schema 2020-12 校验、CLI 创建/加载、关系引用、父级作用域、覆盖保护和 Web 摘要均通过；全量 217 项测试通过。

P18-02 执行记录（2026-09-16）：
- 新增 `scripts/novel_anime_repository.py`，以项目内 SQLite 保存实体、依赖边、资产版本和快照索引；数据库与媒体都保持本地，manifest 继续作为可导出的领域快照。
- manifest 同步会建立 `IP → Series → Season → Episode` 依赖图，并支持 SourceEdition、Arc、Scene、Shot、Asset、Render 以及显式 `input_refs/source_refs`。
- 资产注册验证文件必须位于项目内、计算 SHA-256、保留递增版本并记录来源实体；实际注册唐小山角色图 `AST-CHR-TXS-PORTRAIT` 第 1 版。
- 创建 `p18-core-model` JSON 里程碑快照；从 `IP-JHY` 运行影响分析可列出角色资产、剧集、第一季和五集全部下游对象。
- Web API 新增仓库统计和影响分析；“国漫项目”卡片显示 9 个实体、8 条依赖、1 个资产版本和 1 个快照，并可点击“分析 IP 影响”。
- 新增 5 项 Repository 专项测试并扩展 Web 测试，覆盖初始化、递归影响、资产版本、路径/引用边界和快照内容；全量 222 项测试通过。

P18-03 执行记录（2026-09-16）：
- 新增 `scripts/novel_anime_runtime.py`，SQLite 持久化任务支持幂等键、优先级、实体锁、工作租约、失败重试、取消、过期恢复和本地 worker。
- 建立严格的 13 阶段剧集状态序列；每次前进只能进入下一阶段，并要求对应的人工审核门已明确 `APPROVED`，状态变化记录修订号和审计轨迹。
- 依赖影响可以转换为局部重跑队列；按下游深度排序且只为受影响实体生成重建任务，不重跑无关项目。
- 旧 `jinghua-yuan-local-pilot` 五集已迁移到新项目的五个版本化参考视频资产，全部标记 `legacy=true`、`publication_allowed=false`，迁移具备幂等记录，不覆盖不同内容。
- 实际完成 1 个 `VALIDATE_PROJECT` 持久化任务；Web API 和国漫项目页显示任务成功数、排队/运行状态、锁和迁移计数。当前实际仓库为 14 个实体、13 条依赖、6 个资产版本、1 个快照、1 次迁移。
- 新增 7 项运行时专项测试，覆盖幂等执行、并发锁、重试/取消、租约恢复、审核状态机、局部重跑和旧样片迁移；全量 229 项测试通过。

### P19 IP 来源与故事知识库

状态：PASS

- P19-01：PASS。底本、章节、来源定位、授权地域、使用范围和发布门。
- P19-02：PASS。原文导入、章节切分与人物、地点、道具、事件抽取。
- P19-03：PASS。世界观、角色、关系、规则、时间线、伏笔和连续性账本。

验收：每个改编节拍可追溯到章节或标记原创增补；下一集写作能够读取上一集结束时的人物、服装、道具、位置、关系和知识状态。

P19-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-source-catalog.schema.json` 与 `scripts/novel_source_catalog.py`，定义底本、章节、页码/段落定位、证据、地区、现代贡献和改编策略。
- 权利状态分为未评估、研究中、公版已核验、已授权和阻断；正式发布必须同时具备证据、适用法域、覆盖目标地区、明确改编许可和人工审核通过。
- 现代校注、翻译、插图、版式、序言和排版分别记录权利状态；任何未评估的现代贡献都会阻止发布。来源 URL 禁止内嵌凭据，章节与定位双向引用并验证范围。
- 已为 `jinghua-yuan-series` 创建来源目录，当前保持 `UNASSESSED`、底本 0、章节 0、`script_adaptation_allowed=false`、`publication_allowed=false`，未把技术样片误标为正式可改编内容。
- `SOURCE_READY` 状态现在同时检查来源目录和运行时人工审核门，单独点击批准不能绕过底本权利模型。
- Web API 暴露来源目录，国漫项目卡片显示底本/章节/定位数量和“禁止发布”状态；新增 7 项专项测试，全量 236 项测试通过。

P19-02 执行记录（2026-09-16）：
- 新增 `scripts/novel_source_ingest.py`，对已登记并通过权利审核的本地 UTF-8 底本执行显式授权导入、中文回目/章节切分、稳定章节 ID 分配和来源行号定位；单文件限制 20 MB，并拒绝二进制或非 UTF-8 输入。
- 新增可替换的 `adapters/story_extraction` 边界和确定性的 `LocalLexiconExtractor`，以受控词表提取人物、地点、道具提及和事件候选；所有候选均标记为待人工审核。
- 导入产物只保存文件/章节/句子 SHA-256、行号、字数、提及次数和实体引用，明确 `full_text_stored=false`，不在项目中复制小说全文。正式导入会同步底本目录、核心 manifest 和 Repository；`--test-only` 不污染正式章节与核心数据。
- Web 项目摘要和安全的 `source-imports` API 显示导入、实体与事件候选数量，但不暴露源文本。《镜花缘》实际项目因尚无核验底本继续保持正式导入 0、章节 0 和禁止改编/发布状态。
- 新增 5 项导入专项测试并扩展 Web 测试，覆盖章节行号、授权门、正式同步、技术测试隔离和无正文留存；全量 241 项测试通过。

P19-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-story-bible.schema.json` 与 `scripts/novel_story_bible.py`，把故事长期记忆拆分为世界观、人物、关系、地点、道具、规则、时间线、伏笔和连续性账本 9 类文件，并通过统一元数据和修订号防止文件间版本漂移。
- 所有故事实体必须使用稳定 ID，且必须引用来源目录中的章节/定位，或明确标记为原创增补并记录说明；人物、关系、道具、地点、时间线、伏笔和单集引用均进行跨文件校验。
- 连续性账本保存每集结束时的人物位置、服装、携带物、伤势、知识与情绪，以及关系、道具持有人、时间线位置和未回收伏笔；道具携带状态和持有人必须一致，快照必须组成无断点的单链。
- 每集 manifest 已绑定前一集结束快照与本集 continuity delta 路径。`continuity-input` 在写作前加载上一集状态，缺少上一集快照会阻断后续单集；`BIBLE_READY` 现在同时检查世界、人物、时间线、实体审核和连续性基线，单独批准运行时审核门无法绕过故事圣经。
- 实际《镜花缘》项目已创建空白故事圣经和 `CNT-S01E000-END` 基线，但因尚未导入核验底本，保持 `DRAFT`、实体 0、审核待定，不虚构正式人物与剧情资料。
- Web 项目卡片、故事圣经 API 和单集连续性输入 API 已接入同一份数据；新增 5 项专项测试并扩展运行时和 Web 测试，全量 246 项测试通过。

### P20 改编与编剧室

状态：PASS

- P20-01：PASS。全剧、季度和角色弧规划。
- P20-02：PASS。故事弧、单集卡和结尾钩子规划。
- P20-03：PASS。场景剧本、对白、旁白、情绪、声效和 continuity delta。
- P20-04：PASS。剧情因果、节奏、人物动机、伏笔与跨集矛盾审核。

P20-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-series-plan.schema.json` 与 `scripts/novel_series_plan.py`，以 `series-plan.json`、季度 `season-plan.json` 和 `character-arcs.json` 建立全剧、季度、角色成长弧三级规划。
- 全剧规划固定覆盖项目全部季度，季度规划固定覆盖所属全部集；主要转折和角色弧里程碑必须位于对应季度，并使用稳定的 SeriesPlan、SeasonPlan、CharacterArc、Turn 和 Milestone ID。
- 每项规划通过章节/定位或故事圣经实体追溯依据，原创增补必须显式说明；计划保存 `story_bible_revision`，故事圣经升级后旧计划立即判定为过期，防止继续沿用失效人物或世界状态。
- `readiness` 同时检查故事圣经、全剧计划、所有季度计划、角色弧及其人工审核；实际《镜花缘》已创建一季五集的 DRAFT 规划骨架，当前保持角色弧 0、转折 0、不可进入写作。
- Web 项目卡片与 Series Plan API 已接入同一份规划文件；新增 5 项专项测试并扩展 Web 测试，覆盖拆分文件、一季五集覆盖、跨层引用、转折范围、上游修订失效和完整就绪判断；全量 251 项测试通过。

P20-02 执行记录（2026-09-16）：
- 新增 `schemas/novel-episode-planning.schema.json` 与 `scripts/novel_episode_planning.py`，建立 3～8 集故事弧和每集唯一的 EpisodeCard；实际项目已创建 S01E001～S01E005 五张 DRAFT 单集卡。
- 单集卡定义 premise、开场钩子、目标、阻碍、转折、高潮、结尾钩子，以及人物、地点、道具和伏笔设置/回收引用；READY 卡必须至少包含可追溯的 `HOOK` 与 `ENDING_HOOK` 节拍。
- 每个节拍都必须引用章节/定位、故事圣经实体，或明确标记原创增补；故事弧限定同一季度 3～8 集，并检查角色弧和伏笔引用。规划固定引用 Series Plan 修订号，上游规划变化后自动失效。
- 故事弧与 EpisodeCard 归属可同步到核心 manifest、Season、Episode 和 Repository；实际《镜花缘》因上游未就绪保持故事弧 0、单集卡 5、就绪卡 0、节拍 0。
- Web 项目卡片与 Episode Planning API 已接入；新增 4 项专项测试并扩展 Web 测试，覆盖五集卡片、故事弧范围、钩子完整性、节拍来源和上游修订失效；全量 255 项测试通过。

P20-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-script-package.schema.json` 与 `scripts/novel_episode_script.py`，为 S01E001～S01E005 分别创建 `script.json` 和 `continuity-delta.json`，共 10 个写作文件；脚本包固定引用 Episode Planning 修订号。
- 场景脚本使用稳定 Scene/Unit ID，明确区分 ACTION、DIALOGUE、NARRATION、SFX 和 VISUAL；对白必须绑定场内角色与情绪，旁白必须带表演情绪且不冒充角色，声效必须记录 cue、触发时机和混音提示。
- 每个场景与表演单元都必须追溯到章节/定位、故事圣经实体或原创增补；校验连续序号、节拍引用、人物/地点引用和估算时长，超过单集目标时长 15% 会阻断。
- continuity delta 覆盖人物位置、服装、携带物、伤势、知识、情绪、关系、道具持有人、伏笔和时间线位置；可在不写入账本的情况下预览集末快照，并由完整故事圣经校验结果状态。前集快照缺失会阻止后续剧本或 delta 进入 READY。
- 实际《镜花缘》项目已建立五集 DRAFT 剧本与 delta 骨架；当前场景 0、表演单元 0，只有 S01E001 可读取基线，S01E002～S01E005 等待前集结束快照。场景可同步到核心 manifest 与 Repository。
- Web 项目卡片与 Episode Scripts API 已接入；新增 5 项专项测试并扩展 Web 测试，覆盖五集文件、对白/旁白/声效约束、时长预算、连续性预览和跨集阻断；全量 260 项测试通过。

P20-04 执行记录（2026-09-16）：
- 新增 `schemas/novel-story-review.schema.json` 与 `scripts/novel_story_review.py`，以确定性审核覆盖因果、节奏、人物动机、伏笔、跨集连续性和来源标记六个类别，并生成稳定 Finding ID、严重度、实体引用和分类状态。
- 审核检查全剧/单集规划就绪、目标—阻碍—转折—高潮—钩子因果链、短剧时长覆盖、场景密度、计划人物是否实际出场、伏笔设置/回收是否写入 delta、前集快照以及 delta 是否能形成合法集末状态。
- 报告保存故事圣经、Series Plan、Episode Planning 和 Script Package 四个输入修订号；存在 BLOCKER、WARNING、开放 Finding 或修订过期时禁止人工批准。`WRITING_READY` 现在要求当前报告 PASS、人工明确批准和原有运行时审核门同时满足。
- 实际《镜花缘》首次审核为 `BLOCKED`：21 个阻断项，其中包含上游规划未就绪、五集脚本/delta 未就绪和后四集连续性输入缺失；结果准确呈现当前骨架阶段，没有把空白文件误判为可制作剧本。
- Web 项目卡片与 Story Review API 已接入；新增 4 项专项测试并扩展运行时和 Web 测试，覆盖分类阻断、稳定 Finding、报告往返、阻断批准和上游修订失效；全量 264 项测试通过。

### P21 视觉圣经与资产系统

状态：TODO

- P21-01：PASS。国风视觉风格、色彩脚本、构图和负面约束。
- P21-02：PASS。角色转面、表情、服装、比例、配色和身份一致性资产。
- P21-03：PASS。地点、道具、天气、时间和光线版本。
- P21-04：PASS。参考包、资产版本、选择记录和人工美术审核。

P21-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-visual-bible.schema.json` 与 `scripts/novel_visual_bible.py`，拆分保存 `style.json`、`color-script.json`、`composition-rules.json` 和 `negative-constraints.json`，并固定引用 Story Bible 与 Script Package 修订号。
- 视觉方向覆盖国风美术总述、文化依据、线稿、渲染、材质、角色/环境/动作语言和可复用提示词前缀；来源必须指向已登记章节/故事实体或明确标记原创，参考资产必须存在于核心项目。
- 色彩脚本要求每集唯一配色，使用稳定色板 ID 与大写十六进制颜色；构图配置默认 1080×1920、9:16、30 fps，独立校验画面安全区、字幕区与构图规则。
- 负面约束默认阻止水印、乱码、多余肢体、角色身份漂移、环境连续性漂移，以及现代校注/插图、现成影视设计、未授权参考和内嵌凭据。四个视觉部分必须一起进入 READY 并分别通过人工审核。
- 实际《镜花缘》已创建 DRAFT 视觉圣经：五集配色槽位、0 个正式色板、0 条正式构图规则和 9 项基础负面约束；未擅自确定具体朝代服饰或复用现有影视造型。
- Web 项目卡片与 Visual Bible API 已接入；新增 5 项专项测试并扩展 Web 测试，覆盖拆分文件、完整 READY 配置、画幅、色板引用、同步状态和上游修订失效；全量 269 项测试通过。

P21-02 执行记录（2026-09-16）：
- 新增 `schemas/novel-character-designs.schema.json` 与 `scripts/novel_character_designs.py`，为每个故事角色建立唯一 CharacterDesign，覆盖身份契约、固定色板、正/四分之三/侧/背/近景转面、基础表情、服装、提示词模板和未来语音角色引用。
- 身份契约记录头身比、体型、脸型、肤色、发型/发色、眼型/眼色、显著标记、不可变特征和角色级负面约束，并生成 SHA-256 identity signature；所有转面、表情和服装必须携带同一签名，修改核心特征会立即判定漂移。
- READY 角色必须具有已选的正面、侧面、背面、近景，中性/喜/怒/哀/惊五类表情，固定配色、正负提示词和唯一默认服装；SELECTED 条目必须引用 Repository 中存在当前版本的本地资产。
- 新增结构化身份观察检查，能够逐字段报告脸型、发型、肤色、眼型、标记和头身比偏差；Repository 新增当前资产 ID 查询，Visual Bible 也可安全引用已登记但尚未写入核心 manifest 的版本化资产。
- 实际《镜花缘》已创建角色设定目录，但因正式故事圣经角色仍为 0，当前角色、转面、表情和服装均为 0；旧唐小山图片继续作为 `legacy/reference` 本地资产，不自动冒充正式角色设定。
- Web 项目卡片与 Character Designs API 已接入；新增 5 项专项测试并扩展 Repository/Web 测试，覆盖角色覆盖、完整身份契约、资产登记、签名漂移、观察偏差和默认服装；全量 274 项测试通过。

P21-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-environment-assets.schema.json` 与 `scripts/novel_environment_assets.py`，建立地点布局、固定地标、复用机位、天气/时间/光线/季节变体、道具身份与状态、场景环境绑定的数据模型。
- 地点与道具设计必须覆盖故事圣经中的全部实体；机位、变体和道具状态携带父级连续性签名，选中项必须引用已登记的项目资产，防止环境镜像、材质或道具持有状态漂移。
- 每个带地点的剧本场景都必须有唯一环境绑定，并校验集、地点、时间、天气、光线与所选变体一致；视觉圣经、资产登记和人工审核仍是环境就绪门的一部分。
- 实际《镜花缘》项目已创建并验证 `visual-bible/environment-assets.json`；当前故事圣经尚无正式地点、道具和场景，因此保持 0 个设计、0 个变体、0 个绑定和 DRAFT 阻断状态，没有虚构小说内容。
- Web 项目卡片新增地点/变体/道具/状态/场景绑定摘要，并新增环境资产 API；4 项专项测试、Web 回归和环境检查通过，全量 278 项测试通过。

P21-04 执行记录（2026-09-16）：
- 新增 `schemas/novel-asset-review.schema.json` 与 `scripts/novel_asset_review.py`，建立角色/地点/道具/镜头/剧集参考包、视图引用、当前资产版本选择、选择理由和人工美术审核记录。
- 选中参考必须引用 Repository 当前资产版本；版本过期、引用不存在、选择记录与参考不一致或缺少审核记录都会阻断校验。参考包没有选择项或审核未批准时不能进入视觉就绪。
- 实际《镜花缘》项目已创建并验证 `visual-bible/asset-review.json`；正式角色、地点、道具和镜头仍为空，因此参考包与选择记录为 0，保持 DRAFT 阻断状态。
- Web 项目卡片新增参考包/资产版本/美术审核摘要，并新增 Asset Review API；3 项专项测试、Web 回归和环境检查通过，全量 281 项测试通过。

P22-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-shot-breakdown.schema.json` 与 `scripts/novel_shot_breakdown.py`，为每个剧本场建立稳定 Scene/Shot 分解，记录景别、角度、运动、焦段、时长、首状态、尾状态和参考包引用。
- Shot 与首尾状态分别生成连续性签名；场覆盖、剧集归属、剧本修订和参考包修订都会校验，任何上游修订过期或引用不存在都会阻断分镜。
- 实际《镜花缘》项目已创建并验证 `storyboard/shot-breakdown.json`；当前剧本场仍为 0，因此保持 0 场、0 镜的空分镜骨架，没有虚构镜头。
- Web 项目卡片新增场/镜头/审核摘要，并新增 Shot Breakdown API；2 项专项测试、Web 回归通过，下一步进入静态 storyboard 与首尾帧规划。

P22-02 执行记录（2026-09-16）：
- 新增 `schemas/novel-storyboard.schema.json` 与 `scripts/novel_storyboard.py`，为每个 Shot 建立首帧/尾帧槽位，记录图像资产、参考包引用、状态签名、镜头时长和人工审核。
- Storyboard 必须覆盖全部 Shot，时长必须与 Shot 分解一致；选中的帧必须有资产，参考包或 Shot 修订后旧 storyboard 会被判定为过期。
- 实际《镜花缘》项目已创建并验证 `storyboard/storyboard.json`；当前没有正式 Shot，因此保持 0 个首尾帧、0 个已选帧的空 storyboard 骨架。
- Web 项目卡片新增首尾帧摘要，并新增 Storyboard API；2 项专项测试、Web 回归通过，下一步进入本地 animatic、临时配音和字幕预览。

P22-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-animatic.schema.json` 与 `scripts/novel_animatic.py`，按五集建立本地 Animatic 计划，把 Shot、临时音频、字幕轨和集级预览输出统一到可恢复数据中。
- Animatic 固定引用当前 Script Package 与 Storyboard 修订；READY 集必须同时拥有镜头、临时音频、字幕、预览文件和人工审核，不能把空骨架误判为成片。
- 实际《镜花缘》项目已创建并验证 `animatic/animatic-plan.json`；五集计划已覆盖，但当前 0 镜头、0 音频、0 字幕、0 预览，全部保持 DRAFT。
- Web 项目卡片新增 Animatic 集级进度，并新增 Animatic API；2 项专项测试、Web 回归通过，下一步进入节奏、动作可读性和连续性审核。

P22-04 执行记录（2026-09-16）：
- 新增 `schemas/novel-animatic-review.schema.json` 与 `scripts/novel_animatic_review.py`，建立 Animatic 节奏、动作可读性、角色连续性、场景连续性和道具连续性审核报告。
- 报告固定引用 Animatic、Shot Breakdown 和 Storyboard 修订；没有镜头、临时音频或字幕时生成稳定阻断 Finding，人工审核未批准时不能放行。
- 实际《镜花缘》项目已创建并验证 `animatic/review.json`：11 个阻断项，准确反映当前 0 镜头、0 音频、0 字幕的空骨架，没有把技术结构误判为可审片成品。
- Web 项目卡片新增 Animatic 审核摘要，并新增 Animatic Review API；2 项专项测试、Web 回归通过，P22 分镜与 Animatic 阶段完成，下一步进入 P23 音频制作。

P23-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-voice-profiles.schema.json` 与 `scripts/novel_voice_profiles.py`，建立角色音色 profile、Provider/voice ID、音高、语速、逐句对白/旁白、情绪与发音备注。
- 每个正式角色必须有唯一 voice profile；对白必须绑定对应角色，旁白不能误绑角色；脚本修订后旧配音计划自动失效。
- 实际《镜花缘》项目已创建并验证 `audio/voice-profiles.json`；当前角色和对白仍为 0，因此保持空的本地配音计划，不调用远程 TTS。
- Web 项目卡片新增配音角色/台词摘要，并新增 Voice Profiles API；2 项专项测试、Web 回归通过，下一步进入音乐、环境声、动作音效和混音计划。

P23-02 执行记录（2026-09-16）：
- Voice Profiles 数据模型同时覆盖逐句对白、旁白、情绪和发音备注；对白绑定角色 profile，旁白保持独立，脚本修订会使旧台词计划失效。
- 实际项目当前没有正式角色和对白，因此 0 条台词进入配音队列，未调用远程 TTS。

P23-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-audio-assets.schema.json` 与 `scripts/novel_audio_assets.py`，建立音乐、环境声、动作音效、Cue、来源类型、授权状态和混音目标参数。
- READY 音频轨必须有本地文件、`CLEARED` 授权和人工审核；Cue 必须引用已登记音轨与剧集，Animatic 修订后旧音频计划自动失效。
- 实际《镜花缘》项目已创建并验证 `audio/audio-assets.json`；当前音轨与 Cue 为 0，混音默认目标为 -16 LUFS、-1 dBTP、48 kHz，没有虚构或抓取音乐素材。
- Web 项目卡片新增音频轨/Cue/清权/响度摘要，并新增 Audio Assets API；2 项专项测试、Web 回归通过，下一步进入混音、响度和声画同步。

P23-04 执行记录（2026-09-16）：
- 新增 `schemas/novel-audio-mix.schema.json` 与 `scripts/novel_audio_mix.py`，按集建立对白、音效 Cue、目标响度、真峰值、混音输出和声画同步偏移计划。
- 混音计划固定引用 Audio Assets、Voice Profiles 和 Animatic 修订；同步偏移超过 100ms、输出缺失或人工审核未通过时不能 READY。
- 实际《镜花缘》项目已创建并验证 `audio/mix-plan.json`；五集计划已覆盖，当前 0 个混音输出、最大同步偏移 0ms，仍保持 DRAFT。
- Web 项目卡片新增混音集数/输出/同步偏移摘要，并新增 Audio Mix API；2 项专项测试、Web 回归通过，P23 音频制作阶段完成，下一步进入 P24 动态镜头。

P24-01～P24-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-dynamic-shots.schema.json` 与 `scripts/novel_dynamic_shots.py`，建立 Shot 级 Provider 路由：本地运镜、图生视频、首尾帧、口型同步和人工导入，并记录输入参考与回退策略。
- 同一模型覆盖队列、预算、上传授权、计费确认、重试上限、输出路径和镜头审核；计费或上传任务缺少显式确认会被阻断，预算超限和重试超限同样阻断。
- 实际《镜花缘》项目已创建并验证 `dynamic/dynamic-shots.json`；当前 0 个正式 Shot、0 个队列任务、预算 0 USD，没有调用 Runway、Wan 或其他远程 Provider。
- Web 项目卡片新增动态镜头/队列/预算摘要，并新增 Dynamic Shots API；2 项专项测试、Web 回归通过，P24 动态镜头阶段完成，下一步进入 P25 集级时间线和镜头组装。

P25-01～P25-03 执行记录（2026-09-16）：
- 新增 `schemas/novel-edit-timelines.schema.json` 与 `scripts/novel_edit_timelines.py`，按集组装动态镜头、对白/Cue、字幕状态和四条音频总线，并固定引用 Dynamic Shots 与 Audio Mix 修订。
- 剪辑片段记录来源类型、源文件、时间范围、转场、特效和调色字段；READY 集必须具备片段、字幕、输出文件和人工审核，避免把空时间线误判为成片。
- `rerender_jobs` 支持 `REPLACE_CLIPS` 与 `FULL_EPISODE` 两种局部重渲染计划，校验集/镜头引用和输入修订号，过期任务会被阻断。
- 实际《镜花缘》项目已创建并验证 `edit/edit-timelines.json`：五集覆盖，当前 0 片段、0 个重渲染任务、0 集 READY，保持 DRAFT；没有调用远程视频 Provider。
- Web 项目卡片新增剪辑时间线摘要，并新增 Edit Timelines API；2 项专项测试、Web 回归通过，P25 剪辑与后期阶段完成，下一步进入 P26 来源权利、剧情和连续性 QC。

P26-01～P26-04 执行记录（2026-09-16）：
- 新增 `schemas/novel-qc-report.schema.json` 与 `scripts/novel_qc.py`，建立来源权利、剧情、连续性、角色与视听、技术、发布六类 QC 统一报告，并固定引用 P19～P25 的上游修订号。
- P26-01 会读取来源目录、剧情审核和 Animatic 连续性结果；权利状态、来源证据、剧本改编门、剧情人工审核和跨集连续性任一未通过都会产生可追溯阻断项。
- P26-02 汇总角色/场景/道具审核、Animatic 视听审核、动态镜头审核、混音和剪辑 READY 状态；当前空项目被准确报告为视听与技术阻断，没有虚构成片质量。
- P26-03 增加 `qc/` 报告历史、Web 批注、问题单、问题状态、局部重渲染任务关联和修订比较 API；所有写入仍通过项目 Schema 校验，并保留人工处理记录。
- P26-04 保留人工发布审核门；正式发布必须同时满足权利、六类 QC 和人工确认，QC 报告不会自动发布或绕过来源权利门。
- 实际《镜花缘》项目已创建并验证 `qc/qc-report.json`：6 类状态均为 `BLOCKED`，12 个开放阻断项，0 个批注/问题单，人工审核保持 `PENDING`；新增 2 项专项测试、Web 回归通过，P26 阶段完成，下一步进入 P27 项目工作台。

P27-01～P27-04 执行记录（2026-09-16）：
- Web 控制台新增统一国漫制作台和十个工作区：项目总览、IP 与底本、故事圣经、编剧室、角色美术、分镜 Animatic、音频制作、渲染队列、审片与问题单、发布包；左侧导航均可直接切换，读取同一套项目数据。
- 新增 `/api/novel-anime/projects/<id>/workspaces` 聚合 API，按工作区返回 P18～P26 的状态摘要；页面不维护独立 Web 数据副本，项目 Schema 和状态机仍是唯一数据来源。
- P27-03 接入 QC、问题单、批注、局部重渲染关联和版本比较入口；P27-04 接入仓库快照、迁移记录和备份清单，创建快照需明确本地操作，恢复保留人工确认。
- Web 项目制作台新增 `/backups` API，实际《镜花缘》项目已检测到 10 个连接工作区、1 个历史快照和 1 次旧样片迁移；新增制作台回归测试，JavaScript 语法、Python 编译、Web 回归和全量测试通过，P27 阶段完成，下一步进入 P28 正式五集验收。

P28-01 执行记录（2026-09-16）：
- 新增 `schemas/novel-acceptance-report.schema.json` 与 `scripts/novel_acceptance.py`，建立正式五集验收报告；逐集检查剧本、连续性、角色视觉、配音、字幕、Animatic、混音和剪辑，并固定引用上游修订号。
- 验收确认旧五集技术样片来自迁移记录且 `reference_only=true`、`publication_allowed=false`，不会把旧样片直接当作正式资产。
- 为第一集预留三个真实动作 Provider 代表镜头测试位（当前 `runway`、`NOT_RUN`），需要后续选定正式 Shot、确认上传授权和人工批准后才可运行；没有自动调用付费 Provider。
- 实际《镜花缘》项目已生成并验证 `acceptance/acceptance-report.json`：五集覆盖 5/5，但 0 集 READY、QC 为 `BLOCKED`、12 个 QC 阻断、动作测试 0/3、人工审核 `PENDING`，正式验收决策为 `HOLD`。
- Web 项目卡片新增正式验收摘要，并新增 Acceptance API；2 项验收专项测试、Web 回归、JavaScript/Python 检查和环境检查通过。
- 结果：FAIL/HOLD。当前不能宣布正式五集验收通过；下一步仍为 P28-01 复验，需先补齐权利、剧情连续性、角色资产、配音字幕、Animatic、混音、剪辑和人工审核。

P28-01 复验增量记录（2026-09-17）：
- 从维基文库导入《镜花缘》前五回作为本地 `test_only` 输入，建立 `SRC-JHY-001` 来源目录、章节定位和校验哈希；权利状态保持 `UNASSESSED`，不进入发布链路。
- 故事圣经已推进为 14 角色、8 地点、6 道具、12 时间线事件、2 个伏笔和 6 个连续性快照；S01E001–S01E005 已按前五回拆为 15 场、48 个表演单元，并重新生成下游 Shot/Storyboard/Animatic/音频/动态/剪辑包。
- 最新验收仍为 `HOLD`：5 集覆盖、0 集 READY、QC `BLOCKED`、12 个开放阻断、动作测试 0/3、人工审核 `PENDING`。五集草稿、连续性、正式视觉/音频资产仍待人工审核或制作，未调用远程 Provider。
- Web 项目摘要增加基于项目文件修订的缓存，项目列表、阶段门和工作区不再并发重复校验整套五集数据；缓存命中请求约 0.02 秒。Web 专项与全量回归通过（`306 passed, 6 subtests passed`）。
- 项目库已收敛为唯一试点 `jinghua-yuan-series`；其余 27 个旧试制/示例目录已移入 macOS 废纸篓备份 `/Users/zouhuashan/.Trash/video-projects-backup-20260917`，未永久擦除。
- 完成首批视觉锚点：百花仙子透明角色立绘、昆仑瑶池月夜场景，并以版本化资产登记到仓库；补齐角色身份契约、默认服装、场景布局、夜景变体和审核引用。
- 修复资产审核构建器遗漏角色参考包及硬编码资产版本的问题；现在角色、服装、场景都进入同一审核包，并跟随当前资产版本。
- 新增零成本本地动态样片渲染器 `scripts/render_local_motion_test.py`，使用分层角色/场景、背景慢移、呼吸位移、薄雾、花瓣和 FFmpeg 生成 6 秒 1080×1920 / 24fps H.264 样片；S01E002-SC002 已登记 1 个首帧和 1 个成功本地任务，仍等待人工审核。
- Web 会将唯一《镜花缘》试点显示为“国风动态漫试点”，并自动载入最近的本地样片供播放；未调用远程 Provider，费用为 0。

### P22 分镜与 Animatic

状态：TODO

- P22-01：PASS。Scene/Shot 分解、镜头语法、首尾状态和稳定镜头 ID。
- P22-02：PASS。静态 storyboard、首尾帧、镜头时长和前后连续关系。
- P22-03：PASS。本地 animatic、临时配音、字幕和集级预览。
- P22-04：PASS。节奏、动作可读性、角色/场景/道具连续性审核。

### P23 音频制作

状态：TODO

- P23-01：PASS。角色 voice profile、逐句对白、旁白、情绪与发音版本。
- P23-02：PASS。逐句对白、旁白、情绪和发音版本。
- P23-03：PASS。音乐、环境声、动作音效和来源授权清单。
- P23-04：PASS。混音、响度和声画同步。

### P24 动态镜头

状态：TODO

- P24-01：PASS。按镜头选择本地、图生视频、首尾帧、口型或人工导入。
- P24-02：PASS。Provider 队列、预算、上传授权、重试和回退。
- P24-03：PASS。镜头版本审核、角色一致性和动作可读性。

### P25 剪辑与后期

状态：PASS

- P25-01：PASS。集级时间线、对白和镜头组装。
- P25-02：PASS。转场、特效、色彩、字幕和音频总线字段。
- P25-03：PASS。镜头级替换与无损局部重渲染计划。

### P26 六类 QC 与人工审核

状态：PASS

- P26-01：PASS。来源权利、剧情和连续性 QC。
- P26-02：PASS。角色身份、画面、音频和技术 QC。
- P26-03：PASS。Web 批注、问题单、局部返工和版本对比。
- P26-04：PASS。人工确认、发布包门和发布记录约束。

### P27 Web 制作台

状态：PASS

- P27-01：PASS。项目总览、IP 与底本、故事圣经、编剧室。
- P27-02：PASS。角色美术、分镜和音频工作台。
- P27-03：PASS。渲染队列、成本、审片与问题单。
- P27-04：PASS。发布包、配置、备份和恢复清单。

### P28 《镜花缘》正式五集验收

状态：IN_PROGRESS（P28-01 首轮 FAIL/HOLD）

- 把旧五集技术样片迁移为参考资料，用新流程重新完成五集连续剧情、角色视觉、配音、字幕和 animatic。
- 至少选择一集的三个代表镜头做动作路线对比，默认优先非生成式路线（本地 Cutout Rig / 2D 骨骼 IK / Grease Pencil 或人工关键帧）；远程 AI 视频 Provider 仅作为可选增强基准，必须显式授权上传与计费。
- 通过六类 QC 和人工审片后，再决定是否扩展第一季。

P28-01 角色资产与 ArcReel 集成增量（2026-09-17）：

- 《镜花缘》百花仙子已补齐正面、侧面、背面透明转面图；角色参考从单一锚点扩展为 4 个已选择转面，近景和表情仍待额度恢复后补齐并人工审核。
- 增加 `adapters/workspaces/arcreel.py`，以 HTTP Adapter 对接独立 ArcReel 服务；现有项目仓库、Scene JSON、本地动态分镜和验收报告仍是主链路。
- Web Provider 设置页可配置 ArcReel 服务地址及可选令牌、检测连接状态，并明确显示 AGPL-3.0 和 `Powered by ArcReel` 署名。配置只驻留当前进程，不写盘、不回显令牌。
- 详细边界、接口和数据映射记录在 `docs/ARCREEL-INTEGRATION.md`。该桥接增量当时尚未安装或运行 ArcReel，未触发远程生成，`NEXT` 仍为 `P28-01` 复验。

P28-01 ArcReel 本地运行增量（2026-09-17）：

- ArcReel `0.30.0` 已作为本机侧车运行，镜像按摘要固定，只监听 `127.0.0.1:1241`；运行目录与 VideoCreator 主项目分离。
- Web 会自动发现该侧车并显示健康状态及镜像项目数量；《镜花缘》镜像项目已创建，五集与 15 个稳定镜头 ID 可通过 `scripts/arcreel_mirror.py` 重复核对。
- 本地公开底本已复制到 ArcReel 本机数据目录，工作流进入 `ASSET_INVENTORY`，队列任务数 0；没有复制图片或声音，没有配置收费 Provider，没有触发生成。`NEXT` 继续保持 `P28-01` 复验。

P28-01 自有角色预览增量（2026-09-17）：

- 按当前策略暂停 ArcReel：容器停止、数据保留，Web 显示“已暂停”且不探测外部工作台。
- “角色美术”工作区增加本地角色图画廊和零成本动作预览按钮；预览完全走自有 Pillow/FFmpeg 管线。
- 百花仙子正面图已完成 2 秒 1080×1920 / 24fps 预览实测，视频和首帧均自动登记资产版本与输入依赖。
- 本增量未调用任何远程模型。正式 P28 动作 Provider 对比与人工验收仍未完成，`NEXT` 保持 `P28-01`。

P28-01 本地角色 Rig 增量（2026-09-17）：

- 新增 `scripts/build_character_rig.py`，按原画布对齐生成百花仙子 `full/head/torso/lower` 四层透明 PNG，并登记为可追溯角色资产版本。
- Web 角色美术工作区新增 Rig 摘要与 `/api/novel-anime/projects/<id>/character-rigs` 只读接口；Rig 的人工审核状态保持 `PENDING`。
- 未安装新动画依赖、未调用 Runway/Wan/Sora，ArcReel 继续暂停，`NEXT` 保持 `P28-01`。

P28-01 Rig 分层动作预览增量（2026-09-17）：

- 新增本地 `render_character_rig_preview.py`，将 Rig 的 `head/torso/lower` 三层接入 Pillow/FFmpeg 动画链路，支持独立轻微摆动与呼吸。
- Web 角色美术工作区新增“生成 Rig 动作预览”入口；输出视频、首帧和全部输入依赖均写入资产仓库。
- 百花仙子 Rig 已完成 2 秒 1080×1920 / 24fps 实测；仍未调用远程 Provider，`NEXT` 保持 `P28-01`。

P28-01 Rig 校验增量（2026-09-17）：

- Rig 清单接口新增本地层文件校验：尺寸、RGBA 模式、透明内容和文件存在性均会检查。
- Web 只显示校验结果，不自动改变人工审核状态；局部替换层文件后可直接复验。

P28-01 表情、嘴型与分镜级 Rig 增量（2026-09-17）：

- 新增本地表情/嘴型通道清单，Rig 预览支持 `expression` 与 `mouth_cues` 参数。
- 新增分镜级接口 `/api/novel-anime/projects/<id>/storyboard-rig-preview`，读取 `shot_id` 和镜头时长，按本地 Rig 生成预览。
- 已验证 `SHOT-S01E002-SC002-001` 和四种表情通道；未调用远程 Provider，`NEXT` 保持 `P28-01`。

P28-01 对白嘴型编译增量（2026-09-17）：

- 新增 `scripts/compile_mouth_cues.py`，把本地 voice assignment 台词转换为镜头级 `mouth_cues`。
- 分镜级 Rig 预览会自动加载 `dynamic/mouth-cues.json`，台词更新后可局部重编译和重跑。
- 已编译 16 条带说话角色的试播台词，未调用远程 Provider，`NEXT` 保持 `P28-01`。

P28-01 字幕/音频/嘴型统一时间轴增量（2026-09-17）：

- `dynamic/mouth-cues.json` 增加字幕 cue、音频 cue、嘴型 cue 和镜头起止时间，作为本地统一时间轴。
- 新增 `/api/novel-anime/projects/<id>/timeline-cues`，分镜 Rig 预览返回对应 `timeline_cue`。
- 音频仍为 `PLANNED` 且未写入真实文件，未调用远程 Provider，`NEXT` 保持 `P28-01`。

P28-01 本地 TTS 与字幕混音增量（2026-09-17）：

- 新增 `generate_local_tts.py`，使用 macOS `say` 中文声线生成 16 条 WAV 并登记 `audio.asset_id`。
- 新增 `render_timeline_outputs.py`，按统一 cue 生成镜头级对白混音 WAV 与 SRT，并回写 `mix_asset_id`、`subtitle_asset_id`。
- 已完成本地链路验证；音频人工听审仍未完成，未调用远程 Provider，`NEXT` 保持 `P28-01`。

P28-01 镜头级最终成片预览增量（2026-09-17）：

- 新增 `mux_timeline_shot.py`，将 Rig 视频和统一时间轴对白混音合成为 MP4，并保留 SRT 字幕资产。
- Web 新增 `/api/novel-anime/projects/<id>/storyboard-final-preview` 和“生成最终镜头”入口。
- 已完成 `SHOT-S01E002-SC002-001` 合成测试；人工审片与正式发布仍未完成，`NEXT` 保持 `P28-01`。

P28-01 最终镜头人工审片门增量（2026-09-17）：

- 新增声音、字幕、嘴型三项人工检查和审片备注接口，默认 `PENDING`。
- 批量镜头预览接口在三项均未 `PASS` 前保持阻断，避免未审素材批量扩散。
- 批量执行器只处理说话角色与当前 Rig 匹配的镜头；百花仙子当前可覆盖 4 个镜头，其他角色 ID 明确列为阻断项。
- Web 新增 Rig 覆盖率：当前 4/16（25%）。图片生成连接失败后保持本地/免费路线，没有自动启用付费 API。
- 用户授权自动执行后，完成客观技术审片并批量生成百花仙子 4 个对白镜头；批次清单支持 Resume，发布前人工试听门仍保留。

P28-01 前五集对白镜头全覆盖增量（2026-09-18）：

- 为武则天、嫦娥、太平公主、百草仙子、麻姑、骆宾王、牡丹仙子和上官婉儿新增正面透明角色锚点，并与百花仙子一起形成 9 套本地 `full/head/torso/lower` Rig；Rig 构建器改为多角色增量写入，不再覆盖已有角色。
- 新增暖阁雪夜、上林苑冬日、小蓬莱玉碑、麻姑洞雪夜棋局、败军战场和红岩洞群芳 6 套场景锚点；批量渲染器依据 `scene_id` 自动选择登记场景，找不到时才使用昆仑兼容回退。
- 16/16 个带说话角色的前五集镜头已完成本地动态合成，Rig 覆盖率达到 100%；`dynamic/final-batch.json` 可跨角色合并和 Resume，现含 9 个 Rig 与 16 个最终镜头。
- 修复混音使用短配音截断镜头的问题：对白音频会补静音到视频时长，16 个成片实际时长均与统一时间轴一致并通过 FFmpeg 解码。
- 粒子效果改为按场景选择，战场、麻姑洞和暖阁不再叠加花瓣；Web 分镜预览与批量渲染共享同一背景和效果解析。
- 本轮仅完成客观技术检查与画面抽检；所有新增角色、场景和整批成片仍保留人工美术、声音与发布审核门。`P28-01` 继续执行五集完整叙事单元组装，不进入后续阶段。

P28-01 前五集本地试播母版与 Web 人审增量（2026-09-18）：

- 统一时间轴从 16 条角色对白扩展到 28 条语音单元，新增 12 条旁白；旁白不生成角色嘴型，但与对白共享 TTS、字幕、场景和集级时间轴。
- 新增 `scripts/assemble_local_episodes.py`，把 16 个角色对白镜头、12 个旁白单元和 20 个动作/视觉/音效单元组装为 48 个连续片段，并输出五集 1080×1920 / 24fps 本地试播母版。
- 五集时长分别为 57.16、53.14、53.21、56.72、64.08 秒；全部通过 FFmpeg 完整解码。发现首版字幕在竖屏左右裁切后已返工为 15 字安全行、最多两行、超长句按原时长拆段，并通过五集抽帧复检。
- Web“渲染队列”新增五集在线播放和逐集人审，检查剧情连贯、画面、声音、字幕四项；新增 `/api/novel-anime/projects/<id>/episode-masters` 与 `/episode-masters/review`，四项全为 `PASS` 且填写审核人才会批准单集，五集状态自动汇总。
- 新增 `scripts/qc_episode_masters.py`，逐集检查完整解码、H.264/AAC、1080×1920、24fps、成片时长、非静音音轨、字幕时序/安全行和烧录差异；五集 30 项客观检查全部 `PASS`，最大时长误差 0.048 秒。
- 已生成三个可替换真实动作测试输入包：`MOTIONTEST-001`（Runway，小蓬莱开场）、`MOTIONTEST-002`（Wan，百草仙子微动作）、`MOTIONTEST-003`（OpenAI Sora，嫦娥衣袂与花瓣）；输入与提示词记录在 `provider-tests/s01e001/motion-provider-tests.json`，Web 可查看，均为 `BLOCKED_PENDING_AUTHORIZATION`，未上传、未调用、未产生费用。
- 已创建可恢复快照 `SNP-20260918T004726396Z-P28-FIVE-EPISODE-LOCAL-MASTERS`，锁定当前五集母版清单；项目首页已改为正确展示五集试播状态。
- 当前五集母版生成状态为 `COMPLETED`、技术 QC 为 `PASS`，人工审核保持 `PENDING`，不会自动发布。`P28-01` 仍在执行：下一步是逐集人审；真实 Provider 仅在用户明确选择服务商并授权上传与计费后才可运行。

P28-01 Web pip wheel 安装器绕过修复（2026-09-18）：

- 实机进一步确认：Pillow 12.3.0 的 `cp314-cp314-macosx_11_0_arm64.whl` 已成功下载，失败仅发生在 pip 26.2.1 的 wheel 安装阶段，报 `ImportError: No module named 'pip._internal.operations.install.wheel'`。
- 启动器不再执行 `pip install`；改为 `pip download --only-binary=:all:` 只做版本解析、平台匹配和 wheel 下载，然后使用项目自带 `support/web-python/install_wheels.py` 通过 Python 标准库 `zipfile` 安装到 `.web-python/`。
- 自有 wheel 解包器包含路径穿越保护，并处理 wheel `.data/purelib`、`.data/platlib`、`.data/data` 映射；不依赖 pip 的内部 install API。
- wheel 下载缓存放在 `cache/web-wheels/`，继续使用 macOS 版本补丁、legacy certs、arm64 Python 与 `PYTHONNOUSERSITE=1`。
- 默认 Web 端口仍为 `18765`；本修复不改变 P28 人工审核状态，不触发远程 Provider。

P28-01 Web macOS 版本探测修复（2026-09-18）：

- 实机第三次确认：即使 pip 使用 legacy certs，`packaging.tags` 仍因 `platform.mac_ver()` 返回空字符串而在计算 macOS wheel 标签时崩溃；这是 macOS 26 上已有同类报告的兼容问题。
- 新增 `support/web-python/sitecustomize.py`：Python 启动时仅在 `platform.mac_ver()` 为空时调用系统 `/usr/bin/sw_vers -productVersion`，把真实 macOS 版本补回；架构仍由原生 arm64 Python 自身报告。
- Web 启动器在 pip、自检和 Web 运行三个阶段统一把该目录加入 `PYTHONPATH`，因此 truststore、packaging 和后续依赖看到同一份有效 macOS 版本。
- 保留 `--use-deprecated=legacy-certs` 作为证书后端兼容保护；不修改系统文件、不覆盖 `sw_vers`、不伪造固定 26.x 版本。
- 默认端口保持 `18765`，P28 人工审核状态不变，远程 Provider 继续保持阻断。

P28-01 Web pip truststore 兼容修复（2026-09-18）：

- 实机确认 `.web-python` 新链路已进入基础 Python 的 pip 安装阶段；当前失败来自 pip 26.2.1 的 macOS truststore 初始化，`platform.mac_ver()` 返回空版本导致 `ValueError`。
- Web 依赖安装命令新增 `--use-deprecated=legacy-certs`，显式绕过 truststore 系统证书后端；不修改系统证书、不降级 Python、不重装 Homebrew。
- 项目继续使用 arm64 `/opt/homebrew/bin/python3` + 私有 `.web-python/` + `PYTHONNOUSERSITE=1`；默认端口仍为 `18765`。
- 本修复只影响 pip 下载时的证书后端选择，不改变 P28 人工审核状态，也不触发远程 Provider。

P28-01 Web ensurepip 绕过修复（2026-09-18）：

- 实机日志确认 Homebrew arm64 Python 3.14.7 已成功安装；当前失败点是 `python -m venv` 内部 `ensurepip` 返回非零，不再属于 Python 缺失或 CPU 架构问题。
- Web 环境实现从 `.venv-web` 改为“原生 arm64 Python + 项目私有 `.web-python/` 依赖目录”，完全绕过 `venv/ensurepip`。
- 依赖通过基础 Python 的 `pip --target .web-python` 安装；运行时固定 `PYTHONNOUSERSITE=1` + `PYTHONPATH=.web-python`，继续隔离 `~/Library/Python` 旧 Pillow。
- 新启动器会自动删除此前失败残留的 `.venv-web`，requirements 哈希变化时重建 `.web-python`；启动前仍验证 arm64 架构和 Pillow import。
- `.venv-web/` 与 `.web-python/` 均加入 Git 忽略；默认端口保持 `18765`，本修复不改变 P28 人工审核状态，也不触发远程 Provider。

P28-01 Web arm64 Python 自动引导修复（2026-09-18）：

- 实机第二次启动确认本机 PATH 下没有可直接使用的 arm64 Python；原隔离脚本只能检测并退出，仍需人工安装。
- `start-web.command` 现在先扫描 `/opt/homebrew/bin/python3` 及 Homebrew `python@3.12/3.13/3.14` 常见路径，再检查 PATH 与系统 Python，仅接受 Apple Silicon 下实际报告 `arm64` 的解释器。
- 如果仍未找到且存在原生 `/opt/homebrew/bin/brew`，默认自动执行 `arch -arm64 /opt/homebrew/bin/brew install python`，安装日志继续写入 `logs/web-env.log`，然后自动创建 `.venv-web`。
- 可通过 `VIDEO_CREATOR_AUTO_INSTALL_PYTHON=0` 禁用自动安装；脚本不会使用可能属于 Intel Homebrew 的 `/usr/local/bin/brew` 作为自动引导来源。
- 默认 Web 端口保持 `18765`；本修复不改变 P28 人工审核状态，也不触发远程 Provider。

P28-01 Web Python 架构隔离修复（2026-09-18）：

- 实机启动失败定位为 Python/Pillow 架构混用：Web 进程为 x86_64，而用户目录中的 Pillow `_imaging` 为 arm64，导致 `ImportError: incompatible architecture`。
- `start-web.command` 改为项目级 `.venv-web` 独立环境；Apple Silicon 优先选择原生 arm64 Python，并明确拒绝 x86_64 基础 Python，避免继承 `~/Library/Python/.../site-packages` 历史污染。
- 新增 `requirements-web.txt`，Web 首次启动自动安装 Pillow；依赖文件哈希写入 venv，仅在 requirements 变化时重装。
- 启动前执行 Python 架构与 Pillow import 自检；错误架构的既有 `.venv-web` 会自动删除重建；Web 运行时强制 `PYTHONNOUSERSITE=1`。
- 新增 `logs/web-env.log` 用于环境安装诊断，并将 `.venv-web/` 加入 Git 忽略；默认端口继续保持 `18765`。
- 本修复只解决本机 Web 运行环境，不改变 P28 人工审核状态，也不触发远程 Provider。

P28-01 Web 默认端口迁移（2026-09-18）：

- 本机端口 `8765` 已被其他服务占用，VideoCreator Web Console 默认端口统一迁移到 `18765`。
- `start-web.command`、`restart-web.command`、`scripts/web_server.py`、README 与 `docs/WEB-OPERATIONS.md` 已统一使用 `127.0.0.1:18765`。
- 仍支持通过 `VIDEO_CREATOR_WEB_PORT` 临时覆盖；端口冲突保护保持不变，不会自动杀死占用端口的其他服务。
- 新默认访问地址：`http://127.0.0.1:18765`。
- 本次仅修改 Web 本机监听默认值，不改变 P28 人工审核状态，也不启动远程 Provider。

P28-01 Web 运维脚本增量（2026-09-18）：

- 在继续 Godot / Blender 等动画路线前，先补齐本机 Web Console 的可靠启动与重启入口：新增根目录 `start-web.command` 和 `restart-web.command`。
- 默认后台启动 `scripts/web_server.py` 于 `127.0.0.1:18765`；PID 保存到 `cache/web-server.pid`，详细日志写入 `logs/web-server.log`，启动完成前执行 HTTP 健康检查。
- 启动脚本具备单实例保护：已运行时只返回当前 URL/PID；端口被无关服务占用时拒绝启动，不自动抢占或误杀其他进程。
- 重启脚本通过 PID、项目路径与监听端口识别当前仓库 Web，只停止本项目实例；优先 TERM，超时才 KILL，然后复用统一启动脚本。
- 支持 `VIDEO_CREATOR_WEB_HOST`、`VIDEO_CREATOR_WEB_PORT`、`VIDEO_CREATOR_PYTHON` 临时覆盖；新增 `docs/WEB-OPERATIONS.md` 并更新 README 的推荐启动方式。
- 本增量不启动 ArcReel、不调用远程 AI、不改变 P28 人工审核状态；完成此运维入口后再继续非生成式动画路线实施。

P28-01 Blender 5.2 图像序列输出兼容修复（2026-09-19）：

- 实机 Blender 5.2.1 LTS 执行 `render-reference-demo.command` 失败：`scene.render.image_settings.file_format = "FFMPEG"` 在 5.2 已不再合法，枚举只包含图像格式，导致 TypeError 并在第 145 行中止。
- 根据 Blender 5.2 Output 模型，Blockout 主链改为“Blender PNG 图像序列 → 项目 FFmpeg 编码 MP4”；不再依赖 Blender 内部视频编码 API。
- `reference-dialogue-blockout.py` 现在固定渲染 144 张 `frame_0001.png ... frame_0144.png`，PNG/RGB/8-bit，并在首尾帧存在后才输出 PASS marker；仍保存可编辑 `.blend`。
- `render-reference-demo.command` 会清理旧帧、检查 Blender 与 FFmpeg、验证恰好 144 帧，再用 `libx264 + yuv420p + faststart` 生成 `cache/reference-dialogue-blockout.mp4`；任何缺帧或编码失败均 FAIL。
- 此改法同时提升可恢复性：后续正式长镜头可按图像序列做断点续渲，不被单次视频容器写入失败拖垮。
- NEXT 不变：重新运行 `./render-reference-demo.command`，只审核双角色体型差、站位、视线、夕阳灯光、景深与镜头推进，不把代理几何当最终角色质量。

P28-01 参考视频 Style Bible 与双角色 Demo Blockout（2026-09-19）：

- 已实际读取用户上传的 44.13 秒屏幕录制并抽取关键帧；视觉基准不再是模糊“国风动漫”描述，而是明确记录为“半写实成年男角色 + 幼态/Q版小女孩 + 暖色夕阳电影光 + 浅景深 + 历史营地环境 + 对话表演”的混合 3D 动漫风格。
- 新增 `config/style-ref-guofeng-dialogue-001.json`：冻结成年人与儿童两套比例系统、脸型/眼睛差异、服装材质、夕阳逆光/冷填充、50–85mm 镜头语言、景深、成人左/儿童右的构图关系、对话动作节奏、NPR/线稿边界和人工质量门。
- 首个 Blender Demo 从“百花仙子单人抬手”正式改为 `DEMO-BLENDER-DIALOGUE-001` 双角色 6 秒对话镜头；目标是验证与参考视频相同类型的角色体积、成人/儿童风格差异、视线关系、电影光、景深和表演，而不是先扩展小说角色资产。
- 新增 `support/blender/reference-dialogue-blockout.py`：用本地代理几何快速建立成年男/小女孩双角色、儿童大头大眼比例、营地背景轮廓、暖色逆光+冷填充、68mm Camera、DOF 和 144 帧对话节奏；输出只用于构图/镜头/灯光/节奏验证，不冒充最终角色模型。
- 新增 `render-reference-demo.command`：一键调用 arm64 Blender 后台渲染 `cache/reference-dialogue-blockout.mp4` 和可继续编辑的 `cache/reference-dialogue-blockout.blend`。
- 参考源 UI 自身标注“包含 AI 生成素材”，因此本项目只把它作为视觉目标参考，不假设其原始制作技术；我们的当前实现仍保持 Blender 本地非生成式主线。
- NEXT：本机先 PASS `install-blender.command`，随后运行 `render-reference-demo.command` 生成双角色 Blockout。用户只审核构图/镜头/灯光/体型差异；Blockout 通过后才进入正式成年男角色 + 小女孩 LookDev，不在代理几何上继续堆细节。

P28-01 Blender Anime 基础工具链增量（2026-09-19）：

- 新增 `BLENDER_ANIME` 机器路线并设为 `production_target_route`；`LOCAL_CUTOUT_RIG` 明确为 `animatic_route`，Godot 改为 `EXPERIMENTAL_DEFERRED`。
- Blender 版本锁定 5.2 LTS API 窗口（>=5.2.0 且 <5.3.0），Apple Silicon 统一强制 arm64；新增 `config/blender-anime.json`、`adapters/motion/blender_anime.py` 和回归测试。
- 新增 `install-blender.command` / `check-blender.command`：不存在时使用原生 Homebrew `blender@lts` cask 安装，随后无界面执行 EEVEE + Armature + Camera + Light + PNG render smoke；smoke 输出固定到 `cache/blender-anime-smoke.png`。
- 根据 Blender 5.2 Python API 将 EEVEE engine id 固定为 `BLENDER_EEVEE`，避免沿用旧版 `BLENDER_EEVEE_NEXT` 导致首跑失败。
- 新增 `templates/blender-anime-demo.json`，首个正式质量验证只做百花仙子 6 秒代表镜头，不一次性建模九个角色。
- 更新 `docs/NON-GENERATIVE-ANIMATION.md` 与新增 `docs/BLENDER-ANIME.md`；视觉通过标准明确包含体积、真实透视、NPR、线稿、服装层次、头发/衣袖次级运动、真实镜头空间和人工视觉审核。
- 当前只完成 Blender 基础环境/自动化契约，尚未宣称百花仙子模型或参考 TikTok 风格已复现。NEXT：本机安装与 smoke PASS，然后基于用户上传的参考视频/关键帧冻结 Style Bible 并制作 5–8 秒 Demo。

P28-01 Blender Anime 正式成片路线切换（2026-09-19）：

- 用户明确否定继续以 Cutout/Godot 2.5D 作为国风动漫最终画面路线：即使 2.5D 做完，视觉上仍受单张正面立绘、缺少真实体积/透视/衣物厚度/转身信息的上限约束，难以达到目标国风动漫观感。
- 路线职责重新冻结：`LOCAL_CUTOUT_RIG` 继续 ACTIVE，但职责降为 Animatic/对白粗剪/镜头时长预演；`GODOT_CUTOUT` 降为 `EXPERIMENTAL_DEFERRED`，保留已有代码但不再作为当前 NEXT；新增 `BLENDER_ANIME` 作为正式成片目标路线。
- `BLENDER_ANIME` 目标不是“Grease Pencil 替代 Godot”，而是完整的 3D→2D/NPR 国漫生产链：3D Character + Armature/IK + Shape Keys + Hair/Cloth secondary + Toon/NPR Shader + Grease Pencil/Line Art + Camera + Lighting + FX + Compositing。
- Blender 生产基线锁定当前 active LTS 5.2 系列，最低 5.2.0；Apple Silicon 强制 arm64 运行。正式接入先完成安装/smoke，再只做一个百花仙子 5～8 秒代表镜头，不一次性返工 9 个角色。
- 首个 Blender Anime Demo 验收目标：竖屏 1080×1920、24fps、明显角色体积和透视、头发/衣袖层次、真实肩肘腕动作、镜头轻推、前中后景、Toon/NPR 明暗、线稿/轮廓、国风粒子/氛围；最终视觉必须人工审核。
- TikTok 参考短链当前在 ChatGPT Web 环境无法解析，禁止假装已看过；用户需补视频本体或关键帧后才能做“同款”逐项对齐。该缺口不阻塞 Blender 主线基础搭建。
- 远程 AI Video 继续 `OPTIONAL_BLOCKED`；本路线切换不触发上传、付费 Provider 或自动发布。P28 五集旧母版人工审核状态保持 `PENDING`，新 Demo 是质量路线验证，不冒充旧 P28 人审通过。

P28-01 Godot 2.5D 动作预览增量（2026-09-18）：

- 用户实机反馈：即使 Rig V2 自动分层成功，编辑器静态画面仍明显是平面立绘。该反馈成立；Rig V2/IK readiness 只证明资产可驱动，不代表视觉质量已经脱离“纸片感”。
- 新增 `support/godot/25d-preview` 与 `scripts/render_godot_25d_preview.py`：读取真实 Rig V2 层，调用 Godot Movie Maker 本地离线输出 4 秒动作预览，再通过 FFmpeg 转成 H.264 MP4。
- 首版预览组合：父子 Pivot 层级、呼吸、头部次级运动、人物左臂抬手→停留→回收、另一侧轻微惯性、层间视差、局部 squash/secondary motion、接触阴影和轻微整体镜头漂移；全部本地，无上传/计费。
- Web Rig V2 工作台新增“生成 2.5D 动作预览”，直接在页面内播放视频；以后不再用静态分层编辑画面评价 Godot 动画效果。
- `GODOT_CUTOUT` 机器策略升级为 `2_5D_PREVIEW_CODE_READY`，但仍 `implemented=false`；新增视觉质量门，至少要求 articulated motion、parallax、secondary motion、contact shadow、mesh deformation、人工视觉审核全部满足，Rig V2/IK READY 本身不能视为生产通过。
- 当前首版预览仍未宣称具备真正 mesh deformation；NEXT 是先在百花仙子实机输出该视频并判断“纸片感”改善程度，再决定继续 Polygon2D/mesh deformation，或提前进入 Blender Grease Pencil 对比。

P28-01 Rig V2 新手引导与自动生成增量（2026-09-18）：

- 新增 `scripts/rig_v2_auto_draft.py`：完全本地、非生成式、无远程调用，根据 V1 源图透明像素边界、既有 head/torso 比例和人体几何比例，自动提出 8 个上半身 polygon + Pivot 草稿；人物左侧按正面角色规则映射到画面右侧。
- 自动草稿包含 HIGH/MEDIUM/LOW 置信度与逐层说明；手部/宽袖明确标低置信度，避免把几何启发式包装成精准人体理解。
- Web Rig V2 工作台默认开启“新手引导”：逐层显示第 N/8 步、当前部位、人物左右说明、Pivot 应放位置，并提供上一层/下一层。
- 首次打开且没有历史分层时，系统自动加载本地草稿；用户可以自由修改，也可点击“重新自动草稿”覆盖当前草稿。
- 新增“一键自动生成 Rig V2”：直接用本地草稿生成透明层、登记 Rig V2、重新计算 Godot readiness；自动结果固定 `human_review=PENDING`，不会视为人工验收通过。
- 新增 Web API `rig-v2-auto-draft` / `rig-v2-auto-generate`，restart preflight 同步检查自动草稿模块；不上传图片、不调用 AI 视频或远程 Provider。
- NEXT：用户可直接一键自动生成百花仙子 Rig V2；若上半身 IK readiness=READY，再进入首个真实抬手/指向动作。如果自动分层视觉不理想，再由新手引导逐层微调。

P28-01 Rig V2 编辑器全屏布局修复（2026-09-18）：

- 实机截图确认 Rig V2 编辑器被 `.character-asset-gallery` 的 auto-fill Grid 当成单个约 190px 卡片布局，导致控制区严重挤压、原图 Canvas 几乎不可操作。
- Web 编辑器改为固定全屏工作台：viewport 内悬浮，左侧大 Canvas、右侧 330px 控制栏，页面背景滚动锁定；关闭后恢复角色列表。
- Canvas 区新增棋盘背景、独立滚动、适配画布、放大、缩小；点击坐标仍按 Canvas 内部真实分辨率换算，不因 CSS 缩放改变 polygon/pivot 数据。
- 小屏宽度 <980px 自动切成“上方画布 + 下方控制栏”，保证笔记本/窄窗口也能编辑。
- 本修复仅改变 Web 编辑体验，不改变 Rig V2 数据结构、IK 算法、P28 人审状态。

P28-01 Web restart 预检与 Rig readiness 语法修复（2026-09-18）：

- 实机 `./restart-web.command` 停止旧 Web 后启动失败，根因是 `scripts/godot_rig_readiness.py` 第 11 行把换行误写成字面量 `\\n`，导致 Python `SyntaxError: unexpected character after line continuation character`。
- 已将 V1/V2 manifest 常量恢复为两个真实 Python 行。
- `restart-web.command` 新增 stop-before-preflight 保护：在停止旧 Web 前先对 `web_server.py`、`godot_rig_readiness.py`、`build_character_rig_v2.py`、`rig_v2_segment.py` 执行 `py_compile`，随后真实 `import scripts.web_server`；任何语法/导入错误都会直接 FAIL，旧 Web 保持运行。
- 预检使用项目私有 `.web-python` + `support/web-python`，并优先选择 `VIDEO_CREATOR_PYTHON` / `/opt/homebrew/bin/python3`，与现行 Web 环境保持一致。
- 本修复不改变 18765 端口、P28 人审状态或远程 Provider 策略。

P28-01 Godot 4.7.2 TwoBoneIK smoke 类型/Rest 修复（2026-09-18）：

- 实机 `check-godot.command` 首次 IK smoke 失败：Godot 4.7.2 在当前 warning-as-error 设置下拒绝 `abs()/clamp()` 等 Variant 返回值配合 `:=` 的隐式类型推断，导致 `two_bone_ik.gd` parse error。
- `two_bone_ik.gd` 全部数值局部变量改为显式 `float` / `Vector2`，并使用 `absf` / `clampf`，避免 inference-on-Variant warning 被提升为 error。
- smoke 场景去掉运行时导出的 Script 实例，改为 `preload` + static solver 调用，减少动态 Variant 调用面。
- 同一实机日志出现 `affine_invert det == 0`；Godot Bone2D 的 rest 默认是零 Transform2D。运行时创建 upper/forearm 后现在显式把当前 transform 写入 `rest`，避免 Skeleton2D 对不可逆 rest 求逆。
- 本修复不改变 IK 数学、Rig V2 schema、P28 人审状态或远程 Provider 策略。

P28-01 百花仙子 Rig V2 本地分层工作台增量（2026-09-18）：

- 新增 `scripts/rig_v2_segment.py`：根据人工绘制 polygon 从本地源 PNG 裁出真实透明层，保留原画布对齐；每层必须具备可见像素和 pivot，完成后直接调用 Rig V2 builder 登记版本资产。
- 分层工作文件会保存 polygon、pivot、z-index 到 `visual-bible/rig-v2-work/`，支持刷新后继续；不上传图片、不调用生成模型。
- Web“角色美术”新增 `Rig V2 / Godot IK` 编辑器：直接显示本地角色源图，逐层勾选 head/torso/左右上臂/前臂/手，支持撤销、清空、Pivot 模式和一键生成 Rig V2；保存后立即重新计算 Godot readiness。
- 新增 `support/godot/runtime/two_bone_ik.gd` 自有余弦定理 TwoBoneIK solver，以及真实 Bone2D 链数值 smoke；`install-godot.command` / `check-godot.command` 现在同时检查 Skeleton2D 基础和 IK 端点误差。
- 选择自有 IK backend 的原因：Godot 官方 `SkeletonModification2DTwoBoneIK` 当前仍标记 Experimental；VideoCreator 仍使用 Godot 原生 Skeleton2D/Bone2D，但生产解算不被实验性 API 单点绑定。
- 当前代码链已经推进到“需要本地人工标注百花仙子真实肢体轮廓和 Pivot”的门前；没有伪造 V2 资产。标注完成并显示 `GODOT_UPPER_BODY_IK=READY` 后，NEXT 才进入百花仙子首个实际抬手/指向动作输出。

P28-01 Godot Rosetta/ARM 安装修复（2026-09-18）：

- 实机确认当前终端会话运行在 Rosetta 2/x86_64，而原脚本直接调用 ARM Homebrew 前缀 `/opt/homebrew`，导致 Homebrew 拒绝安装：`Cannot install under Rosetta 2 in ARM default prefix`。
- Godot 当前 Homebrew 包为 cask；安装命令改为 `/usr/bin/arch -arm64 /opt/homebrew/bin/brew install --cask godot`，与 Homebrew 当前 Godot 4.7.2 cask 保持一致。
- Godot 二进制发现顺序改为优先 `/opt/homebrew/bin/godot` 和 `/Applications/Godot.app/Contents/MacOS/Godot`，最后才使用 PATH，避免 `/usr/local` Intel 命令遮蔽原生 ARM 版本。
- `install-godot.command` 与 `check-godot.command` 的版本读取和 headless smoke 统一通过 `/usr/bin/arch -arm64` 启动 Godot，保证即使父终端处于 Rosetta 也使用 ARM slice。
- `config/godot-cutout.json` 与 Adapter 候选顺序同步更新；默认版本门仍为 stable >= 4.7.2，P28 人工审核状态不变。

P28-01 Rig V2 骨骼资产契约增量（2026-09-18）：

- 新增 `scripts/build_character_rig_v2.py`，不再用整张立绘模拟关节；Godot IK 资产必须提供独立透明肢体层、父子骨骼关系、canvas 对齐、pivot、z-index 和来源资产 ID。
- 支持 `GODOT_UPPER_BODY_IK` 与 `GODOT_FULL_BODY_IK` 两种模板/构建模式；构建结果写入独立 `visual-bible/character-rigs-v2.json`，逐层登记版本资产，并生成左右手臂/腿部 joint chain；人工审核仍固定 `PENDING`。
- `godot_rig_readiness.py` 改为同时读取 V1/V2，按角色优先 V2，不删除旧 V1 历史；因此单个角色升级后可以独立进入 Godot 路线，不要求九个角色一次性全部返工。
- 修复 macOS 安装脚本的版本比较：不再依赖 GNU `sort -V`，改成 Bash 数字段比较，兼容 macOS 自带 BSD 工具链。
- 新增 Rig V2 构建测试。当前没有伪造任何真实 V2 角色资产；下一实际资产任务仍是百花仙子上半身分层与 pivot 标注，然后再进入真实 TwoBoneIK 动作验证。

P28-01 Godot Skeleton2D/IK 基础接入增量（2026-09-18）：

- 非生成式路线进入实际实施：新增 `adapters/motion/godot_cutout.py`，负责 Godot 二进制发现、稳定版版本门、环境探测和本地 smoke command；当前生产最低版本固定为 Godot 4.7.2 stable，拒绝 dev/alpha/beta/rc。
- 新增根目录 `install-godot.command` 与 `check-godot.command`；macOS 可用 Homebrew 安装 Godot，并通过 `support/godot/smoke` 的 Skeleton2D + Bone2D 场景做本地无网络 smoke 检查。
- 新增 `scripts/godot_rig_readiness.py`：正式区分 `LOCAL_CUTOUT_RIG`、`GODOT_UPPER_BODY_IK`、`GODOT_FULL_BODY_IK` 三档资产 readiness。现有 head/torso/lower Rig 仍可用于本地 Cutout，但不会被误判为 IK-ready。
- Rig V2 标准层命名冻结：head/torso/pelvis、左右 upper_arm/forearm/hand、左右 thigh/shin/foot；上半身 IK 与全身 IK 分别输出缺失层清单。
- `config/animation-routes.json` 中 `GODOT_CUTOUT` 保持 `implemented=false`，但增加 `implementation_stage=FOUNDATION_READY`、最低版本、stable-only、Rig V2 要求和 smoke project；不因只完成框架而虚报 Godot 已生产可用。
- 新增 Godot Adapter / Rig readiness 回归测试与 `docs/GODOT-CUTOUT.md`。当前下一技术工作是“Rig V2 分层 + 1 个代表角色上半身 IK”，P28 五集人工审核仍为 `PENDING`，远程 Provider 不启用。

P28-01 非生成式动画机器策略增量（2026-09-18）：

- 新增 `config/animation-routes.json`，把动画路线变成 Codex/脚本可读取的机器策略；默认固定为 `LOCAL_CUTOUT_RIG`，远程生成默认关闭。
- 本地候选登记 `GODOT_CUTOUT`、`BLENDER_GREASE_PENCIL`，专用角色候选登记 `LIVE2D_CUBISM`、`SPINE_SKELETAL`，并明确安装/许可证审查状态；`MANUAL_IMPORT` 保持可用人工兜底。
- `REMOTE_AI_VIDEO` 仅登记为 `OPTIONAL_BLOCKED`，不能成为默认 ACTIVE 路线；策略强制要求上传授权和计费确认。
- 新增 `scripts/validate_animation_routes.py` 与回归测试，防止后续改配置时误把远程 AI 变成默认路线或移除人工发布门。
- 本增量只冻结路线和门禁，不安装 Godot/Blender/Live2D/Spine，也不触发任何远程生成；P28-01 五集人工审核状态保持 `PENDING`。

P28-01 非生成式动画路线冻结（2026-09-18）：

- 动漫生产不再以 AI 生图/AI 生视频作为默认前提；现有分层 PNG + Rig + 嘴型/表情 cue + Pillow/FFmpeg 正式定义为 `LOCAL_CUTOUT_RIG` 主链路，可在资产首次完成后长期复用。
- 下一层本地增强路线定义为 `GODOT_CUTOUT`：用于骨骼、IK、网格形变、粒子和复杂角色动作；保持 Scene/Shot JSON 作为上游契约，不把业务流程绑定 Godot。
- 电影感或手绘增强路线定义为 `BLENDER_GREASE_PENCIL`：用于 2D/2.5D 镜头、逐帧补间、骨架/父级驱动、镜头运动和特殊动作；通过 Adapter 输出标准视频资产。
- `LIVE2D_CUBISM` 作为对白特写/表情/口型候选；`SPINE_SKELETAL` 作为商业骨骼/IK 候选。两者在正式接入前必须完成许可证与成本审查。
- Runway / Wan / OpenAI Sora 等远程生成式 Provider 从“验收必做”降级为“可选增强/质量基准”；没有明确上传与计费授权时永远不得自动选择。
- P28 三个代表镜头的动作质量对比改为“路线对比”而非“必须比较三个 AI Provider”；优先验证本地 Cutout、2D 骨骼和 Grease Pencil/人工关键帧，比较一致性、动作表现、制作耗时、可复用率与单集边际成本。
- 详细路线、适用镜头和接入边界记录在 `docs/NON-GENERATIVE-ANIMATION.md`。当前五集人工审核仍为 `PENDING`，本架构调整不绕过 P28-01 人审门。

P28-01 局部返工人审保护增量（2026-09-18）：

- 发现并修复局部返工风险：旧实现执行 `assemble_local_episodes.py --episode <id>` 时会把 `episode-masters.json` 重写成仅含被返工集，并可能抹掉其他集已经记录的人工审核。
- 新实现按五集计划合并旧清单与本次重渲染结果：未返工集完整保留原母版和人工审核；被返工集视为产物已变化，旧审核强制失效并恢复为剧情/画面/声音/字幕四项 `PENDING`。
- 五集总人工状态由逐集状态重新汇总；只有所有现存集均为 `APPROVED` 时总状态才为 `APPROVED`，任一返工集不会继承旧 PASS。
- 清单写入改为临时文件原子替换，并拒绝未知 Episode ID，避免误操作破坏 P28-01 审片记录。
- 新增回归测试覆盖“局部返工保留未改集审核、返工集审核失效、全量 APPROVED 聚合”三项关键行为；本增量不改变当前人工审核结论，`NEXT` 仍为 P28-01 逐集人审。

P28-01 GitHub 人工审片门同步（2026-09-18）：

- 已创建并分配 GitHub Issue #1：`P28-01: 五集逐集人工审片与验收门`，用于承载 E01～E05 的剧情、画面、声音、字幕与审核备注人工勾选。
- 五集母版生成状态继续保持 `COMPLETED`，技术 QC 继续保持 `PASS`；人工审核仍为 `PENDING`，因此 P28-01 不得标记 PASS。
- 任一集人工四项未全部通过前，不进入后续发布或扩大制作；最终发布仍要求人工确认。
- Runway / Wan / OpenAI Sora 三个真实动作 Provider 测试继续保持 `BLOCKED_PENDING_AUTHORIZATION`，本次未触发上传、调用或费用。
- `NEXT` 继续保持 `P28-01` 五集逐集人工审片；Issue #1 与本 TASK 必须保持一致。

执行完成后：

1. 更新本 TASK 中状态。
2. 记录 Git commit。
3. 输出 PASS / FAIL。
4. 指向下一任务。
5. 不提前执行后续阶段。

---

# 42. 任务维护规则

本文件禁止重命名。

版本升级：

```text
V1.0
V1.1
V1.2
V2.0
```

必须在文件内部更新版本，不创建：

```text
TASK-v2.md
TASK-final.md
TASK-new.md
```

每完成一个任务，修改：

```text
Status: TODO
```

为：

```text
Status: PASS
```

失败：

```text
Status: FAIL
```

阻塞：

```text
Status: BLOCKED
```

延期：

```text
Status: DEFERRED
```

任何架构变化必须优先更新本 TASK，再修改代码。

---

# 43. 项目最终原则

```text
稳定 > 炫技
真实素材 > AI 素材
可恢复 > 一次性脚本
模块化 > 强耦合
Provider 可替换 > 单一供应商
局部重跑 > 全量重跑
质量 > 数量
事实来源 > AI 猜测
成本可控 > 无限调用
人工最终确认 > 自动发布
```

**VideoCreator Engine 的目标不是“自动生成视频”，而是构建一套可以长期升级、复用、迭代和商业化的个人视频内容生产系统。**
