# Topic Scoring

在 Research 产物生成后评估选题。Codex 按本文件给五个主观维度打分并写明理由；评分程序从 `research.json` 自动计算证据强度、风险分、加权总分和是否通过门槛。

## 评分输入

五个需要评估的维度都用 0–100 整数，并提供不超过 500 字的理由：

- `traffic_value`：问题覆盖人群、需求强度、时效热点和 3 秒内形成钩子的潜力。没有趋势数据时按保守分数评估，不把猜测写成搜索量事实。
- `commercial_value`：与频道定位的匹配程度、对观众实际决策的帮助，以及可自然延伸的商业场景。
- `evergreen_score`：事实和需求能维持多久；高度依赖短期版本、价格或新闻的选题得分较低。
- `production_cost`：原始成本/复杂度分，0 表示低成本、易制作，100 表示成本高、依赖难取得的素材或复杂演示。该值在总分中反向计入。
- `originality`：问题切口和表达方式相对常见内容的新颖程度；仅添加“AI”标签不加分。

0 表示极弱或极不利，50 表示一般，100 表示极强或制作代价极高；介于锚点间按证据给分。避免无理由的整数精度。

`evidence_strength` 不能由评分人填写。程序逐条读取核心事实引用，取该条最佳来源等级分（官方 100、原始文档 90、权威媒体 80、高质量社区 60）；若至少有两个不同发布方交叉支持该事实，加配置中的独立来源分，最高 100；最后对事实分取平均并四舍五入。Research brief 中的 publisher 写实际发布机构；同一机构的不同页面只算一个发布方。

`risk_score` 根据 Research 风险严重度自动计算：low=20、medium=45、high=75、critical=95；每多一项已记录风险增加配置中的分数，最高 100。没有记录风险时为 0。风险分不进入总分，而是独立过滤。

## 总分和门槛

执行前读取 `config/topic-scoring.json`。总分为：

```text
traffic_value × 20%
+ commercial_value × 20%
+ evergreen_score × 20%
+ evidence_strength × 15%
+ originality × 15%
+ (100 - production_cost) × 10%
```

四舍五入为整数。总分低于 60 时不得自动进入制作；风险分达到配置阈值 70 时触发独立风险拦截，即使总分很高也不得自动进入制作。

把五个评分和理由按 [topic-assessment.schema.json](../../../templates/topic-assessment.schema.json) 写入临时 JSON 文件，运行：

```text
./video-creator score <project-id> --assessment-file <topic-assessment.json>
```

命令要求项目状态为 `RESEARCHED`，读取研究和评分配置，输出 `topic.json`，但不推进生命周期。判断依据和维度理由一并保存；输出为 `do_not_enter_production` 或 `blocked_by_risk_filter` 时停下并向用户说明原因。只有两道门槛都通过才可继续后续制作阶段。
