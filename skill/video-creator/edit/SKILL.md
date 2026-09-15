---
name: video-creator-edit
description: Build and render a short-video edit through the pinned video-use checkout after assets and voice are ready.
---

# VideoCreator Edit

使用 `dependency-manifest.json` 固定的 video-use 提交和 `adapters.video.video_use` 边界。所有输出写入项目的 `edit/`，原始视频保持不变。

执行顺序：盘点并理解原始视频 → 逐字转录与缓存 → 从词边界决定停顿、口癖和失误段落的删除 → 写 EDL → 裁切与音频衔接 → 插入 B-roll 和 Overlay → 最后叠加字幕 → 生成预览 → 最多三轮基础自评 → 输出最终成片。

必须保持这些正确性规则：字幕位于所有 Overlay 之后；剪点落在词边界并保留 30–200ms 边距；每个片段边界有 30ms 音频淡入淡出；Overlay 使用输出时间轴偏移；字幕时间使用裁切后的输出时间轴；相同源文件的转录必须复用。

先用 `verify_video_use_installation` 检查固定提交、Python 环境、ffmpeg、ffprobe 和 helpers。用 `probe_source` 读取真实媒体信息，以 `validate_edl` 检查 EDL，再运行 `render_command` 返回的命令。预览生成后按 `build_self_eval_plan` 检查开头、结尾和每个剪点附近的画面、波形、字幕遮挡、Overlay 时序及总时长；三轮后仍有问题时停止并报告。

转录统一通过 `adapters.asr.transcribe_for_video_use` 写入 video-use 格式。ElevenLabs、Whisper API 和其它会上传媒体的 Provider 必须先获得用户明确授权；Local Whisper 不上传。所有 Provider 必须返回逐词时间戳，短语级结果不能用于剪点。相同源文件、Provider、语言和说话人数命中转录缓存；缓存损坏时停止，禁止用自动重试绕过潜在计费。

剪辑决策必须用 `scripts/edit_decision_list.py` 写入项目 `edit/edit-decision-list.json`，每段保留稳定 `decision_id` 和非空 `reason`。创建、局部修改与回滚都会写入 `edit/edl-history/`，禁止直接覆盖当前文件或历史文件。局部修改和回滚必须携带当前 `expected_revision`；重渲染前运行 `rerender-plan`，源文件校验和变化时重新审查剪辑决策。

最终合并使用 `adapters.video.ffmpeg_finalizer`，不要拼接未经校验的 shell 字符串。Finalizer 统一处理视频合并和转场、音轨延迟与混音、-14 LUFS 响度标准化、尺寸、FPS、H.264/AAC 编码、码率及 MP4 faststart 封装。所有输入路径、参数和输出扩展名通过校验后再执行。
