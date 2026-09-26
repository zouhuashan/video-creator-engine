import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.modern_asset_library import ModernAssetLibraryError, load_library, register_asset
from scripts.render_screen_mg import render_screen_mg
from scripts.render_stock_broll import render_stock_broll
from scripts.render_layered_25d import render_layered_25d


class ModernAssetAndScreenMGTest(unittest.TestCase):
    def test_reusable_asset_replaces_variant_without_duplicating_file(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            image = Image.new("RGB", (32, 32), "#557799")
            output = io.BytesIO()
            image.save(output, format="PNG")
            first = register_asset(project, kind="character", entity_id="HERO", variant="front", expression="neutral", extension=".png", content=output.getvalue())
            second = register_asset(project, kind="character", entity_id="HERO", variant="front", expression="neutral", extension=".png", content=output.getvalue())
            self.assertEqual(first["path"], second["path"])
            self.assertEqual(len(load_library(project)["assets"]), 1)
            with self.assertRaises(ModernAssetLibraryError):
                register_asset(project, kind="character", entity_id="../bad", variant="front", extension=".png", content=output.getvalue())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_screen_mg_creates_local_video(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            result = render_screen_mg(project, shot_id="SHOT-DEMO-001", kind="chat", title="消息", lines=["合同已送达", "马上到"], duration_seconds=1)
            output = project / result["output"]
            self.assertEqual(result["renderer"], "local_screen_mg")
            self.assertEqual(result["duration_seconds"], 1)
            self.assertGreater(output.stat().st_size, 5000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_rights_declared_stock_can_be_trimmed_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "source.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1", "-c:v", "libx264", str(source)], check=True)
            with self.assertRaises(ModernAssetLibraryError):
                register_asset(project, kind="stock", entity_id="CITY", variant="night", extension=".mp4", content=source.read_bytes())
            item = register_asset(project, kind="stock", entity_id="CITY", variant="night", extension=".mp4", content=source.read_bytes(), license_note="owned")
            result = render_stock_broll(project, shot_id="SHOT-CITY-001", asset_path=item["path"], duration_seconds=2)
            self.assertEqual(result["renderer"], "stock_broll_library")
            self.assertGreater((project / result["output"]).stat().st_size, 2000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_layered_renderer_uses_separate_transparent_character(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            background = project / "background.png"
            character = project / "character.png"
            Image.new("RGB", (320, 480), "#26485a").save(background)
            foreground = Image.new("RGBA", (140, 260), (0, 0, 0, 0))
            from PIL import ImageDraw
            ImageDraw.Draw(foreground).ellipse((25, 10, 115, 220), fill="#e1b1a1")
            foreground.save(character)
            result = render_layered_25d(project, shot_id="SHOT-LAYER-001", background=background, character=character, duration_seconds=1)
            self.assertEqual(result["renderer"], "local_layered_25d")
            self.assertGreater((project / result["output"]).stat().st_size, 2000)


if __name__ == "__main__":
    unittest.main()
