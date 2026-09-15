---
name: video-creator-edit
description: Build and render a short-video edit through the pinned video-use checkout after assets and voice are ready.
---

# VideoCreator Edit

使用 `dependency-manifest.json` 固定的 video-use 提交和 `adapters.video.video_use` 边界。所有输出写入项目的 `edit/`，原始视频保持不变。

执行顺序：盘点并理解原始视频 → 逐字转录与缓存 → 从词边界决定停顿、口癖和失误段落的删除 → 写 EDL → 裁切与音频衔接 → 插入 B-roll 和 Overlay → 最后叠加字幕 → 生成预览 → 最多三轮基础自评 → 输出最终成片。

必须保持这些正确性规则：字幕位于所有 Overlay 之后；剪点落在词边界并保留 30–200ms 边距；每个片段边界有 30ms 音频淡入淡出；Overlay 使用输出时间轴偏移；字幕时间使用裁切后的输出时间轴；相同源文件的转录必须复用。

先用 `verify_video_use_installation` 检查固定提交、Python 环境、ffmpeg、ffprobe 和 helpers。用 `probe_source` 读取真实媒体信息，以 `validate_edl` 检查 EDL，再运行 `render_command` 返回的命令。预览生成后按 `build_self_eval_plan` 检查开头、结尾和每个剪点附近的画面、波形、字幕遮挡、Overlay 时序及总时长；三轮后仍有问题时停止并报告。

video-use 自带的转录实现仍属于外部依赖边界；在 ASR Adapter 完成前，不把 ElevenLabs 当作剪辑核心的固定要求，也不声称其它 ASR 已可替换。
