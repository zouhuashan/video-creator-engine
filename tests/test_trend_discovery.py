import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import trend_discovery


def signal(signal_id, *, topic="AI assistants", source_name="Example", observed_at="2026-09-16T00:00:00Z", strength=80, **extra):
    return {
        "signal_id": signal_id,
        "topic": topic,
        "title": f"{topic} update",
        "source_name": source_name,
        "observed_at": observed_at,
        "strength": strength,
        **extra,
    }


class TrendDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def source(self, source_type, records):
        path = self.directory / f"{source_type}-{len(list(self.directory.glob('*.json')))}.json"
        path.write_text(json.dumps({"schema_version": 1, "signals": records}), encoding="utf-8")
        return trend_discovery.JsonFileTrendSource(source_type, path)

    def test_local_adapters_cover_all_five_categories_and_preserve_provenance(self):
        sources = [
            self.source(source_type, [signal(source_type, source_name=f"Publisher {index}")])
            for index, source_type in enumerate(trend_discovery.SOURCE_TYPES)
        ]
        result = trend_discovery.discover_trends(
            sources, run_date="2026-09-16", collected_at="2026-09-16T10:00:00Z"
        )
        self.assertEqual(result["source_types"], sorted(trend_discovery.SOURCE_TYPES))
        self.assertEqual(result["stats"], {"signals_received": 5, "signals_accepted": 5, "duplicates_removed": 0})
        self.assertEqual({item["source_type"] for item in result["signals"]}, set(trend_discovery.SOURCE_TYPES))
        self.assertEqual(
            {item["source_type"]: item["source_name"] for item in result["signals"]},
            {source_type: f"Publisher {index}" for index, source_type in enumerate(trend_discovery.SOURCE_TYPES)},
        )

    def test_duplicate_content_collapses_but_duplicate_ids_are_rejected(self):
        sources = [
            self.source("search_trend", [signal("old", strength=52)]),
            self.source("search_trend", [signal("new", observed_at="2026-09-16T00:30:00Z", strength=91)]),
        ]
        result = trend_discovery.discover_trends(sources, run_date="2026-09-16", collected_at="2026-09-16T10:00:00Z")
        self.assertEqual(result["stats"]["duplicates_removed"], 1)
        self.assertEqual(result["signals"][0]["signal_id"], "new")
        duplicate_id_sources = [
            self.source("community", [signal("same")]),
            self.source("community", [signal("same", source_name="Other")]),
        ]
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "duplicate signal_id"):
            trend_discovery.discover_trends(duplicate_id_sources, run_date="2026-09-16")

    def test_invalid_strength_timezone_url_and_adapter_type_are_rejected(self):
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "strength"):
            trend_discovery.normalize_signal(signal("bad", strength=True), "community")
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "timezone"):
            trend_discovery.normalize_signal(signal("bad", observed_at="2026-09-16T08:00:00"), "community")
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "credentials"):
            trend_discovery.normalize_signal(signal("bad", url="https://user:secret@example.com"), "community")
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "does not match"):
            trend_discovery.normalize_signal(signal("bad", source_type="community"), "search_trend")

    def test_user_comment_schema_does_not_accept_author_metadata(self):
        with self.assertRaisesRegex(trend_discovery.TrendDiscoveryError, "unsupported fields"):
            trend_discovery.normalize_signal(signal("comment", author="private-user"), "user_comment")

    def test_cli_writes_dated_artifact_and_refuses_to_overwrite(self):
        source_path = self.directory / "source.json"
        source_path.write_text(json.dumps([signal("s1")]), encoding="utf-8")
        output_dir = self.directory / "out"
        command = [
            sys.executable, str(ROOT / "scripts" / "trend_discovery.py"),
            "--source", f"community={source_path}", "--date", "2026-09-16",
            "--output-dir", str(output_dir),
        ]
        first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        output = output_dir / "2026-09-16.json"
        self.assertTrue(output.exists())
        second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("refusing to overwrite", second.stderr)


if __name__ == "__main__":
    unittest.main()
