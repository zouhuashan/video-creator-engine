---
name: video-creator-qc
description: Validate rendered VideoCreator outputs and produce traceable QC evidence.
---

# VideoCreator QC

技术质检必须读取真实 `final.mp4`，通过 ffprobe 检查媒体流，通过 FFmpeg 完整解码并扫描黑帧、冻结帧、静音和音频峰值。字幕质检读取渲染器输出的 `subtitle-layout.json`；字幕框使用 0～1 归一化坐标，必须位于配置的安全区内且不与视频号 UI 保留区重叠。缺少字幕布局证据不能宣告通过。

运行 `python3 scripts/technical_qc.py <project-dir>`，结果写入 `qc/technical-qc.json`。任一检查失败时保留失败证据，不推进项目状态。

内容质检由 `python3 scripts/content_qc.py <project-dir> --assessment-file <JSON>` 执行。审查文件必须覆盖配置中的十项检查，每项写明 PASS/FAIL、具体证据及使用到的研究来源编号。程序会再次检查重复口播、无来源绝对化词语、敏感表达、Hook、结论和 CTA；人工或自动规则任一失败即为失败。
