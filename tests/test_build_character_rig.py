import tempfile
import unittest
import json
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.build_character_rig import build_rig, validate_rig
from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository


class CharacterRigTests(unittest.TestCase):
    def test_build_rig_preserves_alignment_and_registers_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "jinghua-yuan-series"
            write_project(project, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
            repository = NovelAnimeRepository(project)
            repository.initialize()
            source = project / "assets" / "characters" / "CHR-JHY-BAIHUA" / "source.png"
            source.parent.mkdir(parents=True)
            image = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 10, 80, 110), fill=(240, 120, 120, 255))
            image.save(source)
            repository.register_asset("AST-CHR-JHY-BAIHUA-FRONT", "character", source, source_entity_ids=["S01E001"])
            result = build_rig(project, source, "AST-CHR-JHY-BAIHUA-FRONT", "CHR-JHY-BAIHUA", "RIG-CHR-JHY-BAIHUA-FRONT-V1")
            self.assertEqual(len(result["rig"]["layers"]), 4)
            self.assertTrue(validate_rig(project, result["rig"])["valid"])
            with Image.open(project / "assets/characters/CHR-JHY-BAIHUA/rig-v1/head.png") as head:
                self.assertEqual(head.size, (100, 120))
            self.assertEqual(repository.stats()["asset_versions"], 5)

    def test_build_rig_keeps_existing_character_rigs(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "jinghua-yuan-series"
            write_project(project, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
            repository = NovelAnimeRepository(project)
            repository.initialize()
            for character_id, source_id in (
                ("CHR-JHY-BAIHUA", "AST-CHR-JHY-BAIHUA-FRONT"),
                ("CHR-JHY-WUZETIAN", "AST-CHR-JHY-WUZETIAN-FRONT"),
            ):
                source = project / "assets" / "characters" / character_id / "source.png"
                source.parent.mkdir(parents=True)
                Image.new("RGBA", (100, 120), (240, 120, 120, 255)).save(source)
                repository.register_asset(source_id, "character", source, source_entity_ids=["S01E001"])
                build_rig(
                    project,
                    source,
                    source_id,
                    character_id,
                    f"RIG-{character_id}-FRONT-V1",
                    "武则天" if character_id.endswith("WUZETIAN") else "百花仙子",
                )

            manifest = json.loads((project / "visual-bible" / "character-rigs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["rigs"]), 2)
            self.assertEqual(manifest["revision"], 2)
            wuzetian = next(item for item in manifest["rigs"] if item["character_id"] == "CHR-JHY-WUZETIAN")
            self.assertEqual(wuzetian["character_name"], "武则天")
            self.assertEqual(wuzetian["layers"][0]["asset_id"], "AST-RIG-JHY-WUZETIAN-FRONT-FULL")


if __name__ == "__main__":
    unittest.main()
