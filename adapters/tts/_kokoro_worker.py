"""Isolated sherpa-onnx worker for :mod:`adapters.tts.kokoro_sherpa`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def validate_speech_samples(samples, sample_rate):
    """Reject silent or missing openings; this is not a transcription check."""
    first = next((i for i, value in enumerate(samples) if abs(value) > .003), None)
    if first is None:
        raise ValueError("generated speech is silent")
    if first / sample_rate > .75:
        raise ValueError("generated speech has a silent opening; check for omitted words")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sid", type=int, required=True)
    parser.add_argument("--speed", type=float, required=True)
    parser.add_argument("--num-threads", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import sherpa_onnx
    except (ImportError, OSError) as error:
        print(f"sherpa-onnx runtime could not be loaded: {error}", file=sys.stderr)
        return 2

    text = sys.stdin.buffer.read().decode("utf-8").strip()
    if not text:
        print("input text is empty", file=sys.stderr)
        return 2

    root = args.model_dir.resolve()
    kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
        model=str(root / "model.int8.onnx"),
        voices=str(root / "voices.bin"),
        tokens=str(root / "tokens.txt"),
        data_dir=str(root / "espeak-ng-data"),
        lexicon=f"{root / 'lexicon-us-en.txt'},{root / 'lexicon-zh.txt'}",
    )
    model = sherpa_onnx.OfflineTtsModelConfig(
        kokoro=kokoro,
        num_threads=args.num_threads,
        debug=False,
        provider="cpu",
    )
    config = sherpa_onnx.OfflineTtsConfig(
        model=model,
        rule_fsts=",".join(
            str(root / name) for name in ("phone-zh.fst", "date-zh.fst", "number-zh.fst")
        ),
        max_num_sentences=1,
    )
    if not config.validate():
        print("sherpa-onnx rejected the Kokoro model configuration", file=sys.stderr)
        return 2

    try:
        tts = sherpa_onnx.OfflineTts(config)
        if not 0 <= args.sid < tts.num_speakers:
            print(
                f"speaker id {args.sid} is outside the installed model range 0..{tts.num_speakers - 1}",
                file=sys.stderr,
            )
            return 2
        audio = tts.generate(text, sid=args.sid, speed=args.speed)
        if len(audio.samples) == 0 or audio.sample_rate <= 0:
            print("sherpa-onnx generated empty audio", file=sys.stderr)
            return 2
        validate_speech_samples(audio.samples, audio.sample_rate)
        if not sherpa_onnx.write_wave(str(args.output), audio.samples, audio.sample_rate):
            print("sherpa-onnx could not write the WAV output", file=sys.stderr)
            return 2
    except Exception as error:
        print(f"Kokoro generation error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
