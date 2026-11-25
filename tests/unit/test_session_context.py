"""
Tests for the shared session and progress context.
"""

import json

import pytest

from core.session_context import SessionContext


def test_context_initializes_with_valid_mode():
    context = SessionContext("practice")

    assert context.mode == "practice"
    assert context.variant is None
    assert context.session_id
    assert context.started_at
    assert context.finished_at is None
    assert context.current_task is None
    assert context.task_history == []


def test_quick_practice_uses_practice_mode_variant():
    context = SessionContext(
        mode="practice",
        variant="quick_practice",
    )

    assert context.mode == "practice"
    assert context.variant == "quick_practice"


def test_context_tracks_chapters_and_objectives():
    context = SessionContext("learn")

    context.unlock_chapter("Storage")
    context.unlock_chapter("Storage")
    context.mark_objective_studied("Create LVM logical volumes")
    context.mark_objective_studied("Create LVM logical volumes")

    assert context.unlocked_chapters == ["Storage"]
    assert context.studied_objectives == [
        "Create LVM logical volumes"
    ]


def test_context_records_task_hints_attempts_and_result():
    context = SessionContext(
        mode="practice",
        vm_id="EXAM01",
    )

    context.start_task(
        task_id="lvm_001",
        category="lvm",
        chapter="Storage",
        objective="Create LVM logical volumes",
        task_source="sander_van_vugt",
    )
    context.record_hint("syntax")
    context.record_attempt(
        passed=False,
        score=4,
        max_score=10,
        elapsed_seconds=45,
    )
    context.record_attempt(
        passed=True,
        score=10,
        max_score=10,
        elapsed_seconds=60,
    )

    result = context.finish_task(
        passed=True,
        score=10,
        max_score=10,
        persistence_passed=True,
        elapsed_seconds=120,
    )

    assert result["task_id"] == "lvm_001"
    assert result["category"] == "lvm"
    assert result["task_source"] == "sander_van_vugt"
    assert result["vm_id"] == "EXAM01"
    assert result["hints_used"] == 1
    assert result["attempts"] == 2
    assert result["result"]["passed"] is True
    assert result["result"]["persistence_passed"] is True
    assert context.current_task is None
    assert context.completed_task_ids == ["lvm_001"]
    assert len(context.task_history) == 1


def test_context_rejects_two_active_tasks():
    context = SessionContext("practice")

    context.start_task("task_001")

    with pytest.raises(RuntimeError, match="already active"):
        context.start_task("task_002")


def test_context_rejects_evidence_without_active_task():
    context = SessionContext("practice")

    with pytest.raises(RuntimeError, match="No active task"):
        context.record_hint("syntax")

    with pytest.raises(RuntimeError, match="No active task"):
        context.record_attempt()

    with pytest.raises(RuntimeError, match="No active task"):
        context.finish_task()


def test_context_round_trip_is_json_serializable():
    context = SessionContext(
        mode="practice",
        variant="quick_practice",
        vm_id="EXAM01",
    )
    context.unlock_chapter("Users and groups")
    context.start_task(
        task_id="users_001",
        category="users_groups",
        chapter="Users and groups",
        objective="Create users",
        task_source="official_rhcsa",
    )
    context.record_attempt(
        passed=True,
        score=10,
        max_score=10,
        elapsed_seconds=30,
    )
    context.finish_task(
        passed=True,
        score=10,
        max_score=10,
        elapsed_seconds=30,
    )
    context.finish_session()

    snapshot = context.to_dict()
    encoded = json.dumps(snapshot)
    restored = SessionContext.from_dict(json.loads(encoded))

    assert restored.session_id == context.session_id
    assert restored.mode == "practice"
    assert restored.variant == "quick_practice"
    assert restored.vm_id == "EXAM01"
    assert restored.unlocked_chapters == ["Users and groups"]
    assert restored.completed_task_ids == ["users_001"]
    assert len(restored.task_history) == 1
    assert restored.finished_at is not None


def test_context_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unsupported simulator mode"):
        SessionContext("unsupported")
