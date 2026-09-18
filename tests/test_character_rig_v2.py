import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.build_character_rig_v2 import RigV2Error, build_rig_v2, template
from scripts.godot_rig_readiness import assess_rig
from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository


class CharacterRigV2Tests(unittest.TestCase):
    def make_project(self, root: Path) -> tuple[Path, NovelAnimeRepository]:
        project = root / "jinghua-yuan-series"
        write_project(project, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
        repository = NovelAnimeRepository(project)
        repository.initialize()
        source = project / "assets/characters/CHR-JHY-BAIHUA/source.png"
        source.parent.mkdir(parents=True)
        Image.new("RGBA", (96, 128), (255, 255, 255, 255)).save(source)
        repository.register_asset(
            "AST-CHR-JHY-BAIHUA-FRONT",
            "character",
            source,
            source_entity_ids=["S01E001"],
        )
        return project, repository

    def test_upper_body_v2_builds_registered_ik_ready_rig(self):
        with tempfile.TemporaryDirectory() as directory:
            project, repository = self.make_project(Path(directory))
            spec = template(
                "CHR-JHY-BAIHUA",
                "RIG2-CHR-JHY-BAIHUA-UPPER-V1",
                "GODOT_UPPER_BODY_IK",
                "百花仙子",
            )
            spec["source_asset_id"] = "AST-CHR-JHY-BAIHUA-FRONT"
            for index, layer in enumerate(spec["layers"]):
                path = project / f"assets/characters/CHR-JHY-BAIHUA/rig-v2/{layer['name']}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (96, 128), (255, 255, 255, 0)).save(path)
                image = Image.open(path)
                image.putpixel((20 + index, 20), (255, 0, 0, 255))
                image.save(path)
                layer["path"] = path.relative_to(project).as_posix()
                layer["pivot"] = {"x": 48, "y": 64}

            result = build_rig_v2(project, spec)
            rig = result["rig"]
            readiness = assess_rig(rig)
            self.assertEqual(rig["rig_version"], 2)
            self.assertTrue(readiness["profiles"]["GODOT_UPPER_BODY_IK"]["ready"])
            self.assertIn("left_arm", rig["joint_chains"])
            self.assertGreater(repository.stats()["asset_versions"], 1)

    def test_missing_required_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _ = self.make_project(Path(directory))
            spec = template("CHR-1", "RIG-1", "GODOT_UPPER_BODY_IK")
            spec["source_asset_id"] = "AST-1"
            spec["layers"].pop()
            with self.assertRaisesRegex(RigV2Error, "missing layers"):
                build_rig_v2(project, spec)


if __name__ == "__main__":
    unittest.main()
