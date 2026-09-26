import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.tts import (
    KokoroSherpaTTS,
    TTSProviderError,
    choose_provider,
    normalize_chinese_punctuation,
    resolve_kokoro_voice,
)


class KokoroSherpaTTSTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        (self.runtime / "sherpa_onnx").mkdir(parents=True)
        (self.runtime / "sherpa_onnx" / "__init__.py").write_text("", encoding="utf-8")
        self.model = self.root / "model"
        self.model.mkdir()
        for name in (
            "model.int8.onnx",
            "voices.bin",
            "tokens.txt",
            "lexicon-us-en.txt",
            "lexicon-zh.txt",
            "phone-zh.fst",
            "date-zh.fst",
            "number-zh.fst",
        ):
            (self.model / name).write_bytes(b"fixture")
        self.python = self.root / "python3.13"
        self.python.write_bytes(b"fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def test_maps_official_voice_ids_and_aliases(self):
        self.assertEqual(resolve_kokoro_voice("zm_010"), ("zm_010", 59))
        self.assertEqual(resolve_kokoro_voice("zf_001"), ("zf_001", 3))
        self.assertEqual(resolve_kokoro_voice("男旁白"), ("zm_010", 59))
        with self.assertRaisesRegex(TTSProviderError, "unsupported Kokoro voice_id"):
            resolve_kokoro_voice("zm_001")

    def test_local_kokoro_has_priority_when_it_is_available(self):
        self.assertEqual(
            choose_provider({"kokoro_local": True, "fish_audio": True}),
            "kokoro_local",
        )

    def test_normalizes_chinese_punctuation_without_breaking_decimals(self):
        self.assertEqual(
            normalize_chinese_punctuation("  温度3.5度, 真的...?\n是的!!  "),
            "温度3.5度，真的……？是的！",
        )

    def test_synthesizes_non_billable_wav_with_isolated_runtime(self):
        captured = {}

        def runner(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(b"RIFF-local-kokoro-wav")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        result = KokoroSherpaTTS(
            runtime_dir=self.runtime,
            model_dir=self.model,
            python_executable=self.python,
            runner=runner,
            environment={"EXISTING": "1"},
        ).synthesize("这盏灯,为什么没有影子?", "zm_010", speed=1.05)

        self.assertEqual(result.provider, "kokoro_local")
        self.assertEqual(result.voice, "zm_010")
        self.assertEqual(result.audio_format, "wav")
        self.assertFalse(result.billable_generation)
        self.assertEqual(captured["kwargs"]["input"].decode(), "这盏灯，为什么没有影子？")
        self.assertEqual(captured["command"][captured["command"].index("--sid") + 1], "59")
        self.assertTrue(
            captured["kwargs"]["env"]["PYTHONPATH"].startswith(str(self.runtime.resolve()))
        )

    def test_reports_missing_runtime_and_unsupported_emotion(self):
        provider = KokoroSherpaTTS(
            runtime_dir=self.root / "missing",
            model_dir=self.model,
            python_executable=self.python,
        )
        with self.assertRaisesRegex(TTSProviderError, "sherpa-onnx was not found"):
            provider.synthesize("测试。", "zm_010")

        provider = KokoroSherpaTTS(
            runtime_dir=self.runtime,
            model_dir=self.model,
            python_executable=self.python,
        )
        with self.assertRaisesRegex(TTSProviderError, "does not support emotion"):
            provider.synthesize("测试。", "zm_010", emotion="calm")


if __name__ == "__main__":
    unittest.main()
