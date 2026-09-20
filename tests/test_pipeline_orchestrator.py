import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.pipeline_orchestrator import _qc_with_retry, pipeline_status, run_pipeline, update_pipeline_review, PipelineError
from support.providers.comfyui_image_provider import ComfyUIImageError


class PipelineOrchestratorTests(unittest.TestCase):
    def test_dry_run_builds_machine_manifest_without_remote_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")

            result = run_pipeline("demo-project", dry_run=True, projects_root=projects)

            self.assertEqual(result["status"], "DRY_RUN_PASS")
            self.assertEqual(result["execution_mode"], "DRY_RUN")
            self.assertEqual(result["routing"]["blender_role"], "AUXILIARY_3D_CONTROL")
            self.assertTrue((project / "pipeline" / "run.json").is_file())
            self.assertTrue((project / "pipeline" / "prompts" / "SHOT-DEMO-001.txt").is_file())
            control = json.loads((project / "pipeline" / "scene-control" / "SHOT-DEMO-001.json").read_text(encoding="utf-8"))
            self.assertFalse(control["final_visual_allowed"])
            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["image"]["status"], "PLANNED")
            self.assertEqual(stages["image"]["route"]["provider_id"], "COMFYUI_IMAGE")
            self.assertFalse(stages["subtitles"]["asr_round_trip"])
            self.assertTrue(stages["review"]["human_required"])
            self.assertEqual(stages["review"]["owner"], "human")
            self.assertTrue(stages["review"]["human_action"])
            for stage_id, stage in stages.items():
                if stage_id != "review":
                    self.assertEqual(stage["owner"], "software")
                    self.assertFalse(stage["human_action"])
            policy = result["automation_policy"]
            self.assertTrue(policy["software_first"])
            self.assertTrue(policy["manual_creation_forbidden_by_default"])
            self.assertEqual(policy["user_actions"], ["SELECT_INPUT", "FINAL_REVIEW", "MANUAL_PUBLISH"])
            self.assertEqual(policy["human_owned_stages"], ["review"])
            self.assertNotIn("review", policy["software_owned_stages"])

            status = pipeline_status("demo-project", projects)
            self.assertEqual(status["run_manifest"], "pipeline/run.json")
            with self.assertRaisesRegex(PipelineError, "not ready"):
                update_pipeline_review("demo-project", "APPROVED", projects_root=projects)

    def test_execute_can_generate_local_comfyui_keyframe_without_remote_confirmation(self):
        class FakeComfy:
            def __init__(self, *args, **kwargs):
                pass

            def health(self, **kwargs):
                return {"connected": True}

            def available_checkpoints(self, **kwargs):
                return ["local-test.safetensors"]

            def generate(self, prompt, output_path, *, size):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"\x89PNG\r\n\x1a\npipeline-test")
                return {"provider": "comfyui_image", "model": "local-test.safetensors", "size": size, "quality": "local", "output": str(output_path)}

        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")
            with patch("scripts.pipeline_orchestrator.ComfyUIImageProvider", FakeComfy):
                result = run_pipeline("demo-project", dry_run=False, projects_root=projects)
            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["image"]["status"], "WAITING_REVIEW")
            self.assertEqual(stages["image"]["route"]["provider_id"], "COMFYUI_IMAGE")
            metadata = project / stages["image"]["metadata"]
            saved = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(saved["review_status"], "PENDING")
            self.assertFalse(saved["remote"])
            self.assertTrue((project / saved["output"]).is_file())

    def test_execute_local_video_provider_uses_only_approved_keyframe(self):
        class FakeLocalVideo:
            def generate(self, request):
                request.output_path.parent.mkdir(parents=True, exist_ok=True)
                request.output_path.write_bytes(b"video")
                return type("Result", (), {
                    "output_path": request.output_path,
                    "provider": "local_ken_burns",
                    "duration_seconds": request.shot_duration_seconds,
                    "image_count": len(request.image_paths),
                    "remote_generation": False,
                })()

        def _fake_assemble(project_path, video, **kwargs):
            (project_path / "final.mp4").write_bytes(b"final")
            return {"status":"PASS","output":"final.mp4","finalizer":"ffmpeg"}

        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")
            image_dir = project / "lookdev" / "image-studio" / "keyframes"
            image_dir.mkdir(parents=True)
            keyframe = image_dir / "approved.png"
            keyframe.write_bytes(b"png")
            (image_dir / "approved.json").write_text(json.dumps({
                "artifact_type": "keyframe",
                "review_status": "APPROVED",
                "output": "lookdev/image-studio/keyframes/approved.png",
            }), encoding="utf-8")

            with patch("scripts.pipeline_orchestrator.LocalKenBurnsVideo", return_value=FakeLocalVideo()), \
                 patch("scripts.pipeline_orchestrator.ComfyUIImageProvider", side_effect=ComfyUIImageError("offline")), \
                 patch("scripts.pipeline_orchestrator.ensure_tts", return_value={"status":"SKIPPED","asset":"","provider":"none"}), \
                 patch("scripts.pipeline_orchestrator.ensure_subtitles", return_value={"status":"SKIPPED","asset":"","asr_round_trip":False}), \
                 patch("scripts.pipeline_orchestrator.assemble_final", side_effect=_fake_assemble), \
                 patch("scripts.pipeline_orchestrator._qc_with_retry", return_value={"status":"PASS","auto_retry":False,"attempt_count":1,"attempts":[]}):
                result = run_pipeline("demo-project", dry_run=False, projects_root=projects)

            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["video"]["status"], "PASS")
            self.assertEqual(stages["video"]["provider"], "local_ken_burns")
            self.assertFalse(stages["video"]["remote_generation"])
            self.assertTrue((project / stages["video"]["asset"]).is_file())

    def test_video_waits_for_human_review_when_new_keyframe_is_pending(self):
        class FakeComfy:
            def __init__(self, *args, **kwargs):
                pass

            def health(self, **kwargs):
                return {"connected": True}

            def available_checkpoints(self, **kwargs):
                return ["local-test.safetensors"]

            def generate(self, prompt, output_path, *, size):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"png")
                return {"provider":"comfyui_image","model":"local-test.safetensors","size":size,"quality":"local","output":str(output_path)}

        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")
            with patch("scripts.pipeline_orchestrator.ComfyUIImageProvider", FakeComfy):
                result = run_pipeline("demo-project", dry_run=False, projects_root=projects)
            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["image"]["status"], "WAITING_REVIEW")
            self.assertEqual(stages["video"]["status"], "WAITING_REVIEW")

    def test_execute_reuses_media_and_reaches_qc_without_manual_editing(self):
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")
            generated = project / "generated" / "shot.mp4"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"video")
            audio = project / "audio" / "voice.wav"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"audio")
            subtitles = project / "subtitles" / "voice.srt"
            subtitles.parent.mkdir(parents=True)
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

            def fake_assemble(project_path, video, *, audio=None, subtitles=None, output=None):
                target = output or (project_path / "final.mp4")
                target.write_bytes(b"final")
                return {"status":"PASS","output":"final.mp4","finalizer":"ffmpeg"}

            with patch("scripts.pipeline_orchestrator.ComfyUIImageProvider", side_effect=ComfyUIImageError("offline")), \
                 patch("scripts.pipeline_orchestrator.assemble_final", side_effect=fake_assemble), \
                 patch("scripts.pipeline_orchestrator._qc_with_retry", return_value={"status":"PASS","auto_retry":False,"attempt_count":1,"attempts":[]}):
                result = run_pipeline("demo-project", dry_run=False, projects_root=projects)

            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["tts"]["status"], "PASS")
            self.assertEqual(stages["subtitles"]["status"], "PASS")
            self.assertEqual(stages["assembly"]["status"], "PASS")
            self.assertEqual(stages["qc"]["status"], "PASS")
            self.assertTrue((project / "final.mp4").is_file())
            self.assertTrue(result["review"]["ready"])


    def test_qc_auto_retry_is_bounded_and_records_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "final.mp4"
            video.write_bytes(b"video")
            failed = {"status":"FAIL","auto_retry":True,"retry_class":"TECHNICAL","checks":{}}
            passed = {"status":"PASS","auto_retry":False,"retry_class":"NONE","checks":{}}
            with patch("scripts.pipeline_orchestrator._auto_qc", side_effect=[failed, passed]), \
                 patch("scripts.pipeline_orchestrator._repair_media_container", return_value={"status":"PASS","action":"TRANSCODE_CONTAINER_NORMALIZE"}) as repair:
                result = _qc_with_retry(video, {"auto_retry":{"enabled":True,"max_attempts_per_stage":2}})
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["attempt_count"], 2)
            self.assertEqual(repair.call_count, 1)
            self.assertEqual(result["attempts"][1]["repair"]["action"], "TRANSCODE_CONTAINER_NORMALIZE")



if __name__ == "__main__":
    unittest.main()
