# Research 阶段

将选题调查与报告落盘分开：先按用户的 `source_mode` 获取并核对材料，再提交带来源引用的结构化输入，由 Research 模块生成项目产物。

## 调查要求

- 从项目 brief 读取 `topic` 和 `source_mode`。`automatic_research` 可检索公开资料；`user_materials_first` 优先核对用户材料；`provided_sources_only` 只使用用户给定来源；`no_external_research` 不做外部检索。没有可支持核心事实的材料时，说明缺少的证据，不编造来源或把推测写成事实。
- 按来源等级选择事实依据：`official`（官方来源）优先于 `primary_document`（原始文档），再优先于 `authoritative_media`（权威媒体）、`high_quality_community`（高质量社区）和 `search_summary`（搜索摘要）。能找到更高等级的直接来源时，不用低等级来源替代；同一事实引用多个来源时按等级从高到低排列。
- 搜索摘要只用于发现候选来源，必须打开原始页面核对后才能作为事实依据。不得让 `search_summary` 单独支撑任何事实、FAQ、观点、价格/规格/版本或风险条目；若无法打开原始页面，该条目应标为待核实而不写入已核验事实。
- 类型判定依据：`official` 是产品/机构/监管方发布的信息；`primary_document` 是原始论文、标准、公告、合同、财报或原始记录；`authoritative_media` 是有编辑核验的专业媒体报道；`high_quality_community` 是提供可复核原始材料或可重复测试的专业社区内容。不要仅按域名知名度推断可信度。
- 逐篇打开来源页面核对主张，不把搜索摘要当作已验证依据。为每个事实、FAQ 答案、正反观点、价格/规格/版本和风险记录 `source_ids` 与不超过 500 字符的 `evidence` 摘要。
- 记录来源标题、发布方、直接 URL、可获得的发布日期、查阅时间和来源类型。价格、规格、版本等易变内容要记录核验时间。
- 素材方向可以是基于已核实事实提出的拍摄/画面建议；不要把创意建议伪装成外部事实。

## 生成项目产物

按 [research-input.schema.json](../../../templates/research-input.schema.json) 整理 JSON brief 到临时输入文件，然后执行：

```text
./video-creator research <project-id> --input-file <research-input.json>
```

命令校验来源引用、输出 `research.json`、`research.md` 和 `sources.md`，再把状态从 `CREATED` 推进到 `RESEARCHED`。输入校验失败或写入失败时不得推进状态；已有研究产物时命令拒绝覆盖。检查三份文件及 `run.json` 后，再进入下一个阶段。
