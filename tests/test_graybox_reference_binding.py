import json
import tempfile
import unittest
from pathlib import Path

import scripts.graybox_reference_binding as refs


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


class GrayboxReferenceBindingTests(unittest.TestCase):
    def _image(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG_1X1)
        return path

    def _character_artifact(self, project: Path):
        image = self._image(project / "lookdev" / "image-studio" / "character-bible" / "hero.png")
        metadata = image.with_suffix(".json")
        metadata.write_text(json.dumps({
            "artifact_type": "character_bible",
            "output": image.relative_to(project).as_posix(),
            "character_id": "CHAR-001",
            "review_status": "APPROVED",
            "style_label": "参考视频·电影级 3D 国漫",
            "created_at": "2026-09-22T00:00:00Z",
        }, ensure_ascii=False), encoding="utf-8")
        return image

    def test_character_reference_can_only_bind_inventory_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            image = self._character_artifact(project)
            candidates = refs.character_candidates(project)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["review_status"], "APPROVED")

            binding = refs.bind_reference(
                project,
                kind="character",
                relative_path=image.relative_to(project).as_posix(),
            )
            self.assertEqual(binding["character_reference"]["character_id"], "CHAR-001")
            self.assertTrue(refs.binding_path(project).is_file())

            rogue = self._image(project / "rogue.png")
            with self.assertRaisesRegex(refs.GrayboxReferenceError, "not in the current project inventory"):
                refs.bind_reference(project, kind="character", relative_path=rogue.relative_to(project).as_posix())

    def test_scene_upload_is_saved_and_can_be_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            uploaded = refs.upload_scene_reference(
                project,
                filename="古宅 门楼.png",
                content=PNG_1X1,
            )
            self.assertTrue((project / uploaded["path"]).is_file())
            binding = refs.bind_reference(project, kind="scene", relative_path=uploaded["path"])
            self.assertEqual(binding["scene_reference"]["source"], "scene_upload")

    def test_invalid_scene_upload_is_rejected_and_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with self.assertRaisesRegex(refs.GrayboxReferenceError, "not a valid image"):
                refs.upload_scene_reference(project, filename="bad.png", content=b"not-an-image")
            scene_root = project / "graybox" / "references" / "scenes"
            self.assertFalse(scene_root.exists() and any(scene_root.iterdir()))

    def test_packaged_smoke_reference_pack_installs_and_binds_both_images(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            result = refs.install_smoke_reference_pack(project)
            self.assertEqual(result["status"], "INSTALLED_AND_BOUND")
            self.assertTrue((project / result["character_reference"]).is_file())
            self.assertTrue((project / result["scene_reference"]).is_file())
            inventory = refs.inventory(project)
            self.assertTrue(inventory["ready"])
            self.assertEqual(
                inventory["binding"]["character_reference"]["source"],
                "image_studio_character",
            )
            self.assertEqual(
                inventory["binding"]["scene_reference"]["source"],
                "scene_upload",
            )

    def test_complete_binding_resolves_character_then_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            character = self._character_artifact(project)
            scene = refs.upload_scene_reference(project, filename="gate.png", content=PNG_1X1)
            refs.bind_reference(project, kind="character", relative_path=character.relative_to(project).as_posix())
            refs.bind_reference(project, kind="scene", relative_path=scene["path"])

            character_path, scene_path, binding = refs.resolve_bound_paths(project, require_complete=True)
            self.assertEqual(character_path, character.resolve())
            self.assertEqual(scene_path, (project / scene["path"]).resolve())
            self.assertEqual(binding["shot_spec_id"], refs.DEFAULT_SPEC_ID)
            inventory = refs.inventory(project)
            self.assertTrue(inventory["ready"])
            self.assertTrue(inventory["character_bound"])
            self.assertTrue(inventory["scene_bound"])

    def test_incomplete_binding_blocks_final_reference_package(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._character_artifact(project)
            with self.assertRaisesRegex(refs.GrayboxReferenceError, "人物参考、场景参考"):
                refs.resolve_bound_paths(project, require_complete=True)


if __name__ == "__main__":
    unittest.main()
