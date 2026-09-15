import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.publish_policy import (
    PublishPolicyError,
    audit_publish_configuration,
    authorize_publish_action,
    record_confirmed_manual_publication,
)


class PublishPolicyTests(unittest.TestCase):
    def test_configuration_audit_enforces_human_only_mode(self):
        result = audit_publish_configuration()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))

    def test_all_four_automatic_publication_actions_are_forbidden(self):
        for action in (
            "wechat_auto_upload", "simulate_publish_click",
            "automatic_originality_declaration", "automatic_commercial_label",
        ):
            with self.subTest(action=action), self.assertRaisesRegex(PublishPolicyError, "V1 forbids"):
                authorize_publish_action(action)

    def test_unknown_publication_capability_is_denied(self):
        with self.assertRaisesRegex(PublishPolicyError, "unknown"):
            authorize_publish_action("schedule_publish")

    def test_manual_record_needs_user_confirmation_and_ready_state(self):
        with tempfile.TemporaryDirectory() as temp:
            project_id = "20260915-manual-publish"
            directory = Path(temp) / project_id
            directory.mkdir()
            project_state.initialize_run_state(directory, project_id)
            for stage in project_state.STAGES[1:project_state.STAGES.index("READY_FOR_REVIEW") + 1]:
                project_state.transition_project(directory, project_id, stage)
            with self.assertRaisesRegex(PublishPolicyError, "explicit user confirmation"):
                record_confirmed_manual_publication(directory, project_id, confirmed_by_user=False, confirmation_note="done")
            state = record_confirmed_manual_publication(
                directory, project_id, confirmed_by_user=True, confirmation_note="User confirmed manual upload"
            )
            self.assertEqual(state["status"], "PUBLISHED_MANUALLY")


if __name__ == "__main__":
    unittest.main()
