# Local Kokoro TTS

`KokoroSherpaTTS` generates Chinese or Chinese/English speech locally with the
Kokoro v1.1 int8 model and sherpa-onnx. It needs no API key and marks every
result as non-billable.

The default paths are configured in `config/providers.yaml`:

- runtime: `.dependencies/kokoro-runtime`
- model: `.dependencies/models/kokoro-int8-multi-lang-v1_1`
- compatible interpreter: `.dependencies/python-bin/python3.13`
- default voice: `zm_010` (speaker 59)

The adapter deliberately starts an isolated worker because the application may
run on Python 3.10 while the local sherpa-onnx extension uses the Python 3.13
ABI. Paths can be replaced through the adapter constructor, so the model and
runtime remain optional dependencies. Missing files produce a configuration
error; the adapter never downloads or installs anything automatically.

Use an official voice ID such as `zm_010`, `zm_012`, `zf_001`, or `zf_002`.
Convenience aliases include `male_narrator`, `female_narrator`, `男旁白`, and
`女旁白`. Kokoro does not expose reliable emotion controls through this local
runtime, so requests with `emotion` are rejected instead of being silently
ignored.
