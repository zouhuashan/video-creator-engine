import unittest

from scripts.technical_qc import TechnicalQCError, evaluate_technical_qc


class TechnicalQCTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "width": 1080, "height": 1920, "fps": 30.0,
            "video_codec": "h264", "audio_codec": "aac", "duration_seconds": 60.0,
            "video_start_seconds": 0.0, "audio_start_seconds": 0.02,
            "video_duration_seconds": 60.0, "audio_duration_seconds": 59.9,
            "size_bytes": 1000,
        }
        self.scan = {
            "decode_exit_code": 0, "black_durations": [], "frozen_durations": [],
            "silence_durations": [0.5], "unclosed_silence_count": 0, "max_volume_db": -1.0,
        }
        self.layout = {
            "schema_version": 1,
            "cues": [{"cue_id": "SUB001", "box": {"x": 0.1, "y": 0.7, "width": 0.6, "height": 0.08}}],
        }

    def test_passes_all_required_checks_with_real_evidence_shape(self):
        result = evaluate_technical_qc(self.metadata, self.scan, self.layout)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 14)
        self.assertTrue(all(result["checks"].values()))

    def test_reports_media_defects_individually(self):
        scan = {**self.scan, "black_durations": [1.2], "frozen_durations": [3.0],
                "silence_durations": [4.0], "max_volume_db": 0.0, "decode_exit_code": 1}
        result = evaluate_technical_qc(self.metadata, scan, self.layout)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            result["failed_checks"],
            ["black_frames", "frozen_frames", "silence", "clipping", "encoding_success", "file_integrity"],
        )

    def test_rejects_subtitles_outside_safe_area_or_behind_ui(self):
        layout = {"schema_version": 1, "cues": [
            {"cue_id": "SUB001", "box": {"x": 0.9, "y": 0.6, "width": 0.08, "height": 0.1}}
        ]}
        result = evaluate_technical_qc(self.metadata, self.scan, layout)
        self.assertFalse(result["checks"]["subtitle_bounds"])
        self.assertFalse(result["checks"]["subtitle_occlusion"])
        self.assertEqual(result["evidence"]["occluded_subtitle_cues"], ["SUB001"])

    def test_missing_subtitle_evidence_fails_both_layout_checks(self):
        result = evaluate_technical_qc(self.metadata, self.scan, {"schema_version": 1, "cues": []})
        self.assertEqual(result["failed_checks"], ["subtitle_bounds", "subtitle_occlusion"])

    def test_invalid_evidence_is_rejected(self):
        with self.assertRaisesRegex(TechnicalQCError, "incomplete"):
            evaluate_technical_qc({"width": None}, self.scan, self.layout)


if __name__ == "__main__":
    unittest.main()
