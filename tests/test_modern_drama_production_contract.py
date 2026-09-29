from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.modern_drama_production_contract import (
    ModernDramaContractError,
    _approval,
    _sha256,
    canonical_asset_ref,
    production_gate,
    set_shot_approval,
)


def _contract() -> dict:
    return {
        "freshness": "FRESH",
        "shots": [
            {
                "shot_id": "SHOT-001",
                "asset_refs": ["C:CHAR-001", "S:SCENE-OFFICE"],
                "approvals": {
                    "storyboard": _approval(),
                    "keyframe": _approval(),
                    "video": _approval(),
                },
            }
        ],
    }


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

    def test_approval_starts_pending(self) -> None:
        self.assertEqual(
            _approval(),
            {"required": True, "status": "PENDING", "note": ""},
        )

    def test_fingerprint_is_deterministic_for_key_order(self) -> None:
        self.assertEqual(_sha256({"a": 1, "b": 2}), _sha256({"b": 2, "a": 1}))

    def test_keyframe_cannot_be_approved_before_storyboard(self) -> None:
        payload = _contract()
        with patch(
            "scripts.modern_drama_production_contract.load_contract",
            return_value=copy.deepcopy(payload),
        ), patch("scripts.modern_drama_production_contract._atomic_json"):
            with self.assertRaisesRegex(ModernDramaContractError, "storyboard approval"):
                set_shot_approval(
                    Path("/tmp/demo"),
                    "SHOT-001",
                    "keyframe",
                    "APPROVED",
                    "identity checked",
                )

    def test_storyboard_approval_is_persisted_without_approving_downstream(self) -> None:
        payload = _contract()
        with patch(
            "scripts.modern_drama_production_contract.load_contract",
            return_value=copy.deepcopy(payload),
        ), patch("scripts.modern_drama_production_contract._atomic_json") as writer:
            shot = set_shot_approval(
                Path("/tmp/demo"),
                "SHOT-001",
                "storyboard",
                "APPROVED",
                "blocking and composition checked",
            )
        self.assertEqual(shot["approvals"]["storyboard"]["status"], "APPROVED")
        self.assertEqual(shot["approvals"]["keyframe"]["status"], "PENDING")
        self.assertEqual(shot["approvals"]["video"]["status"], "PENDING")
        writer.assert_called_once()

    def test_production_gate_requires_approved_assets_and_two_upstream_approvals(self) -> None:
        payload = _contract()
        payload["shots"][0]["approvals"]["storyboard"]["status"] = "APPROVED"
        payload["shots"][0]["approvals"]["keyframe"]["status"] = "APPROVED"

        def approved_entities(_project, kind):
            return {"CHAR-001"} if kind == "character" else set()

        with patch(
            "scripts.modern_drama_production_contract.load_contract",
            return_value=copy.deepcopy(payload),
        ), patch(
            "scripts.modern_drama_production_contract.approved_entities",
            side_effect=approved_entities,
        ):
            result = production_gate(Path("/tmp/demo"), "SHOT-001")
        self.assertFalse(result["ready"])
        self.assertIn("scene asset not approved: SCENE-OFFICE", result["blockers"])

    def test_production_gate_passes_when_contract_and_assets_are_approved(self) -> None:
        payload = _contract()
        payload["shots"][0]["approvals"]["storyboard"]["status"] = "APPROVED"
        payload["shots"][0]["approvals"]["keyframe"]["status"] = "APPROVED"

        with patch(
            "scripts.modern_drama_production_contract.load_contract",
            return_value=copy.deepcopy(payload),
        ), patch(
            "scripts.modern_drama_production_contract.approved_entities",
            side_effect=lambda _project, kind: {"CHAR-001"} if kind == "character" else {"SCENE-OFFICE"},
        ):
            result = production_gate(Path("/tmp/demo"), "SHOT-001")
        self.assertTrue(result["ready"])
        self.assertEqual(result["blockers"], [])


if __name__ == "__main__":
    unittest.main()
