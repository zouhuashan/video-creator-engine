import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class ChildLookdevV6ConfigTests(unittest.TestCase):
    def test_v6_uses_native_mpfb_child_phenotype(self):
        payload=json.loads((ROOT/"config/child-lookdev-v6.json").read_text(encoding="utf-8"))
        self.assertEqual(
            payload["modeling_strategy"],
            "mpfb_native_child_phenotype_plus_light_stylize",
        )
        phenotype=payload["mpfb"]["phenotype"]
        self.assertEqual(phenotype["age"],"child")
        self.assertEqual(phenotype["gender"],"female")
        self.assertEqual(phenotype["race"],"asian")
        self.assertFalse(phenotype["add_breast"])
        self.assertIn(
            "mpfb_native_child_phenotype_applied",
            payload["quality_gate"]["requires"],
        )
        self.assertEqual(payload["quality_gate"]["status"],"PENDING")


if __name__=="__main__":
    unittest.main()
