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
NEXT: P20-01 全剧、季度和角色弧规划
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

状态：TODO

- P20-01：全剧、季度和角色弧规划。
- P20-02：故事弧、单集卡和结尾钩子规划。
- P20-03：场景剧本、对白、旁白、情绪、声效和 continuity delta。
- P20-04：剧情因果、节奏、人物动机、伏笔与跨集矛盾审核。

### P21 视觉圣经与资产系统

状态：TODO

- P21-01：国风视觉风格、色彩脚本、构图和负面约束。
- P21-02：角色转面、表情、服装、比例、配色和身份一致性资产。
- P21-03：地点、道具、天气、时间和光线版本。
- P21-04：参考包、资产版本、选择记录和人工美术审核。

### P22 分镜与 Animatic

状态：TODO

- P22-01：Scene/Shot 分解、镜头语法、首尾状态和稳定镜头 ID。
- P22-02：静态 storyboard、首尾帧、镜头时长和前后连续关系。
- P22-03：本地 animatic、临时配音、字幕和集级预览。
- P22-04：节奏、动作可读性、角色/场景/道具连续性审核。

### P23 音频制作

状态：TODO

- 角色 voice profile、逐句对白、旁白、情绪与发音版本。
- 音乐、环境声、动作音效、来源授权、混音、响度和声画同步。

### P24 动态镜头

状态：TODO

- 按镜头路由本地运镜、图生视频、首尾帧、口型或人工导入。
- 建立远程队列、预算、素材上传授权、重试、回退和版本审核。

### P25 剪辑与后期

状态：TODO

- 集级时间线、对白与镜头组装、转场、特效、调色、字幕和音频总线。
- 支持镜头级替换与无损局部重渲染。

### P26 六类 QC 与人工审核

状态：TODO

- 来源权利、剧情、连续性、角色与视听、技术、人工发布六类质量门。
- Web 批注、问题单、局部返工、版本对比和最终人工确认。

### P27 Web 制作台

状态：TODO

- 项目总览、IP 与底本、故事圣经、编剧室、角色美术、分镜、音频、渲染队列、审片和发布包十个工作区。
- 所有页面操作同一套项目 Schema 和状态机，不维护独立的 Web 数据副本。
- P18～P26 每阶段同步交付对应 API 与最小 Web 页面；P27 负责统一导航、批量操作、审片体验、备份恢复和全局整合，不把 Web 延迟到最后才开发。

### P28 《镜花缘》正式五集验收

状态：TODO

- 把旧五集技术样片迁移为参考资料，用新流程重新完成五集连续剧情、角色视觉、配音、字幕和 animatic。
- 至少选择一集的三个代表镜头接入真实动作 Provider，比较动作质量、一致性、时长与成本。
- 通过六类 QC 和人工审片后，再决定是否扩展第一季。

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
