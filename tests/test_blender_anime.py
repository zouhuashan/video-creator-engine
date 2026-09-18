import tempfile
import unittest
from pathlib import Path

from adapters.motion.blender_anime import (
    BlenderAnimeError,
    parse_version,
    smoke_command,
)


class BlenderAnimeAdapterTests(unittest.TestCase):
    def test_parse_blender_lts_version(self):
        version = parse_version("Blender 5.2.2")
        self.assertEqual(version.tuple, (5, 2, 2))
        self.assertTrue(version.stable)

    def test_parse_prerelease_marker(self):
        version = parse_version("Blender 5.2.0 Beta")
        self.assertFalse(version.stable)

    def test_smoke_command_is_arm64_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "smoke.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            output = root / "smoke.png"
            command = smoke_command(script, output, "/Applications/Blender.app/Contents/MacOS/Blender")
            self.assertEqual(command[:2], ["/usr/bin/arch", "-arm64"])
            self.assertIn("--background", command)
            self.assertIn("--factory-startup", command)
            self.assertIn(str(script), command)
            self.assertIn(str(output), command)

    def test_smoke_command_requires_script(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(BlenderAnimeError, "missing Blender smoke script"):
                smoke_command(Path(directory) / "missing.py", Path(directory) / "out.png", "/tmp/blender")


if __name__ == "__main__":
    unittest.main()
