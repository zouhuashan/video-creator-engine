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
Status: TODO

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
Status: TODO

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
Status: TODO

要求：

- 固定 Git commit/tag。
- 不直接追 latest。
- 写入 dependency manifest。

---

## P6-02 默认动效
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

相同：

```text
text + voice + speed + provider
```

命中缓存时不得重复计费生成。

---

## P8-03 中文口播优化
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

要求：

- 3～10 个核心字。
- 移动端可读。
- 一眼知道问题。
- 禁止密集小字。
- 支持 2～3 个候选封面。

---

## P12-03 标题候选
Status: TODO

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
Status: TODO

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
Status: TODO

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
Status: TODO

验证：

- 稳定生成
- 风格
- 时长
- 字幕
- 语音
- Hook

---

## P14-02 生产 10 条
Status: TODO

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

---

## P14-03 完成 20 条
Status: TODO

只有满足：

```text
20 条成功生成
≥ 90% 不需要工程级人工修复
局部重跑有效
平均制作时间可接受
```

才进入 V2。

---

# 23. V2 — 自动选题与数据闭环

状态：PLANNED

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

## V2-02 自动选题池
输出：

```text
topics/YYYY-MM-DD.json
```

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

当前只执行 V1。

严格顺序：

```text
P0
→ P1
→ P2
→ P3
→ P4
→ P5
→ P6
→ P8
→ P9
→ P10
→ P11
→ P12
→ P13
→ P14
```

Remotion：

```text
P7 = V1 OPTIONAL
```

只有 HyperFrames 无法满足具体场景时提前启用。

---

# 41. 下一任务

```text
NEXT: P5-02
```

任务：

> 创建并校验包含来源、授权、生成者和校验和的 asset-manifest.json。

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
