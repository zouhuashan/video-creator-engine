from __future__ import annotations

import unittest

from scripts.modern_drama_production_contract import (
    ModernDramaContractError,
    _approval,
    _preserved_approvals,
    _review_gate,
    _sha256,
    canonical_asset_ref,
)


class ModernDramaProductionContractTests(unittest.TestCase):
    def test_canonical_asset_refs_are_stable_and_typed(self) -> None:
        self.assertEqual(canonical_asset_ref("character", "CHAR-001"), "C:CHAR-001")
        self.assertEqual(canonical_asset_ref("scene", "SCENE-OFFICE"), "S:SCENE-OFFICE")
        self.assertEqual(canonical_asset_ref("prop", "assets/phone.png"), "P:assets/phone.png")

    def test_asset_ref_rejects_unknown_kind_or_empty_value(self) -> None:
        with self.assertRaises(ModernDramaContractError):
            canonical_asset_ref("video", "x")
        with self.assertRaises(ModernDramaContractError):
            canonical_asset_ref("character", "")

    def test_approval_can_mark_keyframe_not_required(self) -> None:
        self.assertEqual(_approval(), {"required": True, "status": "PENDING", "note": ""})
        self.assertEqual(_approval(False), {"required": False, "status": "NOT_REQUIRED", "note": ""})

    def test_fingerprint_is_deterministic_for_key_order(self) -> None:
        self.assertEqual(_sha256({"a": 1, "b": 2}), _sha256({"b": 2, "a": 1}))

    def test_approvals_survive_only_same_shot_fingerprint(self) -> None:
        existing = {
            "shot_fingerprint": "same",
            "approvals": {
                "storyboard": {"required": True, "status": "APPROVED", "note": "ok"},
                "keyframe": {"required": True, "status": "APPROVED", "note": "ok"},
                "video": {"required": True, "status": "PENDING", "note": ""},
            },
        }
        kept = _preserved_approvals(existing, "same", keyframe_required=True)
        self.assertEqual(kept["storyboard"]["status"], "APPROVED")
        self.assertEqual(kept["keyframe"]["status"], "APPROVED")
        reset = _preserved_approvals(existing, "changed", keyframe_required=True)
        self.assertEqual(reset["storyboard"]["status"], "PENDING")
        self.assertEqual(reset["keyframe"]["status"], "PENDING")

    def test_non_keyframe_route_does_not_fake_keyframe_approval(self) -> None:
        approvals = _preserved_approvals(None, "x", keyframe_required=False)
        self.assertEqual(approvals["keyframe"]["status"], "NOT_REQUIRED")
        self.assertFalse(approvals["keyframe"]["required"])

    def test_review_gate_enforces_stage_order(self) -> None:
        shot = {
            "approvals": {
                "storyboard": _approval(True),
                "keyframe": _approval(True),
                "video": _approval(True),
            }
        }
        with self.assertRaisesRegex(ModernDramaContractError, "storyboard"):
            _review_gate(shot, "keyframe")
        shot["approvals"]["storyboard"]["status"] = "APPROVED"
        _review_gate(shot, "keyframe")
        with self.assertRaisesRegex(ModernDramaContractError, "keyframe"):
            _review_gate(shot, "video")
        shot["approvals"]["keyframe"]["status"] = "APPROVED"
        _review_gate(shot, "video")


if __name__ == "__main__":
    unittest.main()
