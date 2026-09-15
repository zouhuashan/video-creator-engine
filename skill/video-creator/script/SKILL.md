# Script 阶段

将已通过选题门槛的研究结果写成微信视频号六段脚本。

## 前置条件

- 项目状态必须为 `RESEARCHED`。
- 读取 `research.json`、`topic.json` 和 [script-template.md](../../../templates/wechat-channel/script-template.md)。
- `topic.json` 必须为 `eligible_for_production`，风险过滤通过，且总分达到配置门槛；否则停止脚本制作并报告原因。
- 脚本主题必须与 `research.json` 一致。事实性主张只使用已核实研究内容，并为对应段落提供来源编号；`search_summary` 不能单独支撑事实。

## 编写与落盘

按顺序填写 `Hook`、`Problem`、`Evidence`、`Comparison`、`Conclusion`、`CTA`。Evidence 段至少引用一条非搜索摘要来源。口播稿写入 `narration`，来源编号写入 `source_ids`；不要把来源编号写进需要朗读的正文。Hook 对应开头 3 秒，还要在 `hook_type` 中标记 `conclusion`、`counterintuitive` 或 `conflict`，开场第一句需直接表达相应的结论、反常识或冲突。

所有段落用自然中文口播，避免论文式措辞、“首先、其次、最后”等机械连接词，每句话只表达一个重点。脚本校验会按 [script-style.json](../../../config/script-style.json) 检查禁用表达、句长、逗号数量和 Hook 类型标记；提交前也要通读一遍，确认念出来顺口。

## 时长估算与压缩

- 将用户指定时长写入 `target_duration_seconds`；未指定时按 [script-duration.json](../../../config/script-duration.json) 使用默认值 60 秒。脚本模板允许 45～90 秒。
- `word_count` 统计汉字数量并将连续的非汉字字母/数字串各计一个单位，口播来源标注不计入；`speech_rate` 使用配置的估算语速（口播单位/分钟），`estimated_duration` 按字数和该语速估算为秒。
- 只把确认可删、且不含唯一事实依据或关键结论的完整补充句放入 Problem、Comparison、Conclusion 的 `optional_sentences`。若超时，命令按配置顺序自动删除这些句子并重新估算；Hook 必须控制在开头 3 秒，Evidence 和 CTA 会保留。
- 若删除可删句后仍超时，命令不写产物、不推进项目状态。根据报错压缩口播稿，保留六段结构、核心事实和来源引用，再重新运行命令；直到估算时长符合目标。

将输入保存为临时 JSON，格式见 [script-input.schema.json](../../../templates/script-input.schema.json)，然后执行：

```text
./video-creator script <project-id> --input-file <script-input.json>
```

命令会校验六段内容、评分门槛和所有来源编号，输出项目目录中的 `script.json` 与 `script.md`，再把状态从 `RESEARCHED` 推进到 `SCRIPTED`。已有脚本产物时拒绝覆盖。写入失败或校验失败时不得推进状态。
