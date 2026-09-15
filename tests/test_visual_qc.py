import copy
import unittest

from scripts.visual_qc import VisualQCError, evaluate_visual_qc


class VisualQCTests(unittest.TestCase):
    def setUp(self):
        self.storyboard = {"scenes": [
            {"scene_id": "SC001", "start": 0, "end": 3, "caption": "三秒看懂"},
            {"scene_id": "SC002", "start": 3, "end": 9, "caption": "先看价格"},
            {"scene_id": "SC003", "start": 9, "end": 15, "caption": "再看使用频率"},
        ]}
        self.analysis = {"schema_version": 1, "scenes": [
            self.scene("SC001", "fp-a"), self.scene("SC002", "fp-b"), self.scene("SC003", "fp-c")
        ]}

    @staticmethod
    def scene(scene_id, fingerprint):
        return {"scene_id": scene_id, "visual_fingerprint": fingerprint, "empty_space_ratio": 0.2,
                "crop_ok": True, "minimum_text_contrast_ratio": 7.0,
                "key_information_boxes": [{"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.2}]}

    def test_passes_all_seven_visual_checks(self):
        result = evaluate_visual_qc(self.storyboard, self.analysis)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 7)

    def test_reports_every_visual_defect_with_scene_evidence(self):
        storyboard = copy.deepcopy(self.storyboard)
        storyboard["scenes"][1]["end"] = 20
        storyboard["scenes"][1]["caption"] = "字" * 150
        analysis = copy.deepcopy(self.analysis)
        analysis["scenes"][1].update({"visual_fingerprint": "fp-a", "empty_space_ratio": 0.8,
                                      "crop_ok": False, "minimum_text_contrast_ratio": 2.0,
                                      "key_information_boxes": [{"x": 0.9, "y": 0.5, "width": 0.05, "height": 0.1}]})
        result = evaluate_visual_qc(storyboard, analysis)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failed_checks"], [
            "shot_too_long", "repeated_visuals", "subtitle_density", "abnormal_empty_space",
            "incorrect_crop", "key_information_ui_occlusion", "text_background_contrast",
        ])

    def test_requires_exactly_one_analysis_record_per_scene(self):
        missing = copy.deepcopy(self.analysis)
        missing["scenes"].pop()
        with self.assertRaisesRegex(VisualQCError, "missing scenes"):
            evaluate_visual_qc(self.storyboard, missing)

        duplicate = copy.deepcopy(self.analysis)
        duplicate["scenes"][2]["scene_id"] = "SC002"
        with self.assertRaisesRegex(VisualQCError, "duplicate"):
            evaluate_visual_qc(self.storyboard, duplicate)

    def test_rejects_invalid_boxes_and_metrics(self):
        analysis = copy.deepcopy(self.analysis)
        analysis["scenes"][0]["key_information_boxes"][0]["width"] = 2
        with self.assertRaisesRegex(VisualQCError, "invalid visual evidence"):
            evaluate_visual_qc(self.storyboard, analysis)


if __name__ == "__main__":
    unittest.main()
