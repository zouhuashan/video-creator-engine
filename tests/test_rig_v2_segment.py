import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.rig_v2_segment import RigV2SegmentError, segment_layers


class RigV2SegmentTests(unittest.TestCase):
    def make_project(self, root: Path):
        project = root / "jinghua-yuan-series"
        write_project(project, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
        repo = NovelAnimeRepository(project)
        repo.initialize()
        source = project / "assets/characters/CHR-JHY-BAIHUA/front.png"
        source.parent.mkdir(parents=True)
        image = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((10, 5, 90, 115), fill=(230, 140, 160, 255))
        image.save(source)
        repo.register_asset("AST-CHR-JHY-BAIHUA-FRONT", "character", source, source_entity_ids=["S01E001"])
        return project, source

    def test_upper_body_polygons_generate_real_transparent_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            project, source = self.make_project(Path(directory))
            names = ("head", "torso", "upper_arm_l", "forearm_l", "hand_l", "upper_arm_r", "forearm_r", "hand_r")
            layers = {
                name: {
                    "polygon": [[10, 5], [90, 5], [90, 115], [10, 115]],
                    "pivot": {"x": 50, "y": 60},
                    "z_index": index,
                }
                for index, name in enumerate(names)
            }
            result = segment_layers(
                project,
                source.relative_to(project).as_posix(),
                "CHR-JHY-BAIHUA",
                "百花仙子",
                "AST-CHR-JHY-BAIHUA-FRONT",
                "RIG2-CHR-JHY-BAIHUA-UPPER-V1",
                "GODOT_UPPER_BODY_IK",
                layers,
            )
            self.assertTrue(result["finalized"])
            self.assertEqual(len(result["layers"]), 8)
            for layer in result["layers"]:
                path = project / layer["path"]
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertIsNotNone(image.getchannel("A").getbbox())

    def test_polygon_must_have_three_points(self):
        with tempfile.TemporaryDirectory() as directory:
            project, source = self.make_project(Path(directory))
            names = ("head", "torso", "upper_arm_l", "forearm_l", "hand_l", "upper_arm_r", "forearm_r", "hand_r")
            layers = {
                name: {
                    "polygon": [[10, 5], [90, 5], [90, 115], [10, 115]],
                    "pivot": {"x": 50, "y": 60},
                }
                for name in names
            }
            layers["head"]["polygon"] = [[1, 1], [2, 2]]
            with self.assertRaisesRegex(RigV2SegmentError, "at least 3 polygon"):
                segment_layers(
                    project,
                    source.relative_to(project).as_posix(),
                    "CHR-JHY-BAIHUA",
                    "百花仙子",
                    "AST-CHR-JHY-BAIHUA-FRONT",
                    "RIG2-TEST",
                    "GODOT_UPPER_BODY_IK",
                    layers,
                )


if __name__ == "__main__":
    unittest.main()
