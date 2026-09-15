---
name: video-creator-voice
description: Normalize Chinese narration, select a configured TTS provider, and synthesize through the bill-safe voice cache.
---

# VideoCreator Voice

在素材阶段完成后生成中文配音。先读取 `config/zh-voice.json` 和 `config/providers.yaml`，确认音色 ID、语速、情绪及 Provider；音色 ID 未配置时停止并明确指出缺项，不猜测公共音色。

调用顺序固定为：

1. 用 `optimize_chinese_speech` 处理数字读法、英文缩写、产品名、中英文边界、停顿、情绪和强调。
2. 将返回的 `SpeechPlan.text`、voice、speed、`SpeechPlan.emotion` 交给 `CachedTTS.synthesize`。
3. 缓存命中时直接复用音频；损坏缓存必须报告，禁止为绕过错误自动再次调用付费 Provider。
4. 新生成的音频写入项目并记录 Provider、voice、speed、emotion、缓存键和校验和，成功后才能推进到 `VOICE_READY`。

原稿使用 `{pause:short}` 或 `{pause:long}` 标记停顿，使用 `**文字**` 标记强调。Fish Audio 输出 S2-Pro 的方括号控制提示；其它 Provider 使用普通中文标点和引号。产品专名或缩写读法不合适时，先更新 `config/zh-voice.json`，再生成音频，不能在生成后用文件名掩盖错误读法。
