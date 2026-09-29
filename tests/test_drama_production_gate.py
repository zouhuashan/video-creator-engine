import json
from pathlib import Path

from scripts.drama_production_gate import (
    _modern_character_blockers,
    _modern_storyboard_blockers,
)


def test_modern_character_gate_requires_approved_asset(tmp_path: Path):
    path = tmp_path / "rendering/modern-assets.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "revision": 1,
        "updated_at": "2026-09-29T00:00:00Z",
        "assets": [{
            "kind": "character",
            "entity_id": "CHR-001",
            "variant": "front",
            "expression": "neutral",
            "path": "rendering/modern-assets/files/a.png",
            "sha256": "a" * 64,
            "bytes": 1,
            "license_note": "",
            "created_at": "2026-09-29T00:00:00Z",
            "review_status": "APPROVED"
        }]
    }), encoding="utf-8")
    assert _modern_character_blockers(tmp_path, ["CHR-001"]) == []
    assert _modern_character_blockers(tmp_path, ["CHR-002"])


def test_modern_storyboard_gate_requires_shot_approval(tmp_path: Path):
    path = tmp_path / "rendering/modern-timeline-edits.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "revision": 1,
        "shots": {
            "SHOT-1": {
                "human_review": {
                    "status": "APPROVED",
                    "note": "composition and identity checked"
                }
            }
        }
    }), encoding="utf-8")
    assert _modern_storyboard_blockers(tmp_path, "SHOT-1") == []
    assert _modern_storyboard_blockers(tmp_path, "SHOT-2")
