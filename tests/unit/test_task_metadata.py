"""
Tests for task mode and provenance metadata.
"""

import pytest

from tasks.base import SimpleTask
from tasks.registry import TaskRegistry


class ChallengeTask(SimpleTask):
    exam_eligible = False
    challenge_only = True
    task_source = "original_challenge"
    chapter = "Mixed administration"
    objective = "Troubleshooting and combined tasks"


class OfficialTask(SimpleTask):
    exam_eligible = True
    challenge_only = False
    task_source = "official_rhcsa"


def test_base_task_metadata_defaults():
    task = SimpleTask(
        id="metadata_default_001",
        category="testing",
        difficulty="easy",
        points=5,
    )

    assert task.exam_eligible is True
    assert task.challenge_only is False
    assert task.task_source == "official_rhcsa"
    assert task.chapter is None
    assert task.objective is None


def test_base_task_metadata_is_exported():
    task = SimpleTask(
        id="metadata_export_001",
        category="testing",
        difficulty="easy",
        points=5,
    )

    data = task.to_dict()

    assert data["exam_eligible"] is True
    assert data["challenge_only"] is False
    assert data["task_source"] == "official_rhcsa"
    assert data["chapter"] is None
    assert data["objective"] is None


def test_challenge_task_can_override_mode_metadata():
    task = ChallengeTask(
        id="challenge_metadata_001",
        category="testing",
        difficulty="challenge",
        points=10,
    )

    data = task.to_dict()

    assert task.exam_eligible is False
    assert task.challenge_only is True
    assert data["task_source"] == "original_challenge"
    assert data["chapter"] == "Mixed administration"
    assert data["objective"] == "Troubleshooting and combined tasks"


def test_official_task_is_allowed_in_official_modes():
    for mode in ("learn", "practice", "adaptive", "exam"):
        assert TaskRegistry._mode_allows(OfficialTask, mode) is True


def test_challenge_task_is_allowed_only_in_challenge():
    for mode in ("learn", "practice", "adaptive", "exam"):
        assert TaskRegistry._mode_allows(ChallengeTask, mode) is False

    assert TaskRegistry._mode_allows(ChallengeTask, "challenge") is True


def test_official_task_is_not_allowed_in_challenge():
    assert TaskRegistry._mode_allows(OfficialTask, "challenge") is False


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="Unknown simulator mode"):
        TaskRegistry._mode_allows(OfficialTask, "unsupported")
