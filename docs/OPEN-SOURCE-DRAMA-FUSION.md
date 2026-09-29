# Open-Source Drama Fusion

VideoCreator Engine remains the only orchestrator. The goal is not to chain seven complete applications together. Each production stage has one owner, while external projects contribute a method, a contract, or an optional provider.

## Selected ideas

| Stage | Primary implementation | External source used for |
|---|---|---|
| Script | Writing Room / Episode Script | `0xsline/short-drama`: episode hooks, self-check, short-drama writing discipline |
| Character lock | Character Design + Modern Asset Library | internal contract; external tools do not own identity |
| Storyboard | Shot Breakdown + Storyboard | `Seedance2-Storyboard-Generator`: structured shot language |
| Director / state | VideoCreator state machine | `short-drama-production`: approval-before-batch and director-stage separation |
| Voice timing | Voice First | internal; no ASR round-trip |
| Final voice | TTS Router | `GPT-SoVITS` as optional local voice-clone provider |
| Subtitles | SRT/ASS from approved voice timing | `VideoCaptioner` only as optional alignment/QC fallback |
| Video | Cost Router | `Wan2.2` as optional provider on capable GPU hardware |
| Editable project | Modern Editable Timeline | `moyin-creator`: multi-track and local regeneration product ideas |
| Final publish | Human | unchanged |

Pinned source commits are stored in `config/open-source-fusion.json`. They are references, not automatically installed dependencies.

## Hard production rule

Expensive or long-running AI video is not allowed to be the first place where identity or framing is discovered.

```text
Script
→ Character Lock
→ Character assets APPROVED
→ Shot contract
→ Storyboard / keyframe APPROVED
→ Cost Router
→ Local renderer when possible
→ AI video only for the unresolved motion gap
→ QC
→ Human review
```

For modern drama the first quality gate is deliberately small: 30–45 seconds, 2 characters, 2 locations, 8–12 shots. It must prove identity continuity, scene continuity, eyelines/blocking and editorial rhythm before a 2–3 minute episode is attempted.

## Mac policy

The current Apple M5 / 16 GB machine is the orchestration, image, audio, local motion, FFmpeg and QC host. It is not the default host for a full Wan 2.2 production model. Wan 2.2 remains an optional provider for a separate suitable GPU host. This avoids turning a low-cost workflow into a model-installation project.

## Voice policy

Kokoro remains the zero-cost default. GPT-SoVITS is added only for characters that benefit from a locked cloned voice. Its local adapter talks to a user-started loopback GPT-SoVITS API; VideoCreator does not auto-start or auto-download the model.

## Subtitle policy

Because the pipeline already knows the final script and approved voice timing, SRT/ASS generation stays deterministic. VideoCaptioner is useful when imported live footage needs transcription/alignment or when subtitle timing needs an independent QC pass. It is not placed in the default path.

## Why this is faster

The system avoids three common sources of wasted time:

1. tool-to-tool media搬运;
2. regenerating whole episodes for one bad shot;
3. paying a video model to discover a face, costume, composition or camera plan that should have been approved as a still.
