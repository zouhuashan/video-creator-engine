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
            web_server._safe_project_file("jinghua-yuan-local-pilot", "../../.env.example")

    def test_project_file_resolves_known_asset(self):
        path = web_server._safe_project_file("jinghua-yuan-local-pilot", "assets/characters/tang-xiaoshan-portrait.png")
        self.assertTrue(path.is_file())

    def test_project_detail_exposes_local_episode_manifests(self):
        episodes = web_server._episode_metadata(web_server._safe_project("jinghua-yuan-local-pilot"))
        self.assertEqual([episode["episode_id"] for episode in episodes], [f"episode-{index:02d}" for index in range(1, 6)])
        self.assertTrue(all(str(episode["media_url"]).endswith("/final.mp4") for episode in episodes))

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

    def test_web_entrypoints_are_tracked_assets(self):
        self.assertTrue((web_server.WEB_ROOT / "index.html").is_file())
        self.assertTrue((web_server.WEB_ROOT / "app.js").is_file())
        self.assertTrue((web_server.WEB_ROOT / "styles.css").is_file())

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


if __name__ == "__main__":
    unittest.main()
