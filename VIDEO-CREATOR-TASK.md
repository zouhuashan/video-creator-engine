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
NEXT: P30-06/P31-02 启动 ComfyUI + 首张角色定妆板 + 小说导入 smoke
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

P28-02 v5 MPFB 检查门去 marker 化（2026-09-19）：

- 实机 `./check-mpfb.command` 出现“Blender/Python exit code 成功但日志 marker 缺失”的假 FAIL；说明 stdout marker 不适合作为第二个技术真值源。
- `check-mpfb.py` 改为成功后写 `cache/mpfb-check.json`，记录实际 MPFB root package、operator、HumanService API、TargetService macro API、macro keys 与 Blender version；任何 API 不可用直接抛异常，由 `--python-exit-code 1` 转为非 0。
- `check-mpfb.command` 与 `render-child-lookdev-v5.command` 现在以“Python exit code + 非空 status JSON”作为唯一技术门，不再 grep stdout marker；同时在 PASS 时打印实际 root package 和 Service API。
- NEXT：用户 `git pull` 后重新执行 `./check-mpfb.command`。若 PASS，再直接执行 `./render-child-lookdev-v5.command`。

P29 Web AI 生图工作台（2026-09-19）：

- 用户要求 OpenAI 生图备用路线必须直接落到现有 Web Console，禁止把日常使用建立在终端命令上。
- 新增 OpenAI 图片 Provider 配置、`CHAR-CHILD-001` 角色视觉锁、`SHOT-DEMO-001` 镜头配置和 dependency-free `support/providers/openai_image_provider.py`；默认模型为 GPT-Image-2，Provider 定位为 fallback / high-quality keyframe route。
- Web Console 新增独立导航 `AI 生图`，直接在 `http://127.0.0.1:18765` 完成：选择国漫项目、输入/保存 OpenAI API Key（仅当前服务进程）、生成角色定妆板、生成镜头关键帧、页面预览最近资产、人工标记 APPROVED / CHANGES_REQUESTED。
- 后端新增 `GET /api/image-studio/status`、`POST /api/image-studio/character-bible`、`POST /api/image-studio/keyframe`、`POST /api/image-studio/review`。远程生成仍要求显式计费确认；前端每次点击生成都会二次确认。
- 生图结果直接写入当前项目 `lookdev/image-studio/`，因此现有 `/media` 和项目媒体扫描可立即读取，不形成脱离 VideoCreator 的聊天旁路资产；每张图同步写 metadata JSON，默认 `review_status=PENDING`。
- OpenAI API Key 不写磁盘、不返回前端、不进入日志；如果当前 Web 进程已有 Sora 使用的 OpenAI Key，AI 生图会复用同一 session key。
- 当前状态：Web/API/Provider/Review 代码已落库；真实远程生图需要在用户本地 Web 服务加载新代码并由用户点击验证，未执行前不得标记为远程实机 PASS。
- NEXT：用户在 Web 的 `AI 生图` 页面点击生成 `CHAR-CHILD-001` 角色定妆板，人工审核通过后再生成首个镜头关键帧；随后把 APPROVED 关键帧接入 motion/video provider。

P28-02 最终 LookDev 拉通（2026-09-19）：

- 用户明确反馈当前推进过慢，要求停止持续研究人物建模，直接拉通 LookDev 并产生最终视觉效果。该要求升级为当前 P28-02 唯一 NEXT；后续不再以“裸体 basemesh checkpoint”作为阶段产物。
- 新增 `FINAL-CHILD-LOOKDEV-001`：以 v6 的真实 MPFB child basemesh 为底座，一次性加入动漫脸部视觉系统、大眼/虹膜/高光/眼睑、小嘴、双髻+刘海+侧发、青色发带/金饰、浅青白多层汉服、交领/腰封/前片/宽袖、暖夕阳 Rim、冷 Face Fill、Eye Light、82mm 人像镜头、f/2.8 景深和历史营地背景层次。
- 新增 `config/final-child-lookdev-001.json`、`support/blender/final-child-lookdev-001.py`、`render-final-child-lookdev.command` 与回归测试；正式输出 `renders/lookdev/final-child-lookdev-001.png` + `.blend`。
- 该产物直接按“是否读成参考方向里的国风动漫小女孩成片”验收，不再按裸模比例验收。技术 PASS 只说明脚本/渲染链成功；正式人审仍为 `PENDING`。
- 如果该最终 LookDev 仍明显不接近参考目标，下一步应直接切更强的角色资产/生成式角色外观路线，而不是继续对基础人体做 v7/v8 裸模比例微调。
- NEXT：用户执行 `./render-final-child-lookdev.command` 并提交 `renders/lookdev/final-child-lookdev-001.png`。

P28-02 Child LookDev v6 原生 MPFB child phenotype（2026-09-19）：

- 用户实机提交 `child-lookdev-v5.png`：连续真实人体 basemesh 已成功，primitive/公仔拼装问题彻底解决，因此“真实人体底层路线”技术 PASS；但视觉仍是明显成年女性体态（头小、肩胯/腿长成人化、胸部明显），P28-02 人工审核仍 FAIL。
- v5 证明底层路线正确，同时证明“默认成人 MPFB + 我们自己按身高区间改顶点”的 childify 方法不可靠；停止继续使用粗暴 age-region vertex deformation 作为儿童生成主手段。
- 对照 MPFB2 官方源码确认：New Human panel 使用 `SceneConfigSet(..., prefix="NH_")`，实际 Scene 属性全名为 `MPFB_NH_<property>`；`createhuman.py` 会直接读取这些属性并生成 macro phenotype。
- v6 新增 `config/child-lookdev-v6.json`、`support/blender/child-lookdev-v6.py`、`render-child-lookdev-v6.command`、回归测试。创建前强制写入并回读：`MPFB_NH_add_phenotype=True`、`phenotype_gender=female`、`phenotype_age=child`、`phenotype_race=asian`、`phenotype_muscle=minmuscle`、`phenotype_weight=averageweight`、`phenotype_height=minheight`、`phenotype_proportions=average`、`phenotype_influence=1.0`、`MPFB_NH_add_breast=False`。
- MPFB 官方 operator 对 child 的真实 macro 映射为 age=0.1875，对 female 的真实 gender macro 映射为 0.0；v6 不再自行伪造这些 macro。
- MPFB 原生 child basemesh 生成后仅做轻度动漫化：头部 XY +10%、Z +4%、肩部 -4%、腿部轻缩，最后归一化到约 1.28m；该步骤只是向参考中的幼态/chibi 方向推进，不替代原生 child macro。
- v6 技术成功必须同时出现 `VIDEO_CREATOR_MPFB_NATIVE_CHILD_PASS`、framing PASS 和最终 output PASS；人工视觉审核仍保持 `PENDING`。NEXT：用户执行 `./render-child-lookdev-v6.command` 并提交 `renders/lookdev/child-lookdev-v6.png`。

P28-02 v5 MPFB 实际安装修复（2026-09-19）：

- 用户实机输出已证明：Blender 5.2 三个已启用 extension repository 中都不存在 `mpfb/blender_manifest.toml`，因此此前所有 check/render 失败的最终根因是 MPFB 扩展并未真正安装到 Blender 5.2，而不是 module-name 推导问题。
- `install-mpfb.command` 改为严格安装链，不再忽略非零返回码：
  1. 强制 `--online-mode --command extension sync` 同步扩展仓库；
  2. 执行 `extension list -s` 并确认 package id `mpfb` 确实出现在官方仓库列表；
  3. 执行 `extension install -s -e mpfb` 安装并启用；
  4. 运行 `check-mpfb.py`，必须实际发现物理 package、启用真实 module、成功临时 `create_human()` 且得到有效人体 Mesh 才 PASS。
- 安装命令任何一步失败都会立即 FAIL 并打印对应日志尾，不再出现“安装失败但继续 validation”的假成功路径。
- NEXT：用户先 `git pull`，然后重新执行 `./install-mpfb.command`；只有看到 `PASS MPFB ready` 后再运行 `./render-child-lookdev-v5.command`。

P28-02 v5 MPFB extension repository discovery 修复（2026-09-19）：

- 用户再次执行 `check-mpfb.command` 时 `operator.get_rna_type()` 抛出 `KeyError: MPFB_OT_create_human not found`。这证明 Blender 的 `bpy.ops` 动态代理存在并不代表 operator 类已真正加载；之前的 operator-only 存在性检查仍不可靠。
- 根据 Blender 5.2 Extensions API，扩展仓库提供真实 `repo.module` 与 `repo.directory`；扩展 Python module 名应按当前仓库动态组成 `bl_ext.<repo.module>.mpfb`，不能硬编码 `blender_org` / `user_default`。
- `check-mpfb.py` 现在扫描 `bpy.context.preferences.extensions.repos`，只接受存在 `<repo.directory>/mpfb/blender_manifest.toml` 的真实安装；随后调用 `bpy.ops.preferences.addon_enable(module=真实模块名)` 主动加载 MPFB。
- check 不再读取 operator RNA 元数据，而是执行真实 smoke：调用一次 `bpy.ops.mpfb.create_human()`，确认 FINISHED、确实创建 Mesh 且主体顶点数 >1000，再删除所有临时对象并写 status JSON。只有真实创建成功才 PASS。
- `child-lookdev-v5.py` 同步加入相同 extension repo discovery/enable，保证 check PASS 与实际 render 使用完全相同的加载路径。
- NEXT：用户 `git pull` 后重新执行 `./check-mpfb.command`；如果 PASS，再执行 v5 render。

P28-02 v5 MPFB operator-only 自动化修复（2026-09-19）：

- 用户执行新版 `./check-mpfb.command` 时，`bpy.ops.mpfb.create_human` 已注册，但后台 Blender 无法 import `bl_ext.blender_org.mpfb` 或 `mpfb`；说明扩展内部 package path 在当前 Blender 5.2 安装中不可作为稳定自动化接口。
- v5 再次收紧边界：彻底移除 MPFB 内部模块/Service API 依赖，`check-mpfb.py` 只验证已注册的 `bpy.ops.mpfb.create_human` operator，并把 operator RNA property 列表写入 status JSON。
- `child-lookdev-v5.py` 改为直接 `bpy.ops.mpfb.create_human()` 创建真实连续人体 basemesh；从新建 Mesh 中选择顶点数最大的主体作为 `ChildMPFBBaseMesh`，隐藏其它 helper mesh。
- 为避免再次依赖 MPFB UI phenotype 参数，儿童化改为在真实连续 mesh 上直接做 vertex proportion edit：头部整体放大、肩胸收窄、腰胯轻收、腿部视觉缩短，之后统一归一化到 1.34m；不 remesh，不回退到 primitive 拼装。
- v5 的目标仍只是“真实连续人体底座质量门”，不是最终古装角色。NEXT：用户 `git pull` 后先 `./check-mpfb.command`，PASS 后直接 `./render-child-lookdev-v5.command`。

P28-02 MPFB check/install status-file 统一（2026-09-19）：

- 用户执行 `./check-mpfb.command` 出现 `FAIL MPFB validation marker missing`；该输出对应旧版 grep-marker 检查逻辑，而当前仓库的 `check-mpfb.command` 已升级为 status JSON 文件校验。
- 为消除三个命令判定方式不一致，`install-mpfb.command` 同步改为与 check/render 相同机制：通过环境变量 `VIDEO_CREATOR_MPFB_STATUS` 要求 `check-mpfb.py` 写入 `cache/mpfb-check.json`，只以状态文件存在且 Python 退出码为 0 判定 PASS，不再 grep 控制台 marker。
- `render-child-lookdev-v5.command` 已使用同一 status-file 机制；后续 MPFB 检查/安装/渲染三条链统一。
- NEXT：用户先 `git pull`，再执行 `./check-mpfb.command`；若 PASS，直接 `./render-child-lookdev-v5.command`，无需重装。

P28-02 v5 MPFB 官方 Service API 修复（2026-09-19）：

- v5 首次实机确认 MPFB 已安装且 `bpy.ops.mpfb.create_human` 可用，但脚本在创建人物前失败：`Scene` 中不存在猜测的 `add_phenotype` 属性。该 FAIL 不是 framing 问题，而是错误依赖 MPFB UI/Scene 属性。
- 对照 MPFB 官方 scripting API 后改为官方 Service 路线：通过 extension-safe dynamic import 获取 `HumanService` / `TargetService`，用 `TargetService.get_default_macro_info_dict()` 构建标准 macro 字典，再直接调用 `HumanService.create_human(macro_detail_dict=macro)`。
- phenotype 现在使用 MPFB 实际数值语义：`gender=0.0` female、`age=0.0` child、Asian race=1.0，并设置轻肌肉/平均体重/偏幼比例；不再扫描或写任何 Scene UI property。
- `check-mpfb.py` 同步升级：除 operator 外，还必须成功加载 `HumanService.create_human` 和 `TargetService.get_default_macro_info_dict`，避免“插件 UI 可用但自动化 Service 不可用”时误报 PASS。
- NEXT：无需重装 MPFB；用户 `git pull` 后直接重新执行 `./render-child-lookdev-v5.command`。

P28-02 Child LookDev v5 MPFB real basemesh 切换（2026-09-19）：

- 用户实机提交 v4：自动取景与 organic curve/loft 已正常工作，但人工审核仍不通过；角色仍明显是程序化玩偶，说明 procedural primitive/loft 路线已达到质量上限。
- 按既定质量门停止继续 v5/v6 堆 primitive，正式切换到真实连续人体 base mesh。选用 MPFB（MakeHuman Community Blender extension）作为本地非生成式人体基座；目标版本 2.0.17，Blender 5.2 可用。
- 新增 `install-mpfb.command` / `check-mpfb.command` / `support/blender/check-mpfb.py`：使用 Blender 官方 extension CLI 安装并启用 package id `mpfb`，随后验证 `bpy.ops.mpfb.create_human` 可用。
- 新增 `config/child-lookdev-v5.json` / `support/blender/child-lookdev-v5.py` / `render-child-lookdev-v5.command`：通过 MPFB child/female/asian/minheight phenotype 创建连续儿童 basemesh，归一化目标身高，保留真实脸/肩/臂/手拓扑，使用 EEVEE 简单 LookDev 灯光和自动取景输出 v5 PNG + BLEND。
- v5 是“真实 base mesh 质量门”，暂不把古装/头发/正式表情叠回去；先确认底层人体是否脱离公仔感。只有 base mesh 人审通过，才在该真实拓扑上继续 stylize、衣服、头发和 rig。
- P28-02 仍保持 `HUMAN REVIEW=PENDING`。NEXT：本机执行 `./install-mpfb.command`（首次）→ `./render-child-lookdev-v5.command`，提交 `renders/lookdev/child-lookdev-v5.png`。

P28-02 Child LookDev v4 自动取景修复（2026-09-19）：

- v4 首次实机执行被 framing gate 正确拦截：`TorsoOuter` 投影为 `y=-0.1144`，原因是 organic loft 躯干/裙摆比 v3 primitive 更长，而固定 85mm/固定距离镜头无法容纳整个人物；Blender 5.2 的 `World.use_nodes` / `Material.use_nodes` DeprecationWarning 只是 Blender 6.0 迁移提示，不是本次 FAIL 根因。
- v4 改为全人物 evaluated bounding-box 自动取景：在 stage 创建后记录对象集合，再构建 Child，收集新增 Mesh/Curve；通过 evaluated depsgraph 读取包含 Curve/Modifier 后的真实 world-space bounding-box 角点。
- 自动取景会计算角色几何中心，将 Camera/Target 对准该中心，并从近距离开始逐步后移 Camera，直到所有真实包围盒角点都进入 8% normalized safe frame 且深度为正；最多尝试 80 步，无法容纳则继续 FAIL。
- 镜头焦距从固定 85mm 调整为 72mm portrait baseline，但最终距离由角色真实 bounds 自动决定；后续继续修改头发、袖子、裙摆时无需人工重新猜 Camera 参数。
- NEXT：用户重新运行 `./render-child-lookdev-v4.command`；只有自动 framing PASS 后才真正渲染并提交 `child-lookdev-v4.png` 人工审核。

P28-02 Child LookDev v4 建模策略切换（2026-09-19）：

- 用户实机提交 `child-lookdev-v3.png`；v3 虽进一步减弱公仔脸，但人工审核仍未通过：刘海成为硬块/立柱，袖子仍像胶囊体，身体仍可明显读出“基础 primitive 堆叠”，已确认继续微调球体/方块路线收益不足。
- P28-02 v4 不再作为 v3 微调，而是切换建模策略为 `organic_curve_and_loft_mesh`；新增 `config/child-lookdev-v4.json`、`support/blender/child-lookdev-v4.py`、`render-child-lookdev-v4.command` 与回归测试。
- 头发改为 Bezier Curve tapered strands：刘海、侧发使用连续曲线和半径 taper，保留 HairCap/双髻作为大形体，不再使用矩形卡片/立柱发片。
- 躯干、裙摆、宽袖改为程序化 loft ellipse mesh：沿中心线生成连续椭圆截面并 Subdivision/Smooth，袖子从肩部到袖口逐渐放宽形成自然下垂 bell sleeve，不再以球/圆柱/胶囊直接充当最终布料体块。
- 脸继续收小并加强 chin taper；眼睛进一步缩小并嵌入脸面；鼻嘴保持低存在感；正式配色、Principled 材质、暖 Rim + 冷 Fill、85mm 人像镜头和 framing gate 保持。
- v4 技术成功仍只记 `PASS P28-02 v4 technical render`；人工审核保持 `PENDING`。NEXT：用户运行 `./render-child-lookdev-v4.command` 并提交 `renders/lookdev/child-lookdev-v4.png`；若 v4 仍明显是程序化低模公仔，则 P28-02 下一步不再继续堆 procedural primitive，而改为真实可编辑 base mesh / sculpt LookDev 路线。

P28-02 Child LookDev v3 视觉迭代（2026-09-19）：

- 用户实机提交 `child-lookdev-v2.png`；v2 相比 v1 已解决全白 clay、基础配色和眼神高光问题，但人工审核仍未通过：脸仍偏公仔/吉祥物，眼睛略外凸，刘海像五根立柱，侧发/双髻块状，袖子像圆管，服装仍偏几何玩具感。
- 新增 `config/child-lookdev-v3.json`、`support/blender/child-lookdev-v3.py`、`render-child-lookdev-v3.command` 与回归测试；v1/v2 历史产物继续保留。
- v3 头部进一步缩小并加强 chin taper；眼白/虹膜/瞳孔整体缩小并更靠近脸面，去掉凸起腮红几何，保留更轻的鼻嘴曲线，目标从 mascot/toy 转向 stylized child。
- v3 头发不再使用竖向椭球刘海：新增 flat ribbon hair lock 网格，五组刘海与两侧发片用扁平发束表达；双髻继续保留但降低规则球体感。
- v3 袖子不再使用面向相机的圆柱/锥管，改为纵向下垂的 smooth ellipsoid cloth masses；手部移到袖口下方，减少“管子插在身体上”的玩具感。
- 继续使用 Principled 节点材质、浅青白多层古装、暖 Rim + 冷 Fill + Eye Light、82mm 人像镜头和 camera-space framing gate。
- v3 技术成功仍只记 `PASS P28-02 v3 technical render`；人工审核保持 `PENDING`。NEXT：用户运行 `./render-child-lookdev-v3.command` 并提交 `renders/lookdev/child-lookdev-v3.png`；P28-02 未通过前不进入 P28-03。

P28-02 Child LookDev v2 视觉迭代（2026-09-19）：

- 用户实机提交 `child-lookdev-v1.png`；v1 灰模确认幼态/双髻/古装大轮廓方向可继续，但人工审核未通过：脸仍像球体公仔，眼睛像浮雕贴片，嘴鼻图标化，刘海/侧发块状，古装层次不足，且 EEVEE 实际渲染接近全白 clay，无法验证正式配色/光感。
- 新增 `config/child-lookdev-v2.json`、`support/blender/child-lookdev-v2.py`、`render-child-lookdev-v2.command` 与回归测试；v1 产物保留，不覆盖历史。
- v2 材质全部改为 `use_nodes=True` + Principled BSDF Base Color/Roughness/Metallic，避免只改 viewport diffuse_color 而正式 EEVEE 渲染仍接近白模；灯光能量同步收敛，保留暖 Rim + 冷 Fill + Eye Light。
- v2 头部使用程序化 taper：额头/脸颊更饱满、下巴更小；眼睛改为 sclera/iris/pupil/catchlight 多层结构，并增加上眼睑/眉毛曲线；嘴从 torus 圆环改为 Bezier 柔和嘴线，鼻子继续弱化。
- 头发改为不规则双髻、五组重叠刘海、曲线侧发、发带/发饰；服装补内外层、交领、腰封、前后垂片、宽袖与袖口，正式锁浅青/白/墨发/肤色配色。
- v2 保持 flat world-space 静帧变换，不引入不必要 parent，避免 v1/Blockout 已发现的双重变换风险；继续保留 camera-space framing gate。
- v2 技术成功仍只记 `PASS P28-02 v2 technical render`；人工视觉审核保持 `PENDING`。NEXT：用户执行 `./render-child-lookdev-v2.command` 并提交 `renders/lookdev/child-lookdev-v2.png`，未通过前不进入 P28-03 成年男主 LookDev。

P28-02 Child LookDev v1 执行开始（2026-09-19）：

- P28-02 已正式进入实现，不再停留在规格讨论；新增 `config/child-lookdev-v1.json`、`support/blender/child-lookdev-v1.py`、`render-child-lookdev.command` 和回归测试。
- Child LookDev v1 为完全本地 Blender 程序化静帧：幼态大头身比、圆脸、大眼/虹膜/高光、弱鼻小嘴、脸颊红润、双髻/刘海/侧发、浅蓝白古风交领/裙摆/宽袖/腰带/发饰；光照按参考视频使用暖夕阳 Rim + 冷面部 Fill + 轻眼神光，72mm + 浅景深。
- 固定产物：`renders/lookdev/child-lookdev-v1.png` 与 `renders/lookdev/child-lookdev-v1.blend`；当前仅验证角色 LookDev，不包含完整 Rig/动画。
- 新增 camera-space framing gate：头部、躯干、裙摆中心必须落在静帧安全画框内且纵向关系正确，防止技术渲染成功但人物构图失效。
- 技术渲染成功只输出 `PASS P28-02 technical render`；P28-02 人工视觉审核仍为 `PENDING`，必须由用户确认幼态感、五官、双髻、服装层次和参考光感后才能进入 P28-03。
- NEXT：用户本机执行 `./render-child-lookdev.command` 并提交 `child-lookdev-v1.png`；根据实际静帧直接迭代，未通过前不开始成年男主正式 LookDev。

P28-01 双角色 Blockout 构图/父级位移修复（2026-09-19）：

- 用户上传首版 `reference-dialogue-blockout.mp4` 后抽帧检查发现主体几乎全部落到画外，只剩右侧局部角色边缘；该产物视觉 FAIL，不能用于判断 Blender 路线质量。
- 根因定位到代理角色父级坐标：Adult/Child Root 已含横向位置，而子对象又按世界 X 创建后直接 parent，导致父级位移再次叠加，成人继续左移、儿童继续右移。
- 角色构建改为“Root 保存角色世界位置、所有子对象使用 Root-local 坐标”，避免双重平移；成人锁左、小女孩锁右，并补最基础手臂代理以验证说话手势轮廓。
- Camera 改为 52mm、目标 Empty + Track To；推进时只改变相机距离，目标始终保持双角色中心，避免移动 Camera 后旋转不更新造成构图漂移。
- 新增渲染前 camera-space framing gate：Adult head/body、Child head/body 四个关键点必须全部位于 8%–92% 安全画框且深度为正，同时成人头部 X 必须位于儿童头部左侧；失败则在 144 帧渲染前立即中止。
- `render-reference-demo.command` 新增 `VIDEO_CREATOR_REFERENCE_FRAMING_PASS` 硬门；没有构图 PASS marker 不再继续编码 MP4。
- NEXT：重新渲染双角色 Blockout。通过标准仍只看体型差、双人同框、视线、夕阳光、景深和镜头推进；代理模型外观不作为当前验收项。

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

## P29 最终视觉 Provider 化（2026-09-19）

- **现行架构已切换**：最终视觉不再以 Blender 为默认画质生产器；`config/animation-routes.json` 的 `production_target_route` 改为 `IMAGE_PROVIDER_ROUTER`。
- 新增 `config/visual-generation-routes.json`：Image Provider Router 是最终视觉主路由；OpenAI Image 当前作为 `HIGH_QUALITY_FALLBACK` / 手动高质量生图 Provider；所有远程计费调用继续要求明确确认，未来若上传参考图还必须单独获得上传授权。
- Blender 正式降级为 `AUXILIARY_3D_CONTROL`：只负责 camera blocking、pose reference、scene layout、lighting reference、FX assist 和可控 3D 辅助，不再承担默认最终角色画质。
- Web Console 已新增「AI 生图」页面：用户可直接在 `http://127.0.0.1:18765` 保存会话级 OpenAI Key、生成角色定妆板、生成镜头关键帧、预览历史结果并做人工审核；不要求命令行。
- 生图资产统一保存到当前项目 `lookdev/image-studio/`，metadata 的 `review_status` 默认 `PENDING`；人工通过前不得视为正式角色/镜头资产。
- NEXT：从 Web 的「AI 生图」生成并审核 `CHAR-CHILD-001` 定妆板，然后用审核通过的角色锁继续 SHOT keyframe → Motion Provider → Episode。


---

# 44. P30 — Software-First Pipeline Orchestrator（2026-09-19）

## P30-01 自动生产线架构冻结
Status: PASS

用户最终操作边界冻结为：

```text
输入小说/章节或选择现有项目
→ 点击“创建整集”
→ 查看机器流水线进度
→ 预览最终成片
→ 人工最终确认
```

除最终审核/发布外，凡是能够通过脚本、API、批处理、Headless 或 Provider 完成的工作，默认不得要求用户手工制作。

现行主架构：

```text
ChatGPT / Codex
      ↓
Pipeline Orchestrator
      ├── Story / Character / Shot Planner
      ├── Scene Control
      │     └── Blender Headless
      │          camera / pose / blocking / depth / normal / mask / composition only
      ├── ImageProvider Router
      │     ├── OpenAI Image
      │     └── ComfyUI (adapter slot)
      ├── VideoProvider Router
      │     ├── Local Ken Burns
      │     ├── OpenAI Sora
      │     ├── Runway
      │     ├── Wan
      │     └── ComfyUI (adapter slot)
      ├── TTS Provider
      ├── Subtitle Builder (script/TTS timing; no Whisper round-trip)
      ├── FFmpeg Finalizer
      ├── Auto QC
      └── Human Final Review
```

强制规则：

- Blender 永久保持 `AUXILIARY_3D_CONTROL`，不得重新升级为默认最终画质生产器。
- Prompt 必须由 Character Bible + Shot + Scene/Camera 约束自动生成；Web 主流程不要求用户手写 Prompt。
- ImageProvider / VideoProvider 必须可替换；核心 Orchestrator 禁止直接绑定单一供应商。
- OpenAI API Key 与其他密钥仍只允许保存在当前 Web 服务进程或环境变量，不写项目文件、不写日志。
- 字幕优先直接使用已知脚本与 TTS 时长生成；禁止为了拿回原文本再走 Whisper。
- FFmpeg 是最终总装厂；Premiere / After Effects / Nuke 不进入默认生产依赖。
- Auto QC 至少覆盖媒体完整性、技术规格、黑帧/异常帧接口、字幕/音频存在性，并允许失败镜头进入 AUTO_RETRY。
- Web Console 主流程必须提供：创建整集、进度、预览、人工确认；底层 Provider/手工调试页保留为高级工具。
- 正式发布仍必须人工确认，任何流水线不得自动发布平台内容。

P30-01 实施范围：

1. 新增统一 Pipeline Orchestrator 与持久化 run manifest。
2. 新增 VideoProvider Router，和现有 ImageProvider Router 对齐。
3. 固化 Character Bible JSON Schema。
4. 自动构建镜头 Prompt；用户输入 Prompt 只允许作为可选 override，不作为主路径。
5. 把 Web Console 接入 Pipeline status / run / review API。
6. 新增项目级 dry-run，验证从 Story/Character/Shot 到 Review Gate 的整条阶段图可以一次跑通。
7. 保留现有模块与 Provider，不大规模重写已经 PASS 的能力。
8. 正常输出保持 RUN / PASS / FAIL / NEXT；详细过程进入 logs。

验收：

```text
PASS: pipeline dry-run writes one machine-readable run manifest
PASS: image/video routing remains provider-neutral
PASS: Blender is auxiliary only
PASS: Web can trigger and inspect the pipeline without terminal commands
PASS: final review remains human-gated
PASS: no API secret is persisted
```

P30-01 执行记录（2026-09-19）：

- `scripts/pipeline_orchestrator.py` 已形成统一 12 阶段机器执行图：Story → Character → Shot → Scene Control → Prompt → Image → Video → TTS → Subtitles → FFmpeg Assembly → Auto QC → Human Review；run manifest 持久化到项目 `pipeline/run.json`。
- `config/pipeline-orchestrator.json` 新增机器可读的 `execution_policy`：默认 `software_first=true`、禁止把可自动化制作步骤退回人工，用户动作只保留 `SELECT_INPUT / FINAL_REVIEW / MANUAL_PUBLISH`。
- 每个 stage 现在显式记录 `owner` 与 `human_action`；除最终 review 外全部归 `software`，review 固定归 `human`。Blender 继续锁定 `AUXILIARY_3D_CONTROL`，不得产出默认最终视觉。
- ImageProvider Router、VideoProvider Router、Character Bible Schema、自动 Prompt、Web `/api/pipeline/status` / `run` / `review` 已接入；P29 Image Studio 与会话级密钥策略保持不变，run manifest 不保存 API Secret。
- 回归测试 `tests/test_pipeline_orchestrator.py` 增加软件/人工阶段所有权与用户动作边界断言；本轮 GitHub 连接环境未配置 Actions workflow，因此没有远程 CI 结果可引用，本地完整测试仍由仓库现有检查入口执行。
- Git commits：`7c839b3`（software-first policy）、`57c836e`（stage ownership）、`ed22794`（regression assertions）。
- P30-01 验收项从代码与配置层面全部满足；下一阶段不再继续人物建模研究，进入 ComfyUI 本地视觉工厂 Adapter。

NEXT：P30-02 ComfyUI 本地视觉工厂 Adapter。


## P30-02 ComfyUI 本地视觉工厂 Adapter
Status: PASS

目标：把 ComfyUI 从预留插槽升级为 VideoCreator Engine 可直接调用的本地视觉 Provider。用户不进入 ComfyUI 手工拖节点；Web 与 Pipeline 通过 HTTP API 自动完成健康检查、模型发现、Workflow 提交、任务轮询、图片下载、资产登记和人工审核。

强制边界：

- 默认 AUTO 路由必须本地优先：ComfyUI 可用时优先 `COMFYUI_IMAGE`，不可用时才考虑 `OPENAI_IMAGE` 高质量 fallback。
- ComfyUI 只作为 Provider，被 Pipeline Orchestrator 调度，不成为新的主工作台。
- 本地 ComfyUI 不需要 API Key；端点来自 Web 会话、`COMFYUI_BASE_URL` 或本地默认地址，不写入项目资产 metadata。
- OpenAI fallback 仍受远程计费确认门约束；AUTO 不得静默产生远程费用。
- 生成资产继续保存到 `lookdev/image-studio/`，`review_status=PENDING`，人工通过前不得视为正式资产。
- Blender 继续固定为 `AUXILIARY_3D_CONTROL`，不得恢复为最终视觉生产器。
- dry-run 禁止真实生成；execute 才允许调用本地 Provider。

验收：

```text
PASS: ComfyUI Image Adapter can health-check, discover checkpoint, queue workflow, poll and download output
PASS: ImageProvider Router supports local-first AUTO and OpenAI fallback
PASS: Web Image Studio exposes AUTO / ComfyUI / OpenAI without requiring terminal operations
PASS: Pipeline execute can call ComfyUI while dry-run stays side-effect free
PASS: output metadata defaults to PENDING human review
PASS: no API secret is persisted
PASS: regression tests cover local provider and routing
```

P30-02 执行记录（2026-09-20）：

- 新增 `support/providers/comfyui_image_provider.py` 与 `config/providers/comfyui-image-provider.json`：使用 ComfyUI HTTP API 完成 health、checkpoint 发现、API-format txt2img workflow、队列提交、history 轮询、输出下载；不要求用户进入 ComfyUI 拖节点。
- `config/visual-generation-routes.json` 和 `ImageProviderRouter` 已切到 `LOCAL_FIRST_FALLBACK_REMOTE`：AUTO 优先 `COMFYUI_IMAGE`，本地不可用时才考虑 `OPENAI_IMAGE`；远程 fallback 仍必须显式确认计费。
- Web「AI 生图」新增 `AUTO / ComfyUI / OpenAI` 路线、ComfyUI 本地地址保存/检测和本地状态展示；生成结果继续写入 `lookdev/image-studio/`，审核默认 `PENDING`。
- Pipeline execute 已可探测并调用本地 ComfyUI 生成 keyframe，dry-run 只规划不调用；run manifest 记录实际 Provider、fallback chain、remote 标志、输出和 metadata。OpenAI fallback 不会静默产生费用。
- 新增 `tests/test_comfyui_image_provider.py`，使用本地 fake HTTP server 覆盖 health、checkpoint、workflow、queue/history/view；扩展 Router 与 Pipeline 测试覆盖本地优先和 execute 模式。
- 新增 GitHub Actions `.github/workflows/p30-provider-regression.yml`。当前 GitHub 未产生 workflow run，因此不虚报 CI PASS；Web JS 已用 V8 做语法校验、相关 JSON 已做解析校验并通过。真实 Mac/GPU ComfyUI smoke 属于运行时验证，GitHub 连接器无法访问本机 127.0.0.1，但不阻塞代码架构继续推进。
- 关键提交：`cf62089`、`2f46b43`、`6213d71`、`7a11376`、`3a4266a`、`9fdbd03`、`51fe765`、`268f783`、`ef1567e`、`81ee391`、`085d42f`、`b953177`。
- P30-02 代码范围完成；Blender 仍固定 `AUXILIARY_3D_CONTROL`，最终视觉没有回退到传统人物建模路线。

NEXT：P30-03 TTS / 字幕 / FFmpeg 执行化。


## P30-03 TTS / 字幕 / FFmpeg 执行化
Status: PASS

目标：把 P30-01 中仍为 PLANNED 的 TTS、字幕和 Assembly 阶段变成可真实执行的软件步骤，最大化复用现有 `generate_local_tts.py`、音频资产、字幕和 FFmpeg 能力，不再要求用户手工录音、对字幕或进剪辑软件。

执行原则：

- 优先复用现有本地/Provider TTS；没有远程授权时不得因为 TTS 阻塞整个本地流水线。
- 字幕从已知脚本和 TTS 时间信息直接构建，不为“拿回原文”再走 ASR/Whisper。
- FFmpeg 是默认总装器；Premiere / After Effects / Nuke 不进入默认依赖。
- 任何已有且通过验证的音频、字幕和视频产物优先复用，支持 Resume 与局部重跑。
- execute 模式真实执行；dry-run 只生成计划。
- 最终成片生成后必须继续经过 Auto QC 和人工最终审核。

验收：

```text
PASS: TTS stage has a real executable path
PASS: subtitle stage builds from script/TTS timing without ASR round-trip
PASS: FFmpeg assembly can produce final.mp4 from available video/audio/subtitle assets
PASS: existing artifacts are reused instead of regenerated
PASS: dry-run stays side-effect safe
PASS: Web can request execute mode without terminal commands
PASS: final review remains human-gated
```

P30-03 执行记录（2026-09-20）：

- 新增 `scripts/pipeline_media_stages.py`：优先复用现有音频/字幕；需要生成时使用本地 TTS 与已知 mouth-cues/script timing，字幕不做 Whisper/ASR 回环。
- `assemble_final()` 统一使用 FFmpeg 组装视频、音频与字幕为 `final.mp4`，支持无音频/无字幕降级路径；已有合格产物优先复用。
- Pipeline execute 模式已真实调用 TTS、Subtitle、Assembly；dry-run 保持只规划不产生媒体。
- Web “创建整集”已从 dry-run 切换为本地 execute，仍固定 `confirm_billable=false`，不会静默触发远程费用。
- 专项测试覆盖现有音频复用、脚本时间轴字幕生成和 FFmpeg mapping；关键提交：`4f908a2`、`8db94db`、`a4321da`、`1e11e02`、`290f445`。
- P30-03 代码范围完成，用户不需要手工录音、对字幕或进入 Premiere/After Effects。

NEXT：P30-04 Auto QC / Auto Retry / Web 一键整集执行。

## P30-04 Auto QC / Auto Retry / Web 一键整集执行
Status: PASS

目标：让本地流水线在生成/复用媒体后自动执行技术 QC，并对可安全修复的技术故障做有界重试；视觉异常不得无限转码重试，最终成片继续由人工审核。

执行记录（2026-09-20）：

- `_auto_qc()` 使用 ffprobe 检查媒体、视频流、音频流和时长，并通过 FFmpeg blackdetect/freezedetect 检查黑帧与冻结帧。
- `_qc_with_retry()` 引入有界自动重试，次数读取 `config/pipeline-orchestrator.json` 的 `max_attempts_per_stage`；仅技术类故障允许容器规范化转码后重试。
- 黑帧/冻结帧归类为 `VISUAL_REGEN_REQUIRED`，不会进入无意义转码循环。
- 每次 QC attempt 与 repair action 写入 run manifest，Web 可直接看到阶段状态；最终 review 只有在 `final.mp4` 存在且 QC PASS 时才进入 READY。
- Web 主按钮现在执行真实本地流水线；远程 Image/Video Provider 仍受显式授权与计费确认门保护。
- 关键提交：`5faced3`、`24493f9`、`eb7054b`、`1f58c9d`、`4000465`。
- P30-04 PASS；自动修复仍严格限制在技术层，不修改剧情、核心事实、审美选择或发布决定。

NEXT：P30-05 VideoProvider 本地执行化。

## P30-05 VideoProvider 本地执行化
Status: PASS

目标：消除 Video stage 的最后一个“只规划不执行”断点；当存在人工审核通过的 keyframe 时，由软件自动生成本地动态镜头，再继续 TTS / 字幕 / FFmpeg / QC。

执行记录（2026-09-20）：

- `scripts/pipeline_orchestrator.py` 已接入现有 `LocalKenBurnsVideo` + `VideoGenerationRequest`：没有现成视频且 keyframe 已 `APPROVED` 时，execute 自动生成 `generated/<shot>-local.mp4`。
- 新生成但尚未审核的 keyframe 会让 Video stage 明确进入 `WAITING_REVIEW`，不会绕过人工视觉质量门。
- 已有视频继续优先复用；dry-run 只显示 VideoProvider 计划，不生成媒体。
- run manifest 记录 provider、duration、image_count、remote_generation、route 和 reused 标志；本地默认路线不会产生远程费用。
- 回归测试覆盖“只有 APPROVED keyframe 才能驱动本地视频”和“PENDING keyframe 必须等待人工审核”。
- 关键提交：`4cbf231`、`3fcbb7a`、`d856c27`。
- P30-05 PASS；至此软件链已具备 Image → Local Video → TTS → Subtitle → FFmpeg → QC → Human Review 的真实执行路径。

NEXT：P30-06 Web 本机运行环境自检与最终 runtime smoke。

## P30-06 Web 本机运行环境自检与最终 runtime smoke
Status: IN_PROGRESS

已完成的仓库侧工作：

- 新增 `pipeline_preflight()`，无副作用检查 FFmpeg、ffprobe、macOS say、ComfyUI health/checkpoint、已审核 Character Bible / Keyframe。
- 新增 Web API `/api/pipeline/preflight` 和“环境自检”按钮；用户不需要终端即可看到 ComfyUI / FFmpeg / ffprobe / TTS 的 READY / BLOCKED / DEGRADED。
- 自检不会生成媒体、不会写 API Secret、不会触发远程计费。
- 新增非破坏性 preflight 回归测试。
- 关键提交：`015b4a3`、`8ba93a5`、`8870d26`、`33ff085`、`a2c64c0`。

P30-06 追加修复（2026-09-20，针对 Web 报错“未检测到 ComfyUI 安装目录”）：

- 新增 `scripts/comfyui_installer.py`：Web 可一键安装/修复 ComfyUI 核心到固定目录 `.dependencies/ComfyUI`，不污染系统 Python。
- 安装流程固定为：检查 git / 磁盘 / Python 3.10–3.14 → clone 官方 `Comfy-Org/ComfyUI` → 独立 `.venv` → Apple Silicon 优先 PyTorch nightly、失败自动回退稳定版 → `requirements.txt` → torch/MPS 自检。
- Python 选择优先 `python3.13`、`python3.12`，再兼容 3.14/系统 python；适配当前用户机器已有 Homebrew Python 的现实情况。
- Web 新增「安装 ComfyUI」按钮和安装进度：STARTING / CLONE / CREATE_VENV / INSTALL_TORCH_NIGHTLY / INSTALL_REQUIREMENTS / COMPLETE / FAIL。
- 安装通过独立后台进程执行，状态与日志分别写到 `logs/comfyui-install.json` / `logs/comfyui-install.log`；Web 可轮询，不需要终端。
- 更新已有受管安装时使用 `git pull --ff-only`，不做 `reset --hard`，避免破坏本地配置。
- 安装器不会下载 checkpoint / LoRA / VAE 等大型模型；核心安装完成后明确显示“尚未安装 checkpoint”，模型下载必须由用户在 Web 显式选择。
- 新增 `tests/test_comfyui_installer.py`，覆盖 Python 选择、安全后台启动、不下载模型和中断恢复；P30 Provider Regression workflow 已纳入 installer compile/test。
- 关键提交：`1bc3a25`、`69894df`、`57dc16c`、`6cad9e3`、`efa07fe`、`e8e4d35`、`3379d72`、`242b21c`、`7ab8b19`、`5dc587a`。
- 官方当前仍支持 Apple Silicon；ComfyUI 文档建议独立环境并在 Apple Silicon 使用 PyTorch nightly，PyTorch 当前 MPS 后端仍为官方支持路径。
- 当前 GitHub connector 仍未返回 workflow run/status，因此不虚报 CI PASS；真实 clone/pip/MPS 安装必须在用户 Mac 上执行。

P30-06 全站默认项目绑定修复（2026-09-20 14:37 CST，真实 Web 截图）：

- 用户已导入新小说《照骨灯》，但 Web 没有把它作为全站默认小说项目；Image Studio 当前项目与刚才生成资产可能因此错位，页面显示 `最近生成 0 张`。
- 新规则：新导入/最新创建的小说项目优先成为全站 active novel project；旧 localStorage 项目记忆不再压过最新导入项目。显式导航/当前会话手动切换仍可覆盖。
- `state.activeNovelProjectId` 成为前端统一活动项目锚点；`setActiveNovelProject()` 同步 Studio / Pipeline / Image Studio 三个 project id 与对应 selector。
- 小说导入成功后立即设置 `activeNovelProjectId=result.directory_id`，随后 `load(result.directory_id)`；刷新后若无显式会话选择，按 `created_at/updated_at` 选最新小说项目，因此《照骨灯》应自动成为默认。
- Image Studio 生成前重新解析 authoritative active project；若当前已加载 inventory 的 `project_id` 与活动项目不一致，先 reload 正确项目后再生成，避免图片写入其他小说目录。
- Image Studio 项目选择框下新增 `当前生成目标：《项目名》 · directory_id`，生成日志也明确记录项目名。
- 当前项目 inventory 为空时会清理 stale preview；若别的项目存在近期 Image Studio 资产，后端 `recent_elsewhere` 会返回并允许点击切换查看，避免误以为生成结果丢失。
- `web/app.js` V8 syntax compile PASS。
- 关键提交：`345d95d`、`f44dcb8`、`28e91ab`。

P31-02 《照骨灯》默认项目与角色补全修复（2026-09-20 15:07 CST，真实 Web 截图）：

- 用户已导入《照骨灯》，但 AI 生图页未稳定默认选中最新小说项目，并显示 `PROJECT CHARACTER · 项目角色尚未抽取` / `角色资料待抽取`；当前项目 recent 为 0。
- Web 全局 active novel 规则改为：显式新导入/当前会话项目优先；fresh load 默认选择 `animeProjects` 中最新导入项目。新导入项目同步绑定制作台、AI 生图、一键整集和首页项目选择，不再让旧 localStorage 项目压过最新小说。
- Image Studio 新增“当前生成目标：《标题》 · directory_id”提示；生成前再次校验 `state.imageStudio.project_id === active project_id`，不一致则先 reload，日志带小说项目名，防止视觉资产写进错误项目。
- 导入流程此前已调用本地角色抽取，但旧启发式主要依赖“某某说道/某某：”对话署名；对叙述型网文可能得到空角色。`infer_character_lexicon()` 已增强为 speaker + narration action subject + quoted vocative 多信号保守打分，并过滤“少年/白衣男子/众人/只见/此时”等泛化叙述词。
- 对新导入小说，增强后的抽取在 ingest 阶段自动生成角色候选；仍不保存正文。
- 对已导入且角色为空的旧项目，Web 角色修复链正式可用：原“角色资料待抽取”死按钮改为“选择原 TXT 并补全角色”；点击后打开文件选择，读取 UTF-8 TXT，POST `/api/image-studio/character-candidates`，后端必须校验 TXT SHA256 与该项目原 import 一致。
- 补全后只保存结构化角色候选/mentions/hash/count，不保存 source text；同时把匹配 import JSON 的 `extraction.characters` 与 provider 同步更新，使项目 source summary 不再继续显示角色候选 0；非匹配 SHA 的 import 不修改。
- 主按钮触发的修复在成功后会自动 reload Image Studio，并继续执行“生成角色定妆板”；单独“补全角色候选”按钮可只修复不生图。
- 角色修复面板增加独立样式和 `.hidden !important`，避免再次出现组件 display 覆盖隐藏状态。
- 新增回归：叙述型人物 `顾临渊/沈照雪` 可从动作上下文识别；泛化角色词不晋升；修复只更新匹配 SHA import 且不存正文；Web 必须暴露角色修复输入/按钮/API。
- 关键提交：`345d95d`、`f44dcb8`、`28e91ab`、`9714e54`、`1c75c7d`、`816acf9`、`9004645`、`5762fdd`、`5940d63`。

NEXT：刷新 Web，确认默认项目为《照骨灯》；旧项目首次点击“选择原 TXT 并补全角色”只需重新选一次原始 TXT，SHA 校验通过后自动解锁并继续角色定妆生成。新导入小说不再需要此补全步骤。

P30-06 Image Studio 预览修复（2026-09-20 14:27 CST，真实 Web 截图）：

- 首张角色定妆图 ComfyUI 已执行完成，但 Web 预览出现黑框/alt 文本，且“空状态”与结果区同时显示。
- 已确认一个确定前端 bug：全局 `.hidden{display:none}` 定义在前，而后续 `.image-studio-empty{display:flex}` / `.image-studio-result{display:grid}` 覆盖了 display，导致隐藏状态失效。新增 `.image-studio-empty.hidden,.image-studio-result.hidden{display:none !important}`。
- 媒体 URL 链路加固：后端新增 `_media_url()`，对 project id 和每个相对路径 segment 做 URL quote；`_safe_project()` 支持 URL-decoded project id；Image Studio inventory 和生成返回统一使用编码后的 `/media/...`。
- 前端不再直接信任历史 `media_url`；由 `project_id + output` 逐段 `encodeURIComponent` 重建同源 URL，并带生成版本 query 避免旧缓存。
- Web 预览新增 `onerror` 可见错误提示与日志；若媒体 GET 失败会直接显示具体 URL，不再只剩黑框。
- ComfyUI provider 新增 PNG/JPEG/WebP magic header 校验，非图片 bytes（例如 HTML 错误页）不会再保存成 `.png`。
- Image Studio inventory 新增 `media_valid` / `media_bytes`；旧资产刷新后即可区分“URL 加载失败”和“文件本体无效”。新生成结果只有文件头合法才允许返回成功。
- 新增 provider/media URL/image file validation 回归；`web/app.js` 已做 V8 syntax compile，结果 PASS。
- 关键提交：`5fb6d51`、`6d79152`、`1c09455`、`b3a3ebc`、`8cd265c`、`b38f4c3`、`1758a6e`、`967dcd7`、`aeba753`。

P30-06 首张本地角色定妆图真实执行（2026-09-20 14:23 CST）：

- 用户在 Web 点击「生成角色定妆板」后，ComfyUI 实际已成功执行完整 24-step workflow；日志 `24/24`，KSampler 采样约 `197s`，整条 prompt `258.81s`。
- 当前问题不是生成失败，而是 Web 采用同步 HTTP 等待，约 4 分钟期间只有按钮文字变化，没有采样步进度，用户感知为“没反应”。
- Image Studio 已接入 ComfyUI 官方 WebSocket 进度通道：Web 生成前创建唯一 client id，后端排队 `/prompt` 时复用同一 client id；浏览器监听 `/ws?clientId=...` 的 `progress` / `progress_state` / `execution_start` / `execution_success` / `execution_error`。
- Web 新增角色/关键帧生成进度卡，实时显示 `value/max`（例如 `1/24 → 24/24`）、百分比与按钮进度；若 WebSocket 不可用，仍显示已运行秒数，不再出现无反馈长等待。
- ComfyUI provider 新增受限 `client_id` 参数并校验允许字符，结果 metadata 回传 client id；新增回归验证 `/prompt` 确实使用 Web 传入的 client id，并拒绝非法 client id。
- 首张图真实性能基线：Animagine XL 4.0 + Apple MPS + 24 steps，prompt 总耗时约 259 秒。后续性能优化以此为基线，优先考虑预览档降低 steps/分辨率，最终定妆再跑高质量档。
- 关键提交：`d2e34af`、`5f30beb`、`c3b7407`、`2ea4636`、`18ba479`、`11c5ce7`。

P30-06 Web Python 路径污染修复（2026-09-20 14:08 CST，真实 Mac 日志）：

- venv 路径修复后真实启动已正确显示 `python=.dependencies/ComfyUI/.venv/bin/python` 且 `dependency_sync=SKIP already-current`，证明解释器选择和 requirements 指纹均正确。
- 随后 ComfyUI 在 `from PIL import Image` 阶段错误加载 `/Users/zouhuashan/aiagent/video/.web-python/PIL/Image.py`，并因该 Web 专用 Pillow 与 ComfyUI venv native extension ABI/路径不匹配报 `ImportError: cannot import name '_imaging' from 'PIL'`。
- 根因定位为 VideoCreator Web 父进程的 `PYTHONPATH` 被 ComfyUI 子进程继承；不是 ComfyUI venv Pillow 缺失，也不需要重装系统 Python。
- 受管项目 ComfyUI 新增 `_isolated_python_env()`：启动、自检和 pip 同步前清除 `PYTHONPATH`、`PYTHONHOME`、`PYTHONUSERBASE`、`PYTHONSTARTUP`，设置 `PYTHONNOUSERSITE=1`，并显式设置 `VIRTUAL_ENV=.dependencies/ComfyUI/.venv` 与 venv/bin PATH 前缀；代理/CA 等非 Python 网络环境继续保留。
- 只有项目 `.dependencies/ComfyUI` 使用该强隔离环境；外部/Desktop ComfyUI 仍保持原环境，不越权修改。
- dependency smoke 从 `import PIL` 升级为真实加载 `PIL.Image` 与 `PIL._imaging`，同时检查 `sys.path` 不得包含 `.web-python`；native extension 污染以后会在启动 main.py 前直接阻断。
- 核心 installer 的 `_network_env()` 同步清理 Web Python 环境，安装/修复/torch/requirements 自检也不再继承 `.web-python`。
- 启动日志新增 `python_env_isolated` 和 `parent_pythonpath_present`，不记录完整 PYTHONPATH 内容。
- 新增回归：清除 Web Python 环境且保留代理；dependency smoke 必须使用隔离 env 并加载 `PIL._imaging`。
- 关键提交：`88e6db2`、`c576ce1`、`fb03d21`。

P30-06 ComfyUI venv 路径修复（2026-09-20 14:05 CST，真实 Mac 日志）：

- 受管 ComfyUI 启动前依赖自检错误落到 uv managed base Python，真实日志同时出现 `No module named packaging` 与 PEP 668 `externally-managed-environment`。
- 根因不是 venv 依赖再次损坏，而是 `comfyui_service_manager._python_for()` 对 `.venv/bin/python` 调用了 `Path.resolve()`；uv 创建的 venv Python 是指向 managed base Python 的符号链接，resolve 后丢失 `.venv/bin/python` 调用路径，Python 因此不再识别 `pyvenv.cfg`，`sys.prefix == sys.base_prefix`，pip 被 PEP 668 正确阻止。
- 修复：v​​env Python 选择禁止 resolve 符号链接；只做 expanduser/absolute，必须保留 `.dependencies/ComfyUI/.venv/bin/python` 原始执行路径。
- 新增 venv identity 安全门：项目内 ComfyUI 只有在 `sys.prefix != sys.base_prefix` 且 `sys.prefix` 精确指向 `.dependencies/ComfyUI/.venv` 时才允许依赖同步；否则直接拒绝，明确禁止 `--break-system-packages`。
- 启动日志新增 `python=<exact venv path>` 与 `home=<ComfyUI path>`，以后可直接确认解释器上下文。
- 新增回归：venv Python symlink 不得解析为 base interpreter；base interpreter 必须被 venv identity 拒绝；正确项目 venv 必须通过。
- 由于 14:00 前已完整安装 requirements 且记录相同 `requirements_sha256`，修复后的预期启动路径为 `dependency_sync=SKIP already-current`，然后直接启动 `main.py`，不应再次执行 pip。
- 关键提交：`20d7329`、`1c0a98b`、`ebab210`。

P30-06 checkpoint 真实 Mac 验收 PASS（2026-09-20 14:00 CST）：

- ComfyUI 官方 requirements 已完整安装；真实日志显示 `filelock` 相关依赖链、SQLAlchemy/Alembic、aiohttp、comfy-angle、frontend/workflow templates 等均成功落入项目 venv。
- 核心自检再次真实 PASS：PyTorch `2.15.0.dev20260919`，`mps_built=true`、`mps_available=true`，并新增 `requirements_sha256=38851db...ac03` 与 `dependencies_verified_at`。
- Animagine XL 4.0 模型真实下载 PASS：自动选择代理 `http://127.0.0.1:7897`，固定官方 Hugging Face URL，最终 checkpoint SHA256 为 `1d5b43ff75b6ab598502d4c779d2fbfa3dceca51c60c3b609640a60772333916`，与白名单预期一致。
- checkpoint 安装状态为 `PASS / COMPLETE`；至此 Python、TLS、PyTorch/MPS、官方 requirements、模型下载、代理路由、文件完整性链全部真实验收通过。
- 修复状态一致性：checkpoint PASS 时同步写回 `logs/comfyui-install.json` 的 `models_installed=true`、checkpoint 文件名/model id/SHA256/verified_at；核心 installer status 也直接从已验证模型 state 派生 `models_installed=true`，避免旧的 `false` 误导 Web/环境自检。
- 新增对应回归：模型 PASS 同步核心 install state；核心 status 从 verified model state 派生模型就绪。
- 关键提交：`aafd4ce`、`ebe56d9`、`ad92641`、`f5c5d3f`。

NEXT：启动受管 ComfyUI → 确认 checkpoint 被发现 → 从 Image Studio 生成第一张角色定妆板 → 人工审核视觉锁。

P30-06 ComfyUI 启动依赖漂移修复（2026-09-20 13:01 CST，真实 Mac 日志）：

- checkpoint 下载后启动受管 ComfyUI 时，`app/database/db.py` 导入 `filelock` 失败，实际报错 `ModuleNotFoundError: No module named 'filelock'`。
- 当前 ComfyUI 官方 `requirements.txt` 已把 `filelock` 列为直接依赖；官方 README 也明确要求启动前执行 `pip install -r requirements.txt`。因此不采用单独 `pip install filelock` 的一次性补丁，而按“源码 requirements 与 venv 依赖漂移”修复。
- 核心 installer 的 PASS 门升级：安装 requirements 后不仅验证 torch/MPS，还逐条读取当前 `requirements.txt`，通过 `importlib.metadata` + `packaging.Requirement` 检查每个 distribution 是否存在、版本约束是否满足，并额外执行关键模块 import smoke。缺任意官方依赖不得再标记 COMPLETE。
- 核心安装成功状态新增 `requirements_sha256` 与 `dependencies_verified_at`，记录当时已验证的官方 requirements 指纹。
- 受管服务启动前新增依赖同步门：仅对项目 `.dependencies/ComfyUI` 比较当前 requirements SHA256 与 installer state；若指纹变化、缺包或关键 import 失败，自动运行当前 venv 的 `pip install -r requirements.txt`，完成后重新做全 requirements 元数据校验 + import smoke，通过后才启动 `main.py`。
- 依赖同步继承核心安装成功时的 CA 路径（`SSL_CERT_FILE` / `PIP_CERT` / `REQUESTS_CA_BUNDLE`），不关闭 TLS。
- 外部/Desktop ComfyUI 保持只读边界：VideoCreator 不会自动修改其 Python 依赖。
- 新增回归：缺 `filelock` 时启动前自动同步 requirements；指纹和依赖均当前时不执行 pip；外部 ComfyUI 绝不自动改依赖。
- 关键提交：`b483f9f`、`6215f46`、`89a949e`、`0b75457`、`3240c09`。

P30-06 checkpoint 下载网络修复（2026-09-20 11:52 CST，真实 Mac 日志）：

- 首次 Web 模型安装已进入固定白名单 Animagine XL 4.0 下载，但 `/usr/bin/curl` 直连 `huggingface.co:443` 连续超时；模型文件、SHA256、checkpoint 路径本身尚未进入校验阶段。
- 根因定位为后台下载进程未获得可用外网代理路线，而不是 ComfyUI / PyTorch / 模型文件损坏。
- `scripts/comfyui_model_manager.py` 新增网络路线自动发现：优先读取 `HTTPS_PROXY` / `ALL_PROXY` / `HTTP_PROXY`，再读取 Clash Verge/Mihomo 本地 Unix socket `/tmp/verge/*.sock` 的 `/configs`，最后读取 macOS `scutil --proxy`；只生成 loopback/system-derived proxy 候选，不接受 Web 任意代理 URL。
- Clash Verge/Mihomo 自动发现读取 `mixed-port` / `port` / `socks-port`，转换为 `http://127.0.0.1:<port>` 或 `socks5h://127.0.0.1:<port>`；不硬编码代理端口。
- 每个候选路线先用 1-byte Range 做小流量连通性 probe；代理可用则优先走代理，直连只作为最后 fallback，避免再次单次卡 75 秒。
- 实际下载继续使用固定 Hugging Face URL、断点续传 `.part`、8 次 retry 和 15 秒 connect timeout；已有 partial 文件不会重下。
- 日志和 Web 状态新增 `download_route` / `network_route`；若代理 URL 含认证信息，仅显示 scheme/host/port，不记录用户名或密码。
- 新增 macOS system proxy、Clash Verge Unix socket、代理去重、凭据脱敏、代理优先路由回归测试。
- 关键提交：`b1f2775`、`8664ffe`、`53473e1`、`5907202`、`26a0327`、`235f398`。

P30-06 核心运行环境真实 Mac 验收 PASS（2026-09-20 10:54 CST）：

- 用户 Web 一键安装返回 `status=PASS / step=COMPLETE`，ComfyUI 核心位于 `.dependencies/ComfyUI`。
- 最终 Python 为项目私有 uv-managed runtime：`python_source=uv-managed-project-private`，ComfyUI venv 为 `.dependencies/ComfyUI/.venv/bin/python`。
- CA 来源为 `/private/etc/ssl/cert.pem`；PyTorch 使用 nightly，实际版本 `2.15.0.dev20260919`。
- MPS 自检真实通过：`mps_built=true`、`mps_available=true`。此前 MacPorts x86_64、Homebrew 3.14 ensurepip/platform 异常链已被项目私有 arm64 Python 路线彻底隔离。
- 当前唯一缺口明确变为 `models_installed=false`：核心 runtime 已完成，不再重复排查 Python / SSL / PyTorch。

P30-06 checkpoint Web 安装器（2026-09-20）：

- 新增 `scripts/comfyui_model_manager.py`，首发白名单模型固定为 `CagliostroLab/animagine-xl-4.0` 单文件 checkpoint；Web 不接受任意下载 URL。
- 官方模型文件约 6.94 GB，license `openrail++`，固定 expected size `6938434056` 与 SHA256 `1d5b43ff75b6ab598502d4c779d2fbfa3dceca51c60c3b609640a60772333916`。
- 下载使用固定 Hugging Face resolve URL + curl redirect/retry/断点续传；临时文件保存为 `.part`，只有文件大小和 SHA256 双校验通过后才原子移动到 `.dependencies/ComfyUI/models/checkpoints/`。
- SHA256 不匹配时异常文件自动隔离为 `.invalid-*`，绝不进入 checkpoints。
- Web 新增 `/api/comfyui/models/status`、`/api/comfyui/models/install/start` 与「安装国漫基础模型」卡片；实时显示下载百分比、已下载 GB、状态与日志。
- 安装成功后 Web 会自动启动或重启由 VideoCreator 管理的 ComfyUI，并重新读取 checkpoint；外部 ComfyUI 不会被误杀。
- 状态查询不会反复 SHA256 扫描 6.94 GB 文件；完整哈希只在安装/首次确认时执行，后续使用已验证状态 + 文件大小快速判断。
- P30 regression 已加入 `tests/test_comfyui_model_manager.py` 与新模块 compile；Web `app.js` 已用 V8 syntax compile 实测 PASS。
- 关键提交：`b73f029`、`01ec155`、`65ba244`、`938ac99`、`1fb4adf`、`9d19548`、`7f55a56`、`489516d`。

P30-06 安装器第八轮修复（2026-09-20，真实 Mac 日志）：

- 第九次真实安装未进入 managed Python 下载，原因是 uv 收到互斥配置：`UV_MANAGED_PYTHON=1` 与 `UV_PYTHON_PREFERENCE=only-managed` 同时存在，uv 直接返回 `cannot be used with --python-preference`。
- 官方 uv 文档说明 `UV_MANAGED_PYTHON` 对应 `--managed-python`，`UV_PYTHON_PREFERENCE` 是独立的 Python preference 设置；managed Python 已经由精确 request `cpython-3.13-macos-aarch64-none` 与精确解释器路径绑定，不需要再叠加两套策略。
- `_managed_uv_env()` 现在主动移除 `UV_MANAGED_PYTHON`、`UV_PYTHON_PREFERENCE`、`UV_NO_MANAGED_PYTHON`，仅保留项目私有安装目录、bin 目录、CA 环境与 `UV_NO_MODIFY_PATH=1`。
- system fallback 进一步收紧：Apple Silicon 候选 Python 除了必须为 arm64/aarch64，还必须通过 `_python_runtime_healthy()`；`platform.mac_ver()` 为空的 Homebrew Python 3.14 会在候选阶段直接剔除，不再重复进入已知坏链路。
- 回归新增：managed uv env 必须清理互斥策略变量；Apple Silicon 必须拒绝 runtime health check 失败的 arm64 系统 Python。
- 关键提交：`c6d4273`、`49c3c27`。

P30-06 安装器第七轮修复（2026-09-20，真实 Mac 日志）：

- 第八次真实安装已进入 Homebrew arm64 Python 3.14，但该解释器生成的半成品 venv 被 uv 判定为 broken：`platform.mac_ver() returned an empty value`；外层 pip `--python <venv>` 同时触发 pip 内部 `No module named pip._internal.operations.install.wheel`。继续修系统 Python 3.14 不再有价值。
- 架构策略升级为“项目私有 runtime first”：Apple Silicon 上优先由现有 `uv` 下载并管理 `cpython-3.13-macos-aarch64-none`，固定安装到 `.dependencies/python`，可执行入口固定在项目私有目录，不依赖 MacPorts/Homebrew Python。
- uv 官方支持精确 Python request `<implementation>-<version>-<os>-<arch>-<libc>`，支持 `--install-dir` / `UV_PYTHON_INSTALL_DIR` 自定义安装目录；3.13 属于 uv Tier 1 支持版本。
- 项目私有 Python 安装命令使用 `uv python install cpython-3.13-macos-aarch64-none --install-dir .dependencies/python`，并设置 `UV_PYTHON_PREFERENCE=only-managed`；不会修改用户 shell PATH。
- ComfyUI venv 不再通过该 Python 自己的 `ensurepip` 创建；使用 `uv venv --python <managed-python> --seed --clear` 直接生成带 pip 的 `.dependencies/ComfyUI/.venv`。
- managed Python 和 managed venv 均执行 runtime health check：Python 3.13、`platform.machine()` 必须为 arm64/aarch64、macOS 下 `platform.mac_ver()` 必须非空。
- uv 下载 managed Python 时继续继承此前已验证的 macOS CA bundle；TLS 验证不关闭。
- 仅当项目私有 uv-managed Python 3.13 本身安装/兼容性失败时，才 fallback 到系统 arm64 Python；x86_64 MacPorts Python 仍在候选阶段剔除。
- PyTorch Apple Silicon 判断改为真实宿主机检测（含 Rosetta 下 `sysctl hw.optional.arm64`），不再依赖 Web/installer 当前进程自身的 `platform.machine()`。
- 回归新增：managed Python 固定项目目录与 arm64 request、uv venv 必须 `--seed --clear` 且精确绑定 managed Python、Apple Silicon 安装必须优先 managed runtime 而不调用 system runtime。
- 关键提交：`d868aee`、`8f28ef2`、`0ed072c`、`2bbab36`。

P30-06 安装器第六轮修复（2026-09-20，真实 Mac 日志）：

- 第七次真实安装已正确选中 Homebrew arm64 Python 3.14，并使用 `/opt/homebrew/etc/ca-certificates/cert.pem`；旧 x86_64 MacPorts venv 被自动删除。
- 新阻塞发生在 `python3.14 -m venv`：标准 venv 在内部调用 `ensurepip --upgrade --default-pip` 时失败，导致 `CREATE_VENV` 退出。
- Python 3.14 官方 `venv` 明确支持 `--without-pip`；安装器新增自动 fallback：标准 venv 创建失败 → 清理半成品 → `venv --without-pip` → 使用外层已验证可联网的 bootstrap Python 执行 `pip --python <venv_python> install --upgrade pip setuptools wheel`，绕开坏掉的 ensurepip。
- 若外层 pip 无法跨解释器注入，且本机已有 `uv`，自动 fallback 到 `uv pip install --python <venv_python>`；两者都失败才真正报错。
- 已存在但缺 pip 的半成品 venv 也会被识别，不需要用户手动删除目录；安装器直接给该 venv 注入 pip 后继续。
- TLS 校验仍保持开启，CA 仍来自此前验证通过的 Homebrew/macOS trust；没有使用 trusted-host 或关闭证书验证。
- 回归新增：ensurepip 创建失败 → `--without-pip` fallback；已有 venv 缺 pip → 外部注入；外层 pip 命令必须通过 `--python <venv>` 定向目标环境。
- 关键提交：`df5b711`、`24dcf52`、`dcdb5a0`。

P30-06 安装器第五轮修复（2026-09-20，真实 Mac 日志）：

- 第六次真实日志显示自动 fallback 已从 x86_64 MacPorts Python 3.13 切到 x86_64 MacPorts Python 3.12；该 runtime 能安装 x86 PyTorch 2.2.2，但随后在最新 ComfyUI requirements 的 `comfy-angle` 处失败。
- `comfy-angle` 官方说明只提供 macOS arm64 wheel（另有 Windows/Linux 对应架构），没有 macOS x86_64 wheel；因此该失败进一步证明 x86 Python 不应在 Apple Silicon 上进入安装链。
- 最新候选过滤已经在 Apple Silicon 上剔除 x86_64 Python；本轮再新增完整 requirements preflight：每个候选 venv 在下载大体积 PyTorch 前，先执行 `pip install -r requirements.txt --dry-run`。
- 若 `comfy-angle` 或未来其他平台原生依赖无法解析，抛出 `ComfyUIRequirementsUnavailable`，自动排除当前 Python runtime 并选择下一套候选，不下载 PyTorch。
- 只有“完整 requirements dry-run PASS + torch wheel probe PASS”的 Python runtime 才进入真实依赖安装，避免再次下载 150MB+ 后才失败。
- 新增真实回归：x86 Python 3.12 在 `comfy-angle` preflight 失败 → 不调用 torch install → 自动切换 Homebrew arm64 runtime → PASS。
- 关键提交：`94ae9d9`、`45a77a5`、`18905e1`。

P30-06 安装器第四轮修复（2026-09-20，真实 Mac 日志）：

- 第五次真实安装日志首次打印出决定性平台信息：MacPorts Python 3.13 实际为 `machine=x86_64`、`platform=macosx-11.0-x86_64`，而用户机器是 Apple Silicon；因此该解释器不可能匹配 PyTorch 当前发布的 `macosx_*_arm64` wheel。
- 官方 PyTorch nightly index 当前可见 cp313/cp314 的 `macosx_14_0_arm64` wheel，进一步证明问题不是“Python 3.13 没 wheel”，而是候选解释器架构错误。
- 安装器新增 Apple Silicon host detection（原生 arm64 或通过 `sysctl hw.optional.arm64` 识别 Rosetta 环境），并对每个候选 Python 实际执行 `platform.machine()`。
- Apple Silicon 上仅接受 `arm64/aarch64` Python；x86_64 MacPorts/Rosetta Python 在进入 TLS、venv、pip、torch 之前直接从候选池剔除。
- 非 Apple Silicon 主机保持原逻辑，不强制 arm64。
- 回归新增 Apple Silicon 拒绝 x86 Python 与非 Apple 主机不误过滤测试。
- 关键提交：`9f989ee`、`27f1b40`。

P30-06 安装器第三轮修复（2026-09-20，真实 Mac 日志）：

- 第四次真实安装已经证明 SSL 修复成功：MacPorts Python 3.13 使用 `.dependencies/certs/macos-trust.pem` 后可正常下载 pip/setuptools/wheel。
- 新阻塞发生在 PyTorch：nightly CPU index 与 stable PyPI 对当前 venv 都返回 `No matching distribution found for torch`。官方 nightly index当前实际存在 macOS arm64 的 cp313/cp314 wheel，因此不能简单归因于“Python 3.13 没有 PyTorch”；更可能是该 MacPorts runtime 的兼容 tag / architecture / ABI 与 wheel 不匹配。
- 新增 `python_platform` 诊断，记录 Python 版本、`platform.machine()`、`sysconfig.get_platform()`、SOABI、abiflags。
- PyTorch 安装改为先 `pip install --dry-run` 探测 nightly，再探测 stable；只有真正兼容才下载/安装大型 wheel。
- 若当前 Python runtime 没有兼容 torch wheel，抛出专用 `ComfyUITorchUnavailable`，安装器不再整体 FAIL，而是把该解释器加入 exclude 并自动选择下一套 TLS 可用 Python。
- 下一套 Python 会触发现有 venv runtime drift 检查，从而自动删除旧 venv、重建后继续 torch probe。典型真实路径：MacPorts 3.13 → 无匹配 torch wheel → Homebrew 3.14 → 重建 venv → probe/install。
- 成功状态新增 `torch_channel`（nightly/stable）记录。
- 回归新增“第一套 Python 无 torch wheel → 第二套 Python 自动成功”的真实场景。
- Apple 当前官方 MPS 安装页使用 `pip install --pre ... --extra-index-url https://download.pytorch.org/whl/nightly/cpu`；安装器已同步改为 `--extra-index-url`，并增加 `--only-binary=:all:`，避免错误源码编译。
- 关键提交：`a1c46ac`、`4aa0b51`、`c7091d9`。
- 官方 ComfyUI README 仍说明 Apple Silicon 使用 PyTorch nightly；当前 PyTorch nightly index可见 cp313/cp314 macOS arm64 wheel，因此 fallback 由实际 wheel probe 决定，不再硬编码版本猜测。

P30-06 安装器第二轮修复（2026-09-20，真实 Mac 日志）：

- 第三次真实安装日志显示 `bootstrap_python` 已切到 Homebrew Python 3.14 且 `ca_source=python-default`，但 pip 实际仍从旧 `.venv/lib/python3.13` 运行；根因是安装器复用了上一轮由 MacPorts Python 3.13 创建的旧 venv。
- 新增 venv runtime identity 检查：比较 major/minor 与 `sys.base_prefix`；只要 Python 版本或运行时来源发生变化（例如 MacPorts → Homebrew），旧 venv 自动删除并重建。
- 即使 runtime 未变化，现有 venv 自身若无法通过 PyPI HTTPS probe，也会自动重建；新 venv 创建后必须先通过 HTTPS probe 才进入 pip upgrade。
- 当 bootstrap Python 默认 HTTPS 已通过时，安装器读取 `ssl.get_default_verify_paths().cafile`，把已验证 CA 显式注入 `SSL_CERT_FILE` / `PIP_CERT` / `REQUESTS_CA_BUNDLE`，确保 venv pip 与 bootstrap Python 使用同一信任链。
- Python 选择策略同步调整为“先修复首选解释器的 TLS，再考虑下一个解释器”；保持官方当前推荐的 Python 3.13 优先，3.12 fallback，3.14 仅在前者确实不可用时使用。
- 官方当前 README：Python 3.13 very well supported；3.14 works but custom nodes may have issues；Apple Silicon 继续建议 PyTorch nightly。
- 关键提交：`f57cb1a`、`ffb75cb`、`812cc3d`、`f3a6155`、`3abdcc6`。

P30-06 安装器证书修复（2026-09-20，真实 Mac 日志）：

- 本机第一次/第二次 Web 安装已成功完成官方 ComfyUI clone 和 Python 3.13 venv 创建，但在 `UPGRADE_PIP` 阶段出现 `SSLCertVerificationError: unable to get local issuer certificate`；根因定位为所选 MacPorts Python 3.13 的 CA trust 与当前 macOS/网络信任链不一致，不是 ComfyUI/PyTorch 故障。
- 安装器新增 HTTPS preflight：候选 Python 不再只按版本选择，而是必须能通过 PyPI TLS 校验；当前 Python 失败后会自动尝试其他 3.10–3.14 Python。
- macOS 下自动使用 `security find-certificate -a -p` 从 System Root / System / login Keychain 导出机器实际信任的证书到 `.dependencies/certs/macos-trust.pem`，仅导出公开证书，不读取私钥。
- 同时尝试 `/etc/ssl/cert.pem`、MacPorts/Homebrew 常见 CA bundle；成功后统一注入 `SSL_CERT_FILE`、`PIP_CERT`、`REQUESTS_CA_BUNDLE` 给 pip/urllib/requests。
- 明确禁止用 `--trusted-host`、关闭 TLS 校验或其他不安全绕过方式。
- 已存在的 `.dependencies/ComfyUI` 与 `.venv` 会继续复用；再次点击“修复 / 更新 ComfyUI”只从证书/依赖失败点继续，不重新 clone。
- 安装日志新增 `ca_source=...`，便于下一次真实 Mac smoke 精确确认使用了哪条信任链。
- 新增回归覆盖“默认 TLS 失败 → macOS Keychain CA bundle → PyPI probe 成功”。
- 关键提交：`c13a5a2`、`0b4e0d6`。

NEXT：P30-06/P31-02 Mac Web smoke：点击「安装国漫基础模型」→ 自动断点下载 / SHA256 校验 → 自动启动或刷新 ComfyUI → 环境自检 / 本地生图 smoke。

P30-06 追加修复（2026-09-20，针对 Web 报错 `Connection refused`）：

- 新增 `scripts/comfyui_service_manager.py`，把 ComfyUI 从“仅 Provider 检测”升级为受控本地服务：status / start / stop。
- Web AI 生图页新增「启动 ComfyUI」「停止」和服务状态；“保存并检测”现在先保存地址，即使服务未启动也不会因为 connection refused 而拒绝保存。
- 服务管理器只允许管理 loopback `http://127.0.0.1/localhost`，固定执行检测到的 `main.py`，禁止用户传任意命令。
- Stop 只允许终止由 VideoCreator 启动并持有 PID state 的 ComfyUI；检测到外部/Desktop 自己启动的 ComfyUI 时拒绝误杀。
- 自动发现 `COMFYUI_HOME`、仓库 `.dependencies/ComfyUI`、`~/ComfyUI`、`~/Documents/ComfyUI`、`~/ComfyUI-Installs/*/ComfyUI` 以及 macOS Desktop App resources；Desktop 模式会读取 Application Support 的 `config.json/basePath` 与其 `.venv`。
- 日志写入 `logs/comfyui-service.log`，PID/state 写入被 gitignore 的 `logs/comfyui-service.json`；不写 API Key。
- 新增 `tests/test_comfyui_service_manager.py`，覆盖 loopback 限制、未安装状态、固定启动命令和禁止停止外部进程；P30 regression workflow 已纳入该模块。
- 关键提交：`bd02f77`、`1f7837e`、`907d75c`、`aa8e18e`、`7e23960`、`ccc2177`、`9db4ab6`、`15997f3`、`24be554`。
- 当前 GitHub connector 仍未返回 workflow run/status，因此不虚报 CI PASS。

当前唯一阻塞：

- GitHub 连接器无法访问用户 Mac 的 `127.0.0.1:8188`、本地 GPU/ComfyUI checkpoint、FFmpeg 二进制和 Web 端口 `18765`，因此不能在本对话中伪造“真实 Mac runtime smoke PASS”。
- GitHub HEAD 当前没有可读取的 commit status；仓库已配置 P30 回归 workflow，但本连接器没有返回可引用的运行状态，因此保持诚实的 BLOCKED，而不是虚报 CI / 本机验收。
- 代码层工作已完成；解除该阻塞只需在用户 Mac 更新仓库后，从 Web 点击“环境自检”与“创建整集（本地执行）”，得到真实运行结果。

NEXT：P30-06 启动 ComfyUI 与首张角色定妆板本地生图 smoke；核心 runtime + checkpoint 已真实 PASS。


---

# 45. P31 — Web 小说导入工作台（2026-09-20）

## P31-01 新建小说 + TXT 上传
Status: PASS

目标：用户不再通过终端手工创建小说项目、编辑 Source Catalog 或执行 ingest 脚本；从 Web 直接完成“新建独立小说项目 → 上传 TXT → 权利模式 → 自动切章 → 初始化制作台”。

实现：

- Web 左侧新增「导入小说」；输入小说名、作者、首季集数、使用模式并选择 UTF-8 TXT 后即可创建。
- 浏览器先做 UTF-8 fatal decode 与 20 MB 文件大小检查；后端 `/api/novel-anime/import` 使用独立大请求上限，不放宽其他 API 的 64 KB 安全边界。
- 新增 `scripts/novel_web_import.py`：自动生成安全 Project ID / IP Code，创建 P18 核心 manifest、Repository、Runtime、Source Catalog，调用现有 `novel_source_ingest` 自动切章，并初始化 P19～P27 制作台骨架。
- 本地 TXT 使用明确的 `local://upload/... `来源 URI，不伪造公网 source URL；`novel_source_catalog.py` 仅为该本地来源类型扩展 URI 校验。
- 上传正文只写入项目内临时文件供 ingest 使用，完成或失败后立即删除；正式导入产物仍保持 `full_text_stored=false`，只保存章节索引、哈希、行号和抽取候选。
- 权利模式当前提供：
  - `OWNED_OR_LICENSED`：用户明确确认自己是作者或已获得改编授权，可进入本地改编链；状态使用现有 `LICENSED` 契约，但 `publication_allowed=false`，不会自动获得发布权限。
  - `TECHNICAL_TEST`：仅本地技术测试，不解锁正式 script adaptation。
- 公版/第三方授权发布仍要求既有来源证据和人工审核；上传成功不会绕过发布门。
- 导入成功后 Web 显示章节数、首季集数和权限状态，并提供「进入制作台」按钮。
- 新增 `tests/test_novel_web_import.py`，覆盖正式作者/授权导入、技术测试导入、制作台初始化、临时 TXT 清理和“正文不落库”；Source Catalog 与 Web 静态入口回归同步补齐。
- 新增 `.github/workflows/p31-novel-import-regression.yml`，包含 Python compile、Node JS syntax check 和 P31 单测。当前 GitHub 连接器没有返回 workflow run/status，因此不虚报 CI PASS；代码范围按仓库契约已完成。
- 关键提交：`6c29868`、`55a7a30`、`b0e4f55`、`e88abe3`、`5cd394e`、`84b6f19`、`8c1f18e`、`5971daa`、`cee1c1c`、`dd79084`、`a76333e`、`c0dec96`。

用户操作边界现在是：

```text
打开 Web
→ 导入小说
→ 填小说名 / 作者 / 首季集数
→ 选择权利模式
→ 选择 TXT
→ 创建项目并导入小说
→ 进入制作台
```

不需要命令行。

## P31-02 《照骨灯》角色链、重复项目删除与定妆板重生成修复
Status: CODE PASS / LOCAL WEB REVERIFY

执行记录（2026-09-20）：

- 小说 Web 导入链已改为在项目创建阶段完成本地角色候选抽取，并直接写入项目 Story Bible；后续 Character Designs 从项目 Bible 派生。小说项目不再允许回退到全局 demo 角色。
- 相同“小说标题 + TXT SHA256”的重复导入改为幂等复用已有项目，不再继续制造同底本重复项目；若历史重复项目中只有其中一份保留了角色候选/抽取元数据，当前项目可从同底本 sibling 项目恢复结构化角色信息，不要求重新上传 TXT，也不恢复/落盘原始正文。
- Web「国漫项目」卡片已加入“删除项目”操作；后端 /api/novel-anime/delete 只允许删除 novel-anime 项目且必须显式 confirm_delete。删除当前项目后自动选择剩余项目中最新一份作为默认项目。
- 为避免删除入口藏得太深，AI 生图页的“国漫项目”下拉框右侧新增醒目的“删除当前项目”按钮；确认后直接删除当前项目、清理当前选择，并自动切换到剩余默认项目。若已无项目则回到国漫项目页。
- 2026-09-20 删除故障根因修复：`scripts/web_server.py` 的删除实现调用 `shutil.rmtree()` 但遗漏 `import shutil`，导致点击删除后运行时 NameError、目录未删除。现已补 import，并在删除后强校验目录必须不存在；响应返回 `deleted_verified` 与剩余项目 ID。两个同名《照骨灯》在选择器中会附带目录 ID 后 8 位，避免删除一个后自动切到另一个时看起来“没变化”。
前端 API 解析也已增强：若后端进程仍是旧代码并返回非 JSON 错误，会明确提示需要重启一次 Web 服务，而不是静默表现为“删除没效果”。
- 最新导入小说继续作为全站默认小说项目，并同步到制作台、Pipeline 与 Image Studio；《照骨灯》不会因浏览器旧 localStorage 选择而被旧项目静默覆盖。
- Image Studio 对历史空 Story Bible 项目会先从已保存 character candidates / import extraction 元数据自动 bootstrap；恢复完成后主按钮可直接继续“生成角色定妆板”。无可恢复项目角色时继续阻止使用全局演示角色。
- “重新生成角色定妆板直接失败”补充修复：真实 Apple MPS + Animagine XL 4.0 的首张定妆板基线约 259 秒，而 ComfyUI Provider 旧默认总超时仅 180 秒，现提升到 600 秒，避免健康的 24-step 本地任务被中途误报 timeout。
- ComfyUI 生成前 readiness probe 从 0.8 秒放宽到 3.0 秒，降低模型已加载/服务忙时因为 /system_stats 或 /object_info 短暂变慢而出现“点一下直接失败”的假阴性。
- ComfyUI history 若真实 execution_error，Web 现在可得到具体 node_type + exception_message；若确实超时，错误会带 elapsed seconds 与 prompt_id，并明确说明本地任务可能仍在运行，不再只返回模糊“workflow failed”。
- P31 regression 已覆盖角色自动恢复、项目删除、新默认项目以及 ComfyUI Image Provider 的 MPS 超时/错误详情回归。
- GitHub 连接器当前仍未返回可读取的 workflow run/status，因此不虚报 CI PASS；代码与回归用例已提交，真实 Mac Web smoke 仍以用户本机结果为准。
- 关键提交：`04c92969`、`2f504616`、`9226bc4f`、`8fc1ad79`、`07e5582a`、`3c4d1536`、`2baab40d`、`6c9b62bb`、`57bcdac7`、`76d886d3`、`2e83eb77`、`6ec48dfb`、`a359d66e`、`93e3c475`、`98d0321d`、`ee891176`、`6d7da9d5`、`dac94c9a`、`a032ce3a`、`dba4e27b`、`dd2db316`。

当前 Web 验收路径：

```text
刷新 VideoCreator Web
→ AI 生图：在“国漫项目”下拉框右侧点击“删除当前项目”
→ 删除多余的《照骨灯》（保留需要的一份）
→ 页面自动切换到剩余/最新《照骨灯》
→ PROJECT CHARACTER 应显示真实项目角色
→ 点击“生成角色定妆板”
→ 本地 ComfyUI 允许完整 24-step 长任务跑完
→ 成功后直接加载图片预览；若失败，页面返回具体 ComfyUI 节点错误
```

不需要重新上传 TXT，不需要命令行。

NEXT：完成一次《照骨灯》Web 本机复验：删除重复项目 → 确认真实项目角色 → 重新生成角色定妆板；若仍失败，以页面新暴露的具体 ComfyUI node/error 为下一修复输入。


## P31-03 AI 生图中国古风风格锁
Status: CODE PASS / LOCAL WEB REVERIFY

执行记录（2026-09-20）：

- 真实 Web 结果显示 Animagine XL 4.0 虽能稳定生成动漫角色定妆板，但视觉明显偏日系二次元 / 现代制服，不符合《照骨灯》的中国古风定位。
- 根因不是单一 Prompt 缺词：共享角色 Prompt 原先同时包含 `Chinese guofeng` 与 `cinematic 3D animated series`，而项目角色 costume fallback 只写了模糊的 `period costume`；Animagine 本身又是通用动漫 checkpoint，因此会优先落到其熟悉的现代 anime 服装分布。
- `config/providers/comfyui-image-provider.json` 新增 `style_profile=GUOFENG_ANCIENT_CHINA` 与默认正向 Prompt 前缀，固定包含 Chinese guofeng donghua / ancient China / wuxia / xianxia / hanfu / crossed-collar robe / layered fabric / traditional Chinese hair ornament / ink-wash-inspired palette。
- 本地 ComfyUI Provider 在构建 workflow 时会自动把上述风格前缀置于用户 Prompt 前面；用户不需要每次在 Web 手工复制整段国风关键词。
- negative prompt 加强为硬排除 modern clothing / contemporary fashion / school uniform / sailor uniform / JK uniform / blazer / necktie / T-shirt / hoodie / miniskirt / sneakers / office wear / modern city / cyberpunk 等现代或日系校园服装。
- Character Bible / Keyframe 的共享系统 Prompt 改为“premium Chinese guofeng donghua / ancient China / Chinese fantasy / wuxia-xianxia”，明确要求汉服、交领、层叠面料、宽袖/护臂、腰封、中国传统发饰与克制玉石/金属配件，并显式禁止现代制服。
- 小说项目角色缺少已审核服装设计时，Image Studio 的 costume fallback 不再使用模糊 `source-consistent period costume`，而是明确中国古代角色适配汉服/袍服，并禁止 Japanese school uniform。
- 默认 render lock 从 `cinematic stylized 3D animation` 调整为 `premium Chinese guofeng donghua, painterly 2D/2.5D animation`，消除和 Animagine 本地 checkpoint 的语义冲突。
- Web 不再把 Animagine XL 4.0 标成“国漫基础模型”；改为“动漫基础 checkpoint（国风由系统风格锁 / 可选 LoRA 加强）”。附加要求输入框也明确“系统已默认强制中国古风古装”。
- 回归覆盖正向前缀、hanfu 关键词、school uniform / modern clothing 负向约束，以及 Web 风格锁说明。
- 当前仍不把 Animagine 误认为专用中国国风模型：如果风格锁后仍偏日系，下一步是在当前 ComfyUI workflow 增加可选国风 LoRA / 专用 guofeng checkpoint，由 Web 一键选择；不替换现有已验证的 Animagine 基础模型即可完成渐进升级。
- 关键提交：`55145b64`、`792a3705`、`98018479`、`933a2bcd`、`9052827e`、`6ddd6805`、`9c403d3d`、`e5a48a0e`、`0b9be582`、`18d37ba6`。

当前 Web 复验：

```text
重启一次 VideoCreator Web（后端 Python / Provider Prompt 已更新）
→ AI 生图
→ 附加要求可留空，直接“生成角色定妆板”
→ 期望：角色整体仍是动漫，但服装/发型/配色必须明显进入中国古风古装语义
→ 不应再次出现 JK / 水手服 / 西式校服 / T 恤短裙 / 运动鞋等现代服装
```

手工需要进一步加强时，只在“附加要求”里写具体朝代/美术方向，例如：
`宋制汉服，交领右衽，月白与黛青，墨色长发，玉簪，衣料厚重，低饱和水墨配色，武侠国漫角色设定，禁止现代服饰与日系校园制服。`

NEXT：本机重生成一张《照骨灯》角色定妆板确认“古风服装命中率”；若仍明显偏日系，进入 P31-04 Web 可选国风 LoRA / 专用 checkpoint。


## P31-04 Image Studio 风格预设 + 中国国风 LoRA
Status: CODE PASS / LOCAL WEB REVERIFY

执行记录（2026-09-20）：

- 2026-09-20 LoRA 安装器入口修复：本机 Web 后台直接执行 `scripts/comfyui_lora_manager.py` 时曾报 `ModuleNotFoundError: No module named 'scripts'`。根因是脚本文件方式启动时仓库根目录不在 `sys.path`。现已在 import `scripts.*` 前显式注入 repo root，并把后台启动改为 `python -m scripts.comfyui_lora_manager --install <catalog-id>`；同时 P31 CI 新增“直接脚本入口 + module 入口”双重启动校验，防止该问题回归。

- Image Studio 从单一 Prompt 风格锁升级为正式“画面风格预设”系统；配置统一落在 `config/providers/image-style-presets.json`，当前提供 5 种 Web 可选风格：
  - `GUOFENG_ANCIENT_CHINA` → 中国古风（默认）
  - `XIANXIA_DONGHUA` → 仙侠国漫
  - `WUXIA_DONGHUA` → 武侠国漫
  - `INK_GUOFENG` → 水墨国风
  - `ANIME_DEFAULT` → 默认动漫
- 每个预设独立维护 Positive Prompt、Negative Prompt、OpenAI fallback 风格描述、可选 LoRA ID 与 LoRA strength；不再要求用户把长串关键词手工粘到“附加要求”。
- 《照骨灯》及其他首次进入 Image Studio 的小说项目默认使用“中国古风”；风格选择按项目保存在浏览器 localStorage，切换项目后不会互相污染。
- 中国古风 / 仙侠 / 武侠 / 水墨预设继续强制排除现代服饰、JK / 水手服 / 校服、短裙、运动鞋、西装领带、现代都市 / 赛博朋克等不符合古代中国视觉方向的元素；“默认动漫”不加载国风 LoRA。
- 新增 `scripts/comfyui_lora_manager.py`：只允许安装代码审核过的固定 LoRA catalog，不接受任意 URL；支持断点续传、代理自动发现、磁盘空间检查、精确文件大小校验、SHA256 校验、异常文件隔离与后台安装。
- 当前固定国风增强 LoRA：`sdxl-chinese-style-illustration`；安装目录为 `.dependencies/ComfyUI/models/loras/`。Web 只发送 catalog ID，下载 URL 不由浏览器提供。
- ComfyUI Provider 新增 `available_loras()`；生成工作流在 LoRA 已安装且当前 ComfyUI 实际可见该文件时自动插入核心 `LoraLoader` 节点，同时把 model 与 CLIP 都通过 LoRA，再进入 CLIPTextEncode / KSampler。无需用户打开 ComfyUI 拖节点。
- LoRA 未安装、尚未被外部 ComfyUI 刷新识别或当前预设不需要 LoRA时，生成链不会被阻塞：继续使用对应风格的 Positive + Negative Prompt 完成 prompt-only 生成。
- Web AI 生图页新增：
  - “画面风格”下拉框；
  - “中国国风 LoRA”状态卡；
  - “安装国风 LoRA”一键按钮；
  - 下载进度 / SHA256 状态 / ComfyUI 是否已经识别 LoRA 的 READY 状态。
- LoRA 安装完成后，如果 ComfyUI 是 VideoCreator 托管进程，会自动 stop → start → 等待就绪 → 刷新模型列表；若用户自己启动了外部 ComfyUI，不会擅自杀掉外部进程，只提示需要用户重启外部 ComfyUI。
- OpenAI Image fallback 也复用相同风格预设的 `remote_direction` / forbidden direction，因此远程回退不会丢掉“中国古风 / 仙侠 / 武侠 / 水墨”的风格选择。
- Image Studio 生成 metadata 现在记录 `style_preset`、`style_label`、`lora_requested`、`lora_applied`、`lora_name`、`lora_strength`；Web 最近生成卡片与结果详情直接显示“风格 + LoRA ON / Prompt only”，避免用户猜测 LoRA 到底有没有真正生效。
- P31 regression 已增加 style preset、LoRA Loader workflow、固定 allowlist 下载、SHA256 原子安装、异常文件隔离以及 Web 控件回归；workflow 同时对新增 Python 文件执行 py_compile，并继续执行 Node `--check web/app.js`。
- 当前仍保持真实边界：代码链已完成，但 GitHub 连接器无法代替用户 Mac 的 MPS / ComfyUI 运行时验证；国风 LoRA 与当前 Animagine XL 4.0 的最终视觉效果和最优 strength 必须由本机真实出图确认后再微调。
- 关键提交：`a2d75cb1`、`9db39665`、`cbf33394`、`c7d8e0fb`、`7ca08418`、`85eaa350`、`7cdbd8af`、`59436569`、`9d68dc18`、`dbca3670`、`5e2226bf`、`04553269`、`03ef914b`、`aa203af6`、`0f987718`、`36dfa47f`、`cf332779`、`f5f34cb9`、`1e99a07c`。

当前 Web 验收路径：

```text
重启一次 VideoCreator Web
→ AI 生图
→ “画面风格”默认应为“中国古风”
→ 点击“安装国风 LoRA”
→ 等待约 341 MB 下载 + SHA256 校验
→ 托管 ComfyUI 自动刷新；LoRA 状态应进入 READY
→ “附加要求”先留空
→ 点击“生成角色定妆板”
→ 最近生成 / 结果详情应显示：中国古风 · LoRA ON
→ 视觉验收：汉服 / 中国古代发饰 / 古装轮廓明显；不得再出现 JK、水手服、现代短裙、运动鞋、西装领带
```

如果暂时不安装 LoRA，也可以直接选择“中国古风”生成；结果详情会明确显示 `Prompt only`，便于和 LoRA ON 的结果做 A/B 对比。

NEXT：完成《照骨灯》本机 Web smoke（LoRA 安装 → READY → 中国古风定妆板）；若出现具体 LoraLoader / model compatibility 错误，按 Web 暴露的节点错误继续修；若技术链 PASS 但国风强度仍不足，再微调 LoRA strength 或增加第二个汉服专用 LoRA / 国风专用 checkpoint，而不是继续盲目堆 Prompt。


## P31-05 《照骨灯》最终视觉纠偏：电影级 3D 国漫
Status: SUPERSEDED BY P31-06

执行记录（2026-09-20）：

- 用户真实生成结果确认：P31-04 的“中国古风 + sdxl-chinese-style-illustration LoRA”已经能稳定得到汉服、中国发饰和古风配色，但最终仍是明显的 2D/水彩/设定插画，缺少真正 3D 国漫需要的体积、透视、材质、灯光和景深。
- 该结果不是单一提示词失败，而是系统方向存在冲突：
  - P31-03 曾把默认 render lock 改为 `painterly 2D/2.5D animation`；
  - 当前国风 LoRA 本身就是 `Chinese style illustration`，会进一步强化平面插画分布；
  - Animagine XL 4.0 是动漫基础 checkpoint，不应再被当作电影级 3D 国漫最终画质生产器。
- 新增并设为全局默认风格：`CINEMATIC_3D_DONGHUA` / “电影级 3D 国漫”。
  - 目标固定为真正立体的高质量 3D 中国国漫：fully modeled volumetric character、sculpted facial planes、dimensional hair、layered cloth thickness、NPR/Toon + believable PBR material response、subsurface skin、cinematic key/fill/rim light、volumetric atmosphere、perspective、real depth of field。
  - 负向明确排除 flat illustration / 2D drawing / watercolor / ink-paper painting / lineart / cel cutout / cardboard cutout / flat concept illustration / visual novel art / no-depth render。
- “电影级 3D 国漫”**不加载** `sdxl-chinese-style-illustration`。该 LoRA 保留给“中国古风插画 / 仙侠 / 武侠 / 水墨”等概念预览预设，避免插画 LoRA 再把最终角色压回平面。
- 旧“中国古风”重命名为“中国古风插画”，render role 明确为 `CONCEPT_PREVIEW`；不再与最终 3D 视觉混淆。
- 默认角色 render lock 从 2D/2.5D 恢复为 `premium cinematic 3D Chinese donghua`；final 3D preset 在运行时会覆盖项目旧 Visual Bible 中遗留的 2D rendering/art-direction，避免旧项目继续把最终生成拉回平面。
- Character Bible Prompt 对 3D 风格改为真正 `3D production character-turnaround board`：
  - 每个视图必须是同一个 fully modeled 3D character 的 camera render；
  - 保留真实体积、透视、材质厚度和统一 studio lighting；
  - beauty portrait 必须像 finished film character render；
  - 明确禁止 flat painted views。
- Keyframe Prompt 对 3D 风格强制 true 3D film frame：sculpted face volume、dimensional hair geometry、cloth thickness/folds、contact shadows、film lighting、atmospheric depth、real DOF、NPR/PBR 材质响应。
- Provider 路由按风格升级：
  - `CINEMATIC_3D_DONGHUA` 的 `preferred_provider=OPENAI_IMAGE`、`render_role=FINAL_VISUAL`；
  - Web 选择 `AUTO + 电影级 3D 国漫` 且 OpenAI Image 已配置时，优先走 OpenAI 最终视觉，而不是本地 Animagine；
  - OpenAI 未配置时仍允许本地 ComfyUI 回退，但结果明确标记 `LOCAL_PREVIEW`，不再冒充最终画质；
  - 用户显式选择 ComfyUI 时同样允许低成本预览。
- Image Studio 的项目风格 localStorage key 从 v1 升级为 v2，旧项目之前记住的“中国古风插画”不会继续覆盖新的 3D 默认值；《照骨灯》重新进入页面后默认应切到“电影级 3D 国漫”。
- Web 结果 metadata / 详情现在记录并展示 `FINAL_VISUAL` / `LOCAL_PREVIEW` / `CONCEPT_PREVIEW`，同时 3D 风格下 LoRA 卡明确显示 `NOT USED BY 3D`。
- 新增 3D Prompt regression，锁定 turnaround 必须 true volume、finished film character render，keyframe 必须 true 3D film frame / cloth thickness / real DOF；P31 CI 已纳入。
- 关键提交：`2db9f89b`、`ecc9633d`、`d1829746`、`37cd2132`、`2aac2812`、`3c5480f7`、`ee51ca37`、`f44d13ff`、`f6e8a2d8`、`f9bee2bd`、`bb2d63f7`、`40b38b26`。

当前 Web 验收路径：

```text
重启一次 VideoCreator Web
→ AI 生图
→ 画面风格应默认：电影级 3D 国漫
→ 国风插画 LoRA 卡应显示：NOT USED BY 3D
→ Provider 保持 AUTO

如果 OpenAI Image 已配置：
  → 顶部 Provider 应显示 AUTO → OpenAI Final
  → 点击“生成角色定妆板”
  → 确认一次可能产生 API 费用
  → 结果详情应包含：电影级 3D 国漫 · FINAL_VISUAL · No illustration LoRA

如果 OpenAI Image 未配置：
  → 页面明确提示 AUTO 只能生成 LOCAL PREVIEW
  → Animagine 本地结果只用于低成本构图/角色方向预览，不作为最终 3D 验收

最终视觉验收：
  → 角色必须有明显头面体积、鼻梁/颧骨/下颌转折
  → 头发必须是有体积的发束/发丝，不是平涂轮廓
  → 汉服必须有衣料厚度、褶皱、层叠与真实遮挡关系
  → 光照必须有 key/fill/rim、接触阴影、体积光
  → 画面必须有透视与景深
  → 禁止水彩纸感、平面插画、二维纸片、视觉小说立绘
```

NEXT：在《照骨灯》上生成一张 `FINAL_VISUAL` 角色定妆板做真实视觉验收；如 OpenAI 最终视觉仍不匹配，再基于该真实结果微调 3D art direction，而不是继续给 Animagine 叠插画 LoRA。


## P31-06 对齐参考视频：单人半写实 3D LookDev + 禁止 Animagine 冒充最终视觉
Status: CODE PASS / FINAL PROVIDER WEB REVERIFY

执行记录（2026-09-20）：

- 用户再次提供真实生成截图后确认：即使风格选择已经显示“电影级 3D 国漫”，只要结果 metadata 仍是 `comfyui_image · animagine-xl-4.0 · LOCAL_PREVIEW`，画面仍会停留在 2D/anime illustration 分布，不能达到此前参考视频的半写实 3D 国漫成片质感。
- 参考视频目标重新锁定为：
  - 成年角色：半写实、修长成熟、东方面孔，真实头面 / 肩胸体积；
  - 儿童角色：仅在角色本身是儿童时允许明显幼态 / Q 比例；
  - 材质：softened PBR + restrained NPR/Anime，皮肤 SSS、发束/发丝体积、衣料厚度、玉石/金属真实材质响应；
  - 灯光：暖夕阳 / 灯笼逆光 + 冷色柔和面部补光 + key/fill/rim；
  - 镜头：中长焦、浅景深、古风环境层次与空气透视；
  - 表演：最终进入视频阶段后要求视线、头部反应、手势和微表情，而不是纸片平移。
- `CINEMATIC_3D_DONGHUA` 保持原 ID，避免旧项目丢失选择，但显示名升级为“参考视频·电影级 3D 国漫”，配置 schema 升至 v3。
- Final preset 新增：
  - `layout_mode=SINGLE_LOOKDEV_HERO`
  - `final_provider_required=true`
  - `preferred_provider=OPENAI_IMAGE`
  - `render_role=FINAL_VISUAL`
- Character Bible 在该 preset 下不再生成多视图 concept sheet。Prompt 改为 **ONE finished cinematic 3D character LookDev beauty render**：
  - 只允许一个角色 / 一个身体 / 一张脸 / 一个 camera view；
  - 三分之四全身 beauty composition；
  - 禁止 turnaround sheet、multi-panel、collage、ghost figures、faded duplicate figures、expression grid；
  - 直接按参考视频风格要求暖色 rim/backlight、冷色 face fill、中长焦、浅景深与古风环境。
- 这是针对本轮截图中“中心角色 + 周围幽灵分身”问题的结构修复：不再让扩散模型一次在同一张图里承担正/侧/背/表情九宫格式角色一致性。
- Final preset 的负向词新增：concept sheet / character sheet / turnaround sheet / multi-panel layout / multiple copies / ghost figures / flat 2D drawing / watercolor / paper texture / oversized anime eyes 等。
- 后端现在对 Final preset 强制最终 Provider 门禁：
  - `AUTO + OpenAI configured` → 允许 Final Visual；
  - `AUTO + OpenAI not configured` → 直接 BLOCK，不再静默回退 Animagine；
  - 用户显式选 `COMFYUI_IMAGE` + Final preset → 直接拒绝，并提示 Animagine 只能用于概念预览。
- Web 同步修改：
  - Final Provider 缺失时顶部状态显示 `FINAL PROVIDER REQUIRED`；
  - Model 显示 `OpenAI Image required`；
  - Provider 显示 `AUTO → Final Provider Required` 或 `BLOCKED · Final requires OpenAI`；
  - 主按钮在 Final preset 下改为“生成最终 3D LookDev”；
  - 缺少 Final Provider 时按钮禁用，不再生成一张 LOCAL_PREVIEW 让用户误以为这是最终效果；
  - OpenAI Key 区明确改为“参考视频 3D 最终视觉”。
- “中国古风插画 / 仙侠 / 武侠 / 水墨”等本地 ComfyUI 预设仍保留，继续服务低成本概念草图；它们和最终 3D LookDev 不再混用。
- P31 regression 新增：
  - single LookDev hero prompt 不得包含多视图 sheet 指令；
  - Final preset 必须带 `SINGLE_LOOKDEV_HERO` / `final_provider_required`；
  - AUTO 且无 OpenAI 时必须拒绝 Animagine fallback；
  - 显式 COMFYUI_IMAGE 时必须拒绝 Final preset。
- 关键提交：`44b46008`、`a9f67069`、`49f8bac1`、`cd6a7bfd`、`00b6b4ba`、`03b6fd79`、`354808ef`、`8dd23873`、`6e3a7b5d`、`ce067883`、`1dc2f3d6`。

当前 Web 验收路径：

```text
重启一次 VideoCreator Web
→ AI 生图
→ 画面风格：参考视频·电影级 3D 国漫
→ 生图路线：AUTO

若未配置 OpenAI Image：
  → 状态必须显示 FINAL PROVIDER REQUIRED
  → “生成最终 3D LookDev”不可点击
  → 不允许再产生 Animagine LOCAL_PREVIEW

配置 OpenAI Image 后：
  → Provider 显示 AUTO → OpenAI Final
  → 点击“生成最终 3D LookDev”
  → 生成结果必须是一张单人三分之四全身电影 LookDev beauty render
  → 不允许角色定妆 sheet / 九宫格 / 幽灵分身 / 淡化复制人物
  → 视觉验收：半写实 3D 国漫、真实头面和肩胸体积、发丝/衣料厚度、soft PBR + restrained NPR、暖逆光+冷补光、中长焦浅景深、古风环境空气透视
```

本地路线后续候选（不在本轮自动安装）：
- Qwen-Image-Edit-2511 + Anyto3DDonghuaStyle 可作为“本地概念图 → 3D 国漫风格转换”的第二阶段 Image-to-Image 路线；但基础模型体积和运行资源显著高于当前 Animagine，必须单独做磁盘 / 内存 / MPS 预检后再进入 Web 一键安装，不能静默替换现有低成本链路。

NEXT：先完成一张 `FINAL_VISUAL + SINGLE_LOOKDEV_HERO` 的《照骨灯》角色真实验收；通过后再把该 LookDev 作为角色锚点，进入多角度 consistency / keyframe / image-to-video，而不是再次从纯文本生成九宫格。
