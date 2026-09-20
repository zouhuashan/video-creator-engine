import os
import unittest
import json
import tempfile
import threading
import urllib.request
from pathlib import Path

import scripts.web_server as web_server
from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_anime_runtime import NovelAnimeRuntime
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_story_review import audit_story, write_report
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible
from scripts.novel_character_designs import build_character_designs, write_character_designs
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_storyboard import build_storyboard, write_storyboard
from scripts.novel_animatic import build_animatic, write_animatic
from scripts.novel_animatic_review import build_review, write_review
from scripts.novel_voice_profiles import build_voice_profiles, write_voice_profiles
from scripts.novel_audio_assets import build_audio_assets, write_audio_assets
from scripts.novel_audio_mix import build_audio_mix, write_audio_mix
from scripts.novel_dynamic_shots import build_dynamic_shots, write_dynamic_shots
from scripts.novel_edit_timelines import build_edit_timelines, write_edit_timelines
from scripts.novel_qc import build_qc_report, write_qc_report


class WebServerTests(unittest.TestCase):
    def test_provider_status_never_exposes_secret_values(self):
        previous = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "secret-value"
        try:
            providers = web_server._provider_status()
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous
        openai = next(provider for provider in providers if provider["id"] == "openai_sora")
        self.assertTrue(openai["configured"])
        self.assertNotIn("secret-value", str(openai))
        self.assertEqual(openai["env"], "OPENAI_API_KEY")

    def test_project_file_boundary_rejects_traversal(self):
        with self.assertRaises(ValueError):
            web_server._safe_project_file("jinghua-yuan-series", "../../.env.example")

    def test_project_file_resolves_known_asset(self):
        path = web_server._safe_project_file("jinghua-yuan-series", "assets/characters/CHR-JHY-BAIHUA/baihua-anchor-v1.png")
        self.assertTrue(path.is_file())

    def test_project_media_exposes_registered_lookdev_outputs(self):
        media = web_server._media_files(web_server._safe_project("jinghua-yuan-series"))
        paths = {item["path"] for item in media}
        self.assertIn("lookdev/baihua-yaochi-motion-test-v1.png", paths)
        self.assertIn("lookdev/baihua-yaochi-motion-test-v1.mp4", paths)

    def test_novel_anime_project_summary_uses_p18_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory) / "jinghua-yuan-series"
            write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
            NovelAnimeRepository(project_dir).initialize()
            NovelAnimeRuntime(project_dir).initialize()
            write_catalog(project_dir, build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘"))
            write_bible(project_dir, build_bible(project_dir))
            write_plan(project_dir, build_plan(project_dir))
            write_episode_planning(project_dir, build_episode_planning(project_dir))
            write_script_package(project_dir, build_script_package(project_dir))
            write_report(project_dir, audit_story(project_dir))
            write_visual_bible(project_dir, build_visual_bible(project_dir))
            write_character_designs(project_dir, build_character_designs(project_dir))
            write_environment_assets(project_dir, build_environment_assets(project_dir))
            write_asset_review(project_dir, build_asset_review(project_dir))
            write_shot_breakdown(project_dir, build_shot_breakdown(project_dir))
            write_storyboard(project_dir, build_storyboard(project_dir))
            write_animatic(project_dir, build_animatic(project_dir))
            write_review(project_dir, build_review(project_dir))
            write_voice_profiles(project_dir, build_voice_profiles(project_dir))
            write_audio_assets(project_dir, build_audio_assets(project_dir))
            write_audio_mix(project_dir, build_audio_mix(project_dir))
            write_dynamic_shots(project_dir, build_dynamic_shots(project_dir))
            write_edit_timelines(project_dir, build_edit_timelines(project_dir))
            write_qc_report(project_dir, build_qc_report(project_dir))
            imports_dir = project_dir / "sources" / "imports"
            imports_dir.mkdir(parents=True)
            (imports_dir / "test.json").write_text(json.dumps({
                "import_id": "IMP-SRC-JHY-001-TEST", "edition_id": "SRC-JHY-001",
                "source_file_name": "fixture.txt", "source_sha256": "0" * 64,
                "chapters": [{"chapter_id": "CH-JHY-0001"}],
                "extraction": {"characters": [{}], "locations": [{}], "props": [{}], "events": [{}, {}]},
                "test_only": True, "full_text_stored": False, "human_review_required": True,
                "created_at": "2026-09-16T00:00:00Z",
            }), encoding="utf-8")
            projects = web_server._novel_anime_projects(Path(directory))
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["ip_id"], "IP-JHY")
        self.assertEqual(projects[0]["episode_ids"], [f"S01E{index:03d}" for index in range(1, 6)])
        self.assertEqual(projects[0]["repository"], {"entities": 8, "dependencies": 7, "asset_versions": 0, "snapshots": 0})
        self.assertEqual(projects[0]["runtime"]["migrations"], 0)
        self.assertEqual(projects[0]["source_catalog"]["status"], "UNASSESSED")
        self.assertFalse(projects[0]["source_catalog"]["publication_allowed"])
        self.assertEqual(projects[0]["source_catalog"]["import_count"], 1)
        self.assertEqual(projects[0]["source_catalog"]["test_import_count"], 1)
        self.assertEqual(projects[0]["source_catalog"]["event_candidates"], 2)
        self.assertFalse(projects[0]["source_catalog"]["full_text_stored"])
        self.assertEqual(projects[0]["story_bible"]["world_status"], "DRAFT")
        self.assertEqual(projects[0]["story_bible"]["continuity_snapshot_count"], 1)
        self.assertEqual(projects[0]["series_plan"]["status"], "DRAFT")
        self.assertEqual(projects[0]["series_plan"]["season_plan_count"], 1)
        self.assertEqual(projects[0]["episode_planning"]["episode_card_count"], 5)
        self.assertEqual(projects[0]["episode_planning"]["story_arc_count"], 0)
        self.assertEqual(projects[0]["episode_scripts"]["script_count"], 5)
        self.assertEqual(projects[0]["episode_scripts"]["available_input_count"], 1)
        self.assertEqual(projects[0]["story_review"]["overall_status"], "BLOCKED")
        self.assertGreater(projects[0]["story_review"]["blocker_count"], 0)
        self.assertEqual(projects[0]["visual_bible"]["status"], "DRAFT")
        self.assertEqual(projects[0]["visual_bible"]["episode_palette_count"], 5)
        self.assertEqual(projects[0]["character_designs"]["character_count"], 0)
        self.assertEqual(projects[0]["character_designs"]["selected_turnaround_count"], 0)
        self.assertEqual(projects[0]["environment_assets"]["location_count"], 0)
        self.assertEqual(projects[0]["environment_assets"]["prop_count"], 0)
        self.assertEqual(projects[0]["asset_review"]["reference_package_count"], 0)
        self.assertEqual(projects[0]["shot_breakdown"]["shot_count"], 0)
        self.assertEqual(projects[0]["storyboard"]["frame_count"], 0)
        self.assertEqual(projects[0]["animatic"]["episode_count"], 5)
        self.assertEqual(projects[0]["animatic_review"]["overall_status"], "BLOCKED")
        self.assertEqual(projects[0]["voice_profiles"]["profile_count"], 0)
        self.assertEqual(projects[0]["audio_assets"]["track_count"], 0)
        self.assertEqual(projects[0]["audio_mix"]["episode_count"], 5)
        self.assertEqual(projects[0]["dynamic_shots"]["shot_count"], 0)
        self.assertEqual(projects[0]["edit_timelines"]["episode_count"], 5)
        self.assertEqual(projects[0]["qc"]["overall_status"], "BLOCKED")
        self.assertEqual(projects[0]["qc"]["open_blocker_count"], 12)

    def test_novel_studio_exposes_ten_connected_workspaces_and_recovery_inventory(self):
        studio = web_server._novel_anime_workspaces("jinghua-yuan-series")
        self.assertEqual(len(studio["workspaces"]), 10)
        self.assertEqual(studio["workspace_order"], ["overview", "ip", "story", "script", "assets", "storyboard", "audio", "render", "review", "publish"])
        self.assertEqual(studio["workspaces"][2]["id"], "story")
        backups = web_server._backup_inventory(web_server._safe_project("jinghua-yuan-series"))
        self.assertGreaterEqual(backups["snapshot_count"], 1)
        self.assertTrue(backups["recovery_requires_manual_confirmation"])
        acceptance = web_server.acceptance_summary(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(acceptance["decision"], "HOLD")
        self.assertEqual(acceptance["motion_test_count"], 3)

    def test_novel_readiness_exposes_blocked_stage_gates_from_project_state(self):
        summary = next(item for item in web_server._novel_anime_projects() if item["directory_id"] == "jinghua-yuan-series")
        readiness = summary["readiness"]
        self.assertEqual(readiness["decision"], "HOLD")
        self.assertEqual(readiness["ready_count"], 0)
        self.assertEqual(readiness["gate_count"], 7)
        self.assertEqual([gate["id"] for gate in readiness["gates"]], ["source", "story", "visual", "storyboard", "audio", "render", "qc"])
        self.assertTrue(all(gate["status"] == "BLOCKED" for gate in readiness["gates"]))
        self.assertGreaterEqual(len(readiness["next_actions"]), 1)

    def test_novel_project_summary_cache_returns_isolated_results(self):
        web_server._NOVEL_PROJECT_CACHE.clear()
        first = web_server._novel_anime_projects()
        self.assertTrue(first)
        first[0]["title"] = "changed in caller"
        second = web_server._novel_anime_projects()
        self.assertNotEqual(second[0]["title"], "changed in caller")
        self.assertIn(str(web_server.PROJECTS_ROOT.resolve()), web_server._NOVEL_PROJECT_CACHE)

    def test_web_entrypoints_are_tracked_assets(self):
        self.assertTrue((web_server.WEB_ROOT / "index.html").is_file())
        self.assertTrue((web_server.WEB_ROOT / "app.js").is_file())
        self.assertTrue((web_server.WEB_ROOT / "styles.css").is_file())

    def test_web_exposes_novel_import_workspace_and_local_upload_api(self):
        index = (web_server.WEB_ROOT / "index.html").read_text(encoding="utf-8")
        app = (web_server.WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-view="novelImport"', index)
        self.assertIn('id="novelImportFile"', index)
        self.assertIn('/api/novel-anime/import', app)
        self.assertIn('OWNED_OR_LICENSED', app)
        self.assertIn("TextDecoder('utf-8', { fatal: true })", app)

    def test_web_exposes_managed_comfyui_controls(self):
        index = (web_server.WEB_ROOT / "index.html").read_text(encoding="utf-8")
        app = (web_server.WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="imageStudioStartComfy"', index)
        self.assertIn('id="imageStudioStopComfy"', index)
        self.assertIn('/api/comfyui/service/start', app)
        self.assertIn('/api/comfyui/service/stop', app)
        self.assertIn('/api/comfyui/service/status', app)
        self.assertIn('id="imageStudioInstallComfy"', index)
        self.assertIn('/api/comfyui/install/start', app)
        self.assertIn('/api/comfyui/install/status', app)

    def test_character_asset_inventory_exposes_registered_turnarounds(self):
        assets = web_server._character_asset_inventory(web_server._safe_project("jinghua-yuan-series"))
        asset_ids = {item["asset_id"] for item in assets}
        self.assertIn("AST-CHR-JHY-BAIHUA-FRONT", asset_ids)
        self.assertIn("AST-CHR-JHY-BAIHUA-SIDE", asset_ids)
        self.assertIn("AST-CHR-JHY-BAIHUA-BACK", asset_ids)
        self.assertTrue(all(str(item["media_url"]).startswith("/media/jinghua-yuan-series/") for item in assets))

    def test_character_rig_inventory_exposes_review_gated_layers(self):
        rig = web_server._character_rig_inventory(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(rig["count"], 9)
        self.assertEqual(rig["rigs"][0]["id"], "RIG-CHR-JHY-BAIHUA-FRONT-V1")
        self.assertEqual([layer["name"] for layer in rig["rigs"][0]["layers"]], ["full", "head", "torso", "lower"])
        self.assertEqual(rig["rigs"][0]["human_review"]["status"], "PENDING")
        self.assertEqual(rig["rigs"][1]["id"], "RIG-CHR-JHY-WUZETIAN-FRONT-V1")

    def test_episode_master_inventory_exposes_five_playable_local_episodes(self):
        result = web_server._episode_master_inventory(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["episode_count"], 5)
        self.assertTrue(all(item["media_url"].startswith("/media/jinghua-yuan-series/") for item in result["episodes"]))
        self.assertTrue(all(item["qc_frame_url"].endswith("-speech-check.png") for item in result["episodes"]))
        self.assertEqual(set(result["episodes"][0]["human_review"]["checks"]), set(web_server.EPISODE_REVIEW_CHECKS))
        self.assertEqual(result["technical_qc"]["status"], "PASS")
        self.assertEqual(result["technical_qc"]["passed_episode_count"], 5)
        metadata = web_server._episode_metadata(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(len(metadata), 5)
        self.assertEqual(metadata[0]["episode_id"], "S01E001")
        self.assertTrue(all(item["provider"] == "local_episode_assembly" for item in metadata))

    def test_episode_review_requires_named_reviewer_and_updates_aggregate_status(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manifest_dir = project / "renders" / "episodes"
            manifest_dir.mkdir(parents=True)
            path = manifest_dir / "episode-masters.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "project_id": "test-project",
                "status": "COMPLETED",
                "episode_count": 2,
                "episodes": [
                    {"episode_id": "S01E001", "human_review": {"status": "PENDING"}},
                    {"episode_id": "S01E002", "human_review": {"status": "PENDING"}},
                ],
                "human_review": {"required": True, "status": "PENDING"},
            }), encoding="utf-8")
            checks = {key: "PASS" for key in web_server.EPISODE_REVIEW_CHECKS}
            with self.assertRaisesRegex(ValueError, "reviewer is required"):
                web_server._update_episode_master_review(project, {"episode_id": "S01E001", "checks": checks})
            saved = web_server._update_episode_master_review(project, {"episode_id": "S01E001", "checks": checks, "reviewer": "测试审核员", "note": "首集通过"})
            self.assertEqual(saved["human_review"]["status"], "APPROVED")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["human_review"]["status"], "PENDING")
            change_checks = {key: ("CHANGES_REQUESTED" if key == "audio" else "PASS") for key in web_server.EPISODE_REVIEW_CHECKS}
            web_server._update_episode_master_review(project, {"episode_id": "S01E002", "checks": change_checks, "reviewer": "测试审核员"})
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["human_review"]["status"], "CHANGES_REQUESTED")

    def test_provider_motion_test_inventory_is_prepared_but_not_authorized(self):
        result = web_server._provider_motion_test_inventory(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(result["status"], "PREPARED")
        self.assertEqual(result["test_count"], 3)
        self.assertEqual({item["provider"] for item in result["tests"]}, {"runway", "wan", "openai_sora"})
        self.assertTrue(all(item["status"] == "BLOCKED_PENDING_AUTHORIZATION" for item in result["tests"]))
        self.assertTrue(all(item["start_frame_url"].startswith("/media/jinghua-yuan-series/") for item in result["tests"]))

    def test_final_shot_review_has_required_checks(self):
        review = web_server._final_shot_review(web_server._safe_project("jinghua-yuan-series"))
        self.assertIn(review["status"], {"PENDING", "APPROVED", "CHANGES_REQUESTED"})
        self.assertEqual(set(review["checks"]), {"sound", "subtitles", "mouth"})
        if review["status"] == "APPROVED":
            self.assertTrue(all(value == "PASS" for value in review["checks"].values()))

    def test_rig_coverage_only_counts_matching_character(self):
        coverage = web_server._rig_coverage(web_server._safe_project("jinghua-yuan-series"))
        self.assertEqual(coverage["covered_shot_count"], 16)
        self.assertEqual(coverage["total_shot_count"], 16)
        self.assertEqual(coverage["coverage_percent"], 100.0)
        self.assertNotIn("CHR-JHY-WUZETIAN", coverage["missing_character_ids"])
        self.assertEqual(coverage["missing_character_ids"], [])

    def test_arcreel_local_sidecar_is_reported_as_paused(self):
        web_server.RUNTIME_INTEGRATIONS.pop("arcreel", None)
        status = web_server._integration_status()[0]
        self.assertTrue(status["paused"])
        self.assertFalse(status["connected"])
        self.assertNotIn("api_key", status)

    def test_key_settings_endpoint_returns_status_without_secret(self):
        web_server.RUNTIME_KEYS.pop("openai_sora", None)
        server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.VideoCreatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/settings/keys"
            request = urllib.request.Request(url, data=json.dumps({"provider": "openai_sora", "key": "test-key-123456"}).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode())
            self.assertEqual(result, {"provider": "openai_sora", "configured": True, "source": "session"})
            self.assertNotIn("test-key-123456", json.dumps(result))
        finally:
            web_server.RUNTIME_KEYS.pop("openai_sora", None)
            server.shutdown()
            server.server_close()

    def test_arcreel_settings_endpoint_connects_without_exposing_token(self):
        class ArcReelHandler(web_server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):  # noqa: N802
                payload = {"status": "ok"} if self.path == "/health" else {"enabled": True}
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        arc_server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), ArcReelHandler)
        arc_thread = threading.Thread(target=arc_server.serve_forever, daemon=True)
        arc_thread.start()
        web_server.RUNTIME_INTEGRATIONS.pop("arcreel", None)
        server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.VideoCreatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/settings/integrations"
            body = {
                "integration": "arcreel",
                "base_url": f"http://127.0.0.1:{arc_server.server_port}",
                "api_key": "arc-test-secret",
            }
            request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode())
            self.assertTrue(result["configured"])
            self.assertTrue(result["connected"])
            self.assertTrue(result["auth_enabled"])
            self.assertEqual(result["license"], "AGPL-3.0")
            self.assertNotIn("arc-test-secret", json.dumps(result))
        finally:
            web_server.RUNTIME_INTEGRATIONS.pop("arcreel", None)
            server.shutdown()
            server.server_close()
            arc_server.shutdown()
            arc_server.server_close()


if __name__ == "__main__":
    unittest.main()
