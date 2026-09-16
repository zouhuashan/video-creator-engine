import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_anime_runtime import NovelAnimeRuntime, NovelAnimeRuntimeError
from scripts.novel_source_catalog import build_catalog, write_catalog


class NovelAnimeRuntimeTests(unittest.TestCase):
    def make_runtime(self, root: Path) -> NovelAnimeRuntime:
        project_dir = root / "jinghua-yuan-series"
        write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
        NovelAnimeRepository(project_dir).initialize()
        runtime = NovelAnimeRuntime(project_dir)
        runtime.initialize()
        return runtime

    def test_idempotent_job_is_claimed_completed_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            first = runtime.submit_job("VALIDATE_PROJECT", "jinghua-yuan-series", idempotency_key="validate-v1")
            duplicate = runtime.submit_job("VALIDATE_PROJECT", "jinghua-yuan-series", idempotency_key="validate-v1")
            self.assertEqual(first["job_id"], duplicate["job_id"])
            result = runtime.work_once("worker-1")
            jobs = runtime.list_jobs()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["result"]["episodes"], 5)
        self.assertEqual(jobs[0]["attempts"], 1)

    def test_entity_lock_serializes_jobs_for_same_target(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            runtime.submit_job("IMPACT_ANALYSIS", "IP-JHY")
            runtime.submit_job("IMPACT_ANALYSIS", "IP-JHY")
            first = runtime.claim_job("worker-a")
            blocked = runtime.claim_job("worker-b")
            self.assertIsNone(blocked)
            runtime.complete_job(first["job_id"], "worker-a", {})
            second = runtime.claim_job("worker-b")
        self.assertIsNotNone(second)
        self.assertNotEqual(first["job_id"], second["job_id"])

    def test_failure_retries_then_stops_and_cancel_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            job = runtime.submit_job("UNKNOWN_HANDLER", "IP-JHY", max_attempts=2)
            claimed = runtime.claim_job("worker")
            retried = runtime.fail_job(claimed["job_id"], "worker", "first failure")
            self.assertEqual(retried["status"], "RETRY_WAIT")
            claimed = runtime.claim_job("worker")
            failed = runtime.fail_job(claimed["job_id"], "worker", "second failure")
            self.assertEqual(failed["status"], "FAILED")
            cancel_target = runtime.submit_job("IMPACT_ANALYSIS", "S01E001")
            running = runtime.claim_job("worker")
            canceled = runtime.cancel_job(running["job_id"])
            stats = runtime.stats()
        self.assertEqual(canceled["status"], "CANCELED")
        self.assertEqual(stats["locks"], 0)
        self.assertEqual(cancel_target["job_id"], canceled["job_id"])

    def test_stale_worker_lease_recovers_job(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            runtime.submit_job("IMPACT_ANALYSIS", "IP-JHY")
            claimed = runtime.claim_job("dead-worker", lease_seconds=10)
            with runtime._connect() as connection:
                connection.execute("UPDATE entity_locks SET lease_expires_at = '2000-01-01T00:00:00.000Z' WHERE job_id = ?", (claimed["job_id"],))
            recovered = runtime.recover_stale()
            job = runtime.list_jobs()[0]
        self.assertEqual(recovered, [claimed["job_id"]])
        self.assertEqual(job["status"], "QUEUED")

    def test_state_transition_requires_matching_approved_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            with self.assertRaisesRegex(NovelAnimeRuntimeError, "source catalog"):
                runtime.transition("IP-JHY", "SOURCE_READY", "source checked")
            catalog = build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘")
            catalog["status"] = "LICENSED"
            catalog["rights_assessment"].update({
                "status": "LICENSED", "basis": "runtime test license", "jurisdictions": ["test"],
                "territories": ["CN"], "publication_allowed": True,
                "human_review": {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test fixture"},
                "evidence": [{"id": "EVD-JHY-001", "type": "license", "title": "test license", "url": "https://example.org/license", "accessed_at": "2026-09-16", "note": "test fixture"}],
            })
            catalog["adaptation_policy"].update({"script_adaptation_allowed": True, "publication_allowed": True})
            write_catalog(runtime.project_dir, catalog)
            with self.assertRaisesRegex(NovelAnimeRuntimeError, "source_rights"):
                runtime.transition("IP-JHY", "SOURCE_READY", "source checked")
            runtime.record_review("IP-JHY", "source_rights", "APPROVED", "human-reviewer", "local test approval")
            transition = runtime.transition("IP-JHY", "SOURCE_READY", "source checked")
            runtime.record_review("IP-JHY", "story_bible", "APPROVED", "human-reviewer", "local test approval")
            with self.assertRaisesRegex(NovelAnimeRuntimeError, "valid story bible"):
                runtime.transition("IP-JHY", "BIBLE_READY", "bible checked")
            with self.assertRaisesRegex(NovelAnimeRuntimeError, "expected BIBLE_READY"):
                runtime.transition("IP-JHY", "WRITING_READY", "skip")
        self.assertEqual(transition["revision"], 2)
        self.assertEqual(transition["to_status"], "SOURCE_READY")

    def test_rerun_queues_root_and_all_downstream_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.make_runtime(Path(directory))
            jobs = runtime.queue_rerun("IP-JHY", "IP metadata changed")
        self.assertEqual(len(jobs), 8)
        self.assertEqual({job["target_id"] for job in jobs}, {"IP-JHY", "SER-JHY-01", "S01", *{f"S01E{index:03d}" for index in range(1, 6)}})
        self.assertTrue(all(job["status"] == "QUEUED" for job in jobs))

    def test_legacy_pilot_migration_is_local_versioned_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = self.make_runtime(root)
            legacy = root / "legacy"
            for index in range(1, 6):
                output = legacy / "episodes" / f"episode-{index:02d}" / "final.mp4"
                output.parent.mkdir(parents=True)
                output.write_bytes(f"episode-{index}".encode())
            first = runtime.migrate_legacy_pilot(legacy)
            second = runtime.migrate_legacy_pilot(legacy)
            stats = runtime.repository.stats()
        self.assertEqual(len(first["assets"]), 5)
        self.assertFalse(first["publication_allowed"])
        self.assertTrue(second["reused"])
        self.assertEqual(stats["asset_versions"], 5)


if __name__ == "__main__":
    unittest.main()
