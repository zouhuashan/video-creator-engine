# 微信视频号脚本模板

主题：填写与 `research.json` 一致的选题

口播稿按以下顺序填写。事实性内容在输入 JSON 中关联 `source_ids`；引用标注只用于核验，不读出口播。Evidence 至少引用一条非搜索摘要来源。

Hook 对应开头 3 秒，另需填写 `hook_type`：`conclusion`（先给结论）、`counterintuitive`（反常识）或 `conflict`（明确冲突）。开场第一句要让观众立刻听到对应内容。用短句和常用中文表达，每句只说一个重点；避免论文式措辞和“首先、其次、最后”的机械连接。

输入还可设置 `target_duration_seconds`（默认 60 秒）。Problem、Comparison、Conclusion 中可用 `optional_sentences` 标记确认可以删去的完整补充句；超时后系统按配置顺序删除这些句子，保留 Hook、Evidence 和 CTA。不要把关键结论或独有证据标成可删内容。

## Hook

用一句开场抓住注意力。

## Problem

说明观众遇到的问题或冲突。

## Evidence

用已核实的事实、演示结果或证据支撑主题。

## Comparison

呈现方案、观点或预期与实际之间的对比。

## Conclusion

给出明确结论。

## CTA

给出一个清楚、自然的下一步引导。
