from __future__ import annotations

import unittest

from scripts.modern_drama_production_contract import (
    ModernDramaContractError,
    _approval,
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

    def test_approval_starts_pending(self) -> None:
        self.assertEqual(
            _approval(),
            {"required": True, "status": "PENDING", "note": ""},
        )

    def test_fingerprint_is_deterministic_for_key_order(self) -> None:
        self.assertEqual(_sha256({"a": 1, "b": 2}), _sha256({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
