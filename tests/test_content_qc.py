import copy
import unittest

from scripts.content_qc import ContentQCError, evaluate_content_qc, load_config


class ContentQCTests(unittest.TestCase):
    def setUp(self):
        self.script = {"sections": [
            {"section": "hook", "narration": "三秒告诉你值不值。", "source_ids": []},
            {"section": "problem", "narration": "订阅费并不便宜。", "source_ids": []},
            {"section": "evidence", "narration": "官方价格是二十美元。", "source_ids": ["S001"]},
            {"section": "comparison", "narration": "按使用频率比较更合理。", "source_ids": []},
            {"section": "conclusion", "narration": "高频用户更值得订阅。", "source_ids": []},
            {"section": "cta", "narration": "留言说说你的使用频率。", "source_ids": []},
        ]}
        self.research = {"sources": [{"source_id": "S001"}]}
        self.assessment = {"schema_version": 1, "assessments": [
            {"check": name, "status": "PASS", "evidence": f"已核验 {name}",
             **({"source_ids": ["S001"]} if name in {"factual_accuracy", "numeric_accuracy"} else {})}
            for name in load_config()["required_checks"]
        ]}

    def test_requires_and_passes_all_ten_checks(self):
        result = evaluate_content_qc(self.script, self.research, self.assessment)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 10)

    def test_automated_rules_override_optimistic_review(self):
        script = copy.deepcopy(self.script)
        script["sections"][1]["narration"] = script["sections"][0]["narration"]
        script["sections"][4]["narration"] = "这绝对是最好的选择。"
        script["sections"][5]["narration"] = "加微信返现。"
        result = evaluate_content_qc(script, self.research, self.assessment)
        self.assertEqual(
            result["failed_checks"],
            ["platform_sensitive_language", "duplicate_content", "unsupported_absolute_claims"],
        )

    def test_explicit_review_failure_is_preserved(self):
        assessment = copy.deepcopy(self.assessment)
        assessment["assessments"][0]["status"] = "FAIL"
        assessment["assessments"][0]["evidence"] = "发现错别字"
        result = evaluate_content_qc(self.script, self.research, assessment)
        self.assertEqual(result["failed_checks"], ["typos"])

    def test_rejects_missing_duplicate_or_unknown_checks(self):
        assessment = copy.deepcopy(self.assessment)
        assessment["assessments"].pop()
        with self.assertRaisesRegex(ContentQCError, "missing checks"):
            evaluate_content_qc(self.script, self.research, assessment)

        assessment = copy.deepcopy(self.assessment)
        assessment["assessments"][1]["check"] = "typos"
        with self.assertRaisesRegex(ContentQCError, "duplicate"):
            evaluate_content_qc(self.script, self.research, assessment)

    def test_rejects_unknown_source_evidence(self):
        assessment = copy.deepcopy(self.assessment)
        assessment["assessments"][0]["source_ids"] = ["S999"]
        with self.assertRaisesRegex(ContentQCError, "unknown source"):
            evaluate_content_qc(self.script, self.research, assessment)


if __name__ == "__main__":
    unittest.main()
