import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository, NovelAnimeRepositoryError, repository_stats


class NovelAnimeRepositoryTests(unittest.TestCase):
    def make_repository(self, root: Path) -> NovelAnimeRepository:
        project_dir = root / "jinghua-yuan-series"
        write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
        repository = NovelAnimeRepository(project_dir)
        repository.initialize()
        return repository

    def test_initializes_entities_and_hierarchy_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))
            self.assertEqual(repository.stats(), {"entities": 8, "dependencies": 7, "asset_versions": 0, "snapshots": 0})
            self.assertEqual(repository_stats(repository.project_dir), repository.stats())

    def test_impact_walks_from_ip_to_all_five_episodes(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))
            impact = repository.impact(["IP-JHY"])
        self.assertEqual([item["entity_id"] for item in impact[:2]], ["SER-JHY-01", "S01"])
        self.assertEqual({item["entity_id"] for item in impact if item["entity_type"] == "episode"}, {f"S01E{index:03d}" for index in range(1, 6)})
        self.assertTrue(all(item["depth"] == 3 for item in impact if item["entity_type"] == "episode"))

    def test_asset_registry_keeps_versions_checksums_and_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))
            asset_path = repository.project_dir / "assets" / "characters" / "tang-xiaoshan.png"
            asset_path.parent.mkdir(parents=True)
            asset_path.write_bytes(b"version-one")
            first = repository.register_asset("AST-CHR-TXS-PORTRAIT", "character", asset_path, source_entity_ids=["S01E001"])
            asset_path.write_bytes(b"version-two")
            second = repository.register_asset("AST-CHR-TXS-PORTRAIT", "character", asset_path, source_entity_ids=["S01E001"])
            impact = repository.impact(["S01E001"])
            stats = repository.stats()
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertNotEqual(first["checksum"], second["checksum"])
        self.assertEqual(stats["asset_versions"], 2)
        self.assertIn("AST-CHR-TXS-PORTRAIT", {item["entity_id"] for item in impact})

    def test_asset_must_be_inside_project_and_sources_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.make_repository(root)
            outside = root / "outside.png"
            outside.write_bytes(b"image")
            with self.assertRaisesRegex(NovelAnimeRepositoryError, "inside the project"):
                repository.register_asset("AST-CHR-TXS-PORTRAIT", "character", outside)
            inside = repository.project_dir / "inside.png"
            inside.write_bytes(b"image")
            with self.assertRaisesRegex(NovelAnimeRepositoryError, "registered entities"):
                repository.register_asset("AST-CHR-TXS-PORTRAIT", "character", inside, source_entity_ids=["S01E999"])

    def test_snapshot_contains_project_assets_and_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))
            snapshot = repository.create_snapshot("core model ready")
            path = repository.project_dir / snapshot["relative_path"]
            payload = json.loads(path.read_text(encoding="utf-8"))
            stats = repository.stats()
        self.assertEqual(payload["project"]["project_id"], "jinghua-yuan-series")
        self.assertEqual(len(payload["dependencies"]), 7)
        self.assertEqual(stats["snapshots"], 1)
        self.assertEqual(len(snapshot["manifest_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
