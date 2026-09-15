---
name: video-creator-validation
description: Produce and independently verify real VideoCreator pilot cohorts without publishing.
---

# VideoCreator Pilot Validation

P14 只统计真实项目。每条必须具有可播放的 `final.mp4`、完整 QC、七文件发布包、`READY_FOR_REVIEW` 状态和 `pilot-evaluation.json`，不得用测试夹具、空文件或合成占位结果计数。

首批五条可运行 `python3 scripts/pilot_producer.py` 本地生成。该批次固定使用官方来源、本地非计费 macOS 中文语音、动态信息卡视觉、真实 FFmpeg 成片、技术/内容/视觉 QC、封面、发布文案、打包和人工审核门禁。流程不得上传或发布。

生产程序完成后必须再运行 `python3 scripts/pilot_validation.py` 独立复核五个不同项目。验证器重新读取状态、QC、发布包、媒体流和成片 SHA-256，并要求稳定生成、风格、时长、字幕、语音和 Hook 六项全部通过。
