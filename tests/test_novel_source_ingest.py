import json
import tempfile
import unittest
from pathlib import Path

from adapters.story_extraction import ChapterText, LocalLexiconExtractor
from scripts.novel_anime_project import build_project, load_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_source_catalog import build_catalog, load_catalog, write_catalog
from scripts.novel_source_ingest import NovelSourceIngestError, ingest_source, split_chapters


class NovelSourceIngestTests(unittest.TestCase):
    def make_project(self, root: Path, *, authorized: bool) -> tuple[Path, Path, Path]:
        project_dir = root / "jinghua-yuan-series"
        write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
        catalog = build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘")
        rights_status = "LICENSED" if authorized else "UNASSESSED"
        catalog["editions"] = [{
            "id": "SRC-JHY-001", "title": "镜花缘测试底本", "edition_label": "测试底本",
            "author": "测试作者", "language": "zh-CN", "publication_year": None, "publisher": None,
            "source_url": "https://example.org/jhy", "file_checksum": None,
            "rights_status": rights_status, "chapter_ids": [],
            "modern_contributions": [{"type": "annotation", "rights_status": "EXCLUDED", "note": "不使用"}],
        }]
        if authorized:
            catalog["status"] = "LICENSED"
            catalog["rights_assessment"].update({
                "status": "LICENSED", "basis": "test license", "jurisdictions": ["test"], "territories": ["CN"],
                "evidence": [{"id": "EVD-JHY-001", "type": "license", "title": "test license", "url": "https://example.org/license", "accessed_at": "2026-09-16", "note": "test fixture"}],
                "publication_allowed": True,
                "human_review": {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test fixture"},
            })
            catalog["adaptation_policy"].update({"script_adaptation_allowed": True, "publication_allowed": True})
        write_catalog(project_dir, catalog)
        NovelAnimeRepository(project_dir).initialize()
        source = root / "source.txt"
        source.write_text("第1回 初见\n唐小山在船舱发现罗盘。\n她决定离开船舱。\n第2回 出海\n唐小山带着罗盘抵达海港。\n", encoding="utf-8")
        lexicon = root / "lexicon.json"
        lexicon.write_text(json.dumps({
            "characters": [{"id": "CHR-TXS", "name": "唐小山", "aliases": []}],
            "locations": [{"id": "LOCN-CABIN", "name": "船舱", "aliases": []}, {"id": "LOCN-HARBOR", "name": "海港", "aliases": []}],
            "props": [{"id": "PROP-COMPASS", "name": "罗盘", "aliases": []}],
        }, ensure_ascii=False), encoding="utf-8")
        return project_dir, source, lexicon

    def test_chapter_split_supports_chinese_and_numeric_headings(self):
        chapters = split_chapters("第一回 开端\n正文一。\n第2回 转折\n正文二。", "JHY")
        self.assertEqual([chapter.title for chapter in chapters], ["第一回 开端", "第2回 转折"])
        self.assertEqual([chapter.chapter_id for chapter in chapters], ["CH-JHY-0001", "CH-JHY-0002"])
        self.assertEqual([(chapter.line_start, chapter.line_end) for chapter in chapters], [(2, 2), (4, 4)])

    def test_authorized_import_updates_catalog_manifest_and_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, source, lexicon = self.make_project(Path(directory), authorized=True)
            result = ingest_source(project_dir, "SRC-JHY-001", source, lexicon_file=lexicon, authorization_confirmed=True)
            artifact = json.loads((project_dir / result["output"]).read_text(encoding="utf-8"))
            catalog = load_catalog(project_dir / "sources" / "source-catalog.json")
            project = load_project(project_dir / "novel-anime-project.json")
            repository = NovelAnimeRepository(project_dir)
            stats = repository.stats()
        self.assertEqual(result["chapter_count"], 2)
        self.assertEqual(catalog["editions"][0]["chapter_ids"], ["CH-JHY-0001", "CH-JHY-0002"])
        self.assertEqual(project["ip"]["source_edition_ids"], ["SRC-JHY-001"])
        self.assertEqual(stats["entities"], 9)
        self.assertFalse(artifact["full_text_stored"])
        self.assertNotIn("唐小山决定离开船舱", json.dumps(artifact, ensure_ascii=False))
        self.assertGreaterEqual(result["event_candidates"], 2)

    def test_import_requires_explicit_authorization_and_verified_edition(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, source, lexicon = self.make_project(Path(directory), authorized=True)
            with self.assertRaisesRegex(NovelSourceIngestError, "authorization_confirmed"):
                ingest_source(project_dir, "SRC-JHY-001", source, lexicon_file=lexicon)
        with tempfile.TemporaryDirectory() as directory:
            project_dir, source, lexicon = self.make_project(Path(directory), authorized=False)
            with self.assertRaisesRegex(NovelSourceIngestError, "not verified"):
                ingest_source(project_dir, "SRC-JHY-001", source, lexicon_file=lexicon, authorization_confirmed=True)

    def test_test_only_import_does_not_modify_catalog_or_core_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, source, lexicon = self.make_project(Path(directory), authorized=False)
            result = ingest_source(project_dir, "SRC-JHY-001", source, lexicon_file=lexicon, test_only=True)
            catalog = load_catalog(project_dir / "sources" / "source-catalog.json")
            project = load_project(project_dir / "novel-anime-project.json")
        self.assertTrue(result["test_only"])
        self.assertEqual(catalog["chapters"], [])
        self.assertEqual(project["source_editions"], [])

    def test_extractor_stores_hashes_and_review_candidates_without_sentences(self):
        result = LocalLexiconExtractor().extract(
            (ChapterText("CH-JHY-0001", "第一回", "唐小山发现罗盘，决定离开船舱。", 1, 1),),
            {"characters": [{"id": "CHR-TXS", "name": "唐小山", "aliases": []}], "locations": [{"id": "LOCN-CABIN", "name": "船舱", "aliases": []}], "props": [{"id": "PROP-COMPASS", "name": "罗盘", "aliases": []}]},
        )
        self.assertEqual(result.characters[0]["total_mentions"], 1)
        self.assertTrue(result.events[0]["needs_review"])
        self.assertEqual(len(result.events[0]["sentence_sha256"]), 64)
        self.assertNotIn("sentence", result.events[0])


if __name__ == "__main__":
    unittest.main()
