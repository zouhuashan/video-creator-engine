import subprocess
import unittest
from pathlib import Path

from adapters.tts import MacOSSayTTS, TTSProviderError


class MacOSSayTTSTests(unittest.TestCase):
    @staticmethod
    def successful_runner(command, **kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"FORM-aiff-audio")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def test_synthesizes_non_billable_aiff_without_shell(self):
        provider = MacOSSayTTS(runner=self.successful_runner)
        result = provider.synthesize("本地配音。", "Tingting", 1.1)
        self.assertEqual(result.provider, "macos_say")
        self.assertEqual(result.audio_format, "aiff")
        self.assertFalse(result.billable_generation)
        self.assertTrue(result.audio)

    def test_rejects_unsupported_emotion_and_failed_process(self):
        provider = MacOSSayTTS(runner=self.successful_runner)
        with self.assertRaisesRegex(TTSProviderError, "does not support emotion"):
            provider.synthesize("文本", "Tingting", emotion="happy")

        provider = MacOSSayTTS(
            runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 1, b"", b"failed")
        )
        with self.assertRaisesRegex(TTSProviderError, "synthesis failed"):
            provider.synthesize("文本", "Tingting")


if __name__ == "__main__":
    unittest.main()
