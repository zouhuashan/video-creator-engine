from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.modern_asset_library import approved_entities, load_library, review_asset


class ModernAssetReviewTests(unittest.TestCase):
    def test_legacy_asset_defaults_to_pending_and_can_be_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "rendering/modern-assets.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 1,
                        "updated_at": "2026-09-29T00:00:00Z",
                        "assets": [
                            {
                                "kind": "character",
                                "entity_id": "CHAR-001",
                                "variant": "front",
                                "expression": "neutral",
                                "path": "rendering/modern-assets/files/a.png",
                                "sha256": "a" * 64,
                                "bytes": 1,
                                "license_note": "",
                                "created_at": "2026-09-29T00:00:00Z"
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_library(project)["assets"][0]["review_status"], "PENDING")
            self.assertEqual(approved_entities(project, "character"), set())
            review_asset(project, "rendering/modern-assets/files/a.png", "APPROVED", "identity locked")
            self.assertEqual(approved_entities(project, "character"), {"CHAR-001"})


if __name__ == "__main__":
    unittest.main()
