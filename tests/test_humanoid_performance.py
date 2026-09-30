import json

import pytest

from scripts.humanoid_performance import RELATIVE_DIR, REVIEW_CHECKS, review, status


def _ready_project(tmp_path):
    output = tmp_path / RELATIVE_DIR
    output.mkdir(parents=True)
    (output / "performance.mp4").write_bytes(b"video")
    (output / "poster.png").write_bytes(b"poster")
    (output / "performance.blend").write_bytes(b"blend")
    (output / "performance-report.json").write_text(
        json.dumps(
            {
                "human_review": "PENDING",
                "performance": {"contact_pass": True},
                "technical_qc": {"video_sha256": "abc"},
            }
        ),
        encoding="utf-8",
    )
    assets = tmp_path / "production/assets/characters/makehuman-system-cc0"
    assets.mkdir(parents=True)
    (assets / "asset-manifest.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_pass_requires_every_visual_check(tmp_path):
    project = _ready_project(tmp_path)
    checks = {name: True for name in REVIEW_CHECKS}
    checks["hand_pose"] = False
    with pytest.raises(ValueError, match="勾选全部"):
        review(project, {"decision": "PASS", "checks": checks, "notes": ""})
    assert status(project)["can_expand"] is False


def test_reject_preserves_notes_and_keeps_expansion_locked(tmp_path):
    project = _ready_project(tmp_path)
    result = review(
        project,
        {
            "decision": "REJECTED",
            "checks": {name: name != "facial_expression" for name in REVIEW_CHECKS},
            "notes": "表情仍然僵硬",
        },
    )
    assert result["human_review"] == "REJECTED"
    assert result["review"]["notes"] == "表情仍然僵硬"
    assert result["can_expand"] is False
    assert list((project / RELATIVE_DIR / "reviews").glob("*-rejected.json"))


def test_pass_unlocks_only_after_contact_and_all_checks(tmp_path):
    project = _ready_project(tmp_path)
    result = review(
        project,
        {"decision": "PASS", "checks": {name: True for name in REVIEW_CHECKS}, "notes": "可以继续"},
    )
    assert result["human_review"] == "PASS"
    assert result["can_expand"] is True
    saved = json.loads((project / RELATIVE_DIR / "performance-report.json").read_text(encoding="utf-8"))
    assert saved["expansion_allowed"] is True
    assert saved["human_review"]["reviewed_by"] == "WEB_HUMAN"
