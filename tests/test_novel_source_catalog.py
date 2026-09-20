import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_source_catalog import (
    NovelSourceCatalogError,
    build_catalog,
    load_catalog,
    validate_catalog,
    write_catalog,
)


class NovelSourceCatalogTests(unittest.TestCase):
    def catalog_with_edition(self):
        catalog = build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘")
        catalog["editions"] = [{
            "id": "SRC-JHY-001",
            "title": "镜花缘",
            "edition_label": "待核验历史底本",
            "author": "李汝珍",
            "language": "zh-Hant",
            "publication_year": None,
            "publisher": None,
            "source_url": "https://example.org/catalog/jinghua-yuan",
            "file_checksum": None,
            "rights_status": "UNASSESSED",
            "chapter_ids": ["CH-JHY-0001"],
            "modern_contributions": [
                {"type": "annotation", "rights_status": "EXCLUDED", "note": "不使用现代注释"},
                {"type": "illustration", "rights_status": "EXCLUDED", "note": "不使用现代插图"},
            ],
        }]
        catalog["chapters"] = [{
            "id": "CH-JHY-0001", "edition_id": "SRC-JHY-001", "sequence": 1,
            "title": "第一回", "volume": "卷一", "locator_ids": ["LOC-JHY-0001"],
        }]
        catalog["locators"] = [{
            "id": "LOC-JHY-0001", "chapter_id": "CH-JHY-0001",
            "source_url": "https://example.org/catalog/jinghua-yuan#chapter-1",
            "location": {"page_start": 1, "page_end": 8, "paragraph_start": None, "paragraph_end": None, "label": "卷一第一回"},
            "excerpt_sha256": None, "text_storage_allowed": False,
        }]
        return catalog

    def test_new_catalog_is_local_test_only_and_not_publishable(self):
        catalog = build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘")
        self.assertEqual(catalog["rights_assessment"]["status"], "UNASSESSED")
        self.assertTrue(catalog["adaptation_policy"]["local_technical_test_allowed"])
        self.assertFalse(catalog["adaptation_policy"]["script_adaptation_allowed"])
        self.assertFalse(catalog["adaptation_policy"]["publication_allowed"])

    def test_edition_chapter_and_locator_are_bidirectionally_linked(self):
        catalog = validate_catalog(self.catalog_with_edition())
        self.assertEqual(catalog["editions"][0]["chapter_ids"], ["CH-JHY-0001"])
        self.assertEqual(catalog["chapters"][0]["locator_ids"], ["LOC-JHY-0001"])
        broken = self.catalog_with_edition()
        broken["editions"][0]["chapter_ids"] = []
        with self.assertRaisesRegex(NovelSourceCatalogError, "must match its chapter records"):
            validate_catalog(broken)

    def test_publication_gate_requires_evidence_regions_and_human_approval(self):
        catalog = self.catalog_with_edition()
        catalog["status"] = "PUBLIC_DOMAIN_VERIFIED"
        catalog["rights_assessment"].update({
            "status": "PUBLIC_DOMAIN_VERIFIED", "basis": "test evidence set",
            "jurisdictions": ["CN copyright term"], "territories": ["CN"],
            "publication_allowed": True,
            "human_review": {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test only"},
            "evidence": [{"id": "EVD-JHY-001", "type": "institution_catalog", "title": "catalog", "url": "https://example.org/evidence", "accessed_at": "2026-09-16", "note": "test fixture"}],
        })
        catalog["adaptation_policy"].update({"script_adaptation_allowed": True, "publication_allowed": True})
        catalog["editions"][0]["rights_status"] = "PUBLIC_DOMAIN_VERIFIED"
        self.assertTrue(validate_catalog(catalog)["rights_assessment"]["publication_allowed"])
        catalog["rights_assessment"]["evidence"] = []
        with self.assertRaisesRegex(NovelSourceCatalogError, "requires evidence"):
            validate_catalog(catalog)

    def test_unassessed_rights_cannot_enable_script_adaptation(self):
        catalog = self.catalog_with_edition()
        catalog["adaptation_policy"]["script_adaptation_allowed"] = True
        with self.assertRaisesRegex(NovelSourceCatalogError, "cannot enable script adaptation"):
            validate_catalog(catalog)

    def test_local_upload_uri_is_valid_source_provenance(self):
        catalog = self.catalog_with_edition()
        catalog["editions"][0]["source_url"] = "local://upload/jinghua-yuan-series/source.txt"
        catalog["locators"][0]["source_url"] = "local://upload/jinghua-yuan-series/source.txt#chapter-1"
        validated = validate_catalog(catalog)
        self.assertTrue(validated["editions"][0]["source_url"].startswith("local://upload/"))

    def test_rejects_credentialed_urls_and_reversed_ranges(self):
        catalog = self.catalog_with_edition()
        catalog["editions"][0]["source_url"] = "https://user:secret@example.org/book"
        with self.assertRaisesRegex(NovelSourceCatalogError, "without credentials"):
            validate_catalog(catalog)
        catalog = self.catalog_with_edition()
        catalog["locators"][0]["location"].update({"page_start": 8, "page_end": 1})
        with self.assertRaisesRegex(NovelSourceCatalogError, "range is reversed"):
            validate_catalog(catalog)

    def test_catalog_round_trip_is_bound_to_project(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory) / "jinghua-yuan-series"
            write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
            output = write_catalog(project_dir, build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘"))
            self.assertEqual(load_catalog(output)["project_id"], "jinghua-yuan-series")
            with self.assertRaisesRegex(NovelSourceCatalogError, "refusing to overwrite"):
                write_catalog(project_dir, build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘"))

    def test_json_schema_declares_rights_editions_chapters_and_locators(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas" / "novel-source-catalog.schema.json").read_text(encoding="utf-8"))
        self.assertTrue({"rights_assessment", "adaptation_policy", "edition", "chapter", "locator"}.issubset(schema["$defs"]))


if __name__ == "__main__":
    unittest.main()
