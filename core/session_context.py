"""
Shared session and progress context for RHCSA simulator modes.

The context stores active-session evidence without replacing ResultsDB.
ResultsDB remains responsible for durable history and SM-2 statistics.
"""

from copy import deepcopy
from datetime import datetime, timezone
import uuid


class SessionContext:
    """
    Common state for Learn, Practice, Adaptive, Exam and Challenge.

    Quick Practice is represented as:
        mode="practice"
        variant="quick_practice"
    """

    SCHEMA_VERSION = 1
    MODES = frozenset(
        {"learn", "practice", "adaptive", "exam", "challenge"}
    )

    def __init__(
        self,
        mode,
        session_id=None,
        vm_id=None,
        variant=None,
    ):
        normalized_mode = str(mode).lower()

        if normalized_mode not in self.MODES:
            raise ValueError(
                f"Unsupported simulator mode: {mode}"
            )

        self.schema_version = self.SCHEMA_VERSION
        self.session_id = session_id or uuid.uuid4().hex
        self.mode = normalized_mode
        self.variant = variant
        self.vm_id = vm_id

        self.started_at = self._now()
        self.finished_at = None

        # Study progression shared across modes.
        self.unlocked_chapters = []
        self.studied_objectives = []
        self.completed_task_ids = []

        # Current task and completed task evidence.
        self.current_task = None
        self.task_history = []

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _elapsed_seconds(started_at, finished_at):
        if not started_at or not finished_at:
            return None

        try:
            start = datetime.fromisoformat(started_at)
            finish = datetime.fromisoformat(finished_at)
            return max(0, int((finish - start).total_seconds()))
        except (TypeError, ValueError):
            return None

    def unlock_chapter(self, chapter):
        """Add a chapter to the unlocked study scope."""
        if chapter and chapter not in self.unlocked_chapters:
            self.unlocked_chapters.append(chapter)

    def mark_objective_studied(self, objective):
        """Record that an objective has been studied."""
        if objective and objective not in self.studied_objectives:
            self.studied_objectives.append(objective)

    def start_task(
        self,
        task_id,
        category=None,
        chapter=None,
        objective=None,
        task_source=None,
        vm_id=None,
    ):
        """
        Start collecting evidence for one task.

        A session can have only one active task at a time.
        """
        if self.current_task is not None:
            raise RuntimeError(
                "A task is already active in this session"
            )

        self.current_task = {
            "task_id": task_id,
            "category": category,
            "chapter": chapter,
            "objective": objective,
            "task_source": task_source,
            "vm_id": vm_id or self.vm_id,
            "started_at": self._now(),
            "finished_at": None,
            "elapsed_seconds": None,
            "attempts": 0,
            "hints_used": 0,
            "hint_events": [],
            "attempt_log": [],
            "result": None,
        }

        return deepcopy(self.current_task)

    def record_hint(self, hint_type=None):
        """Record one hint or solution aid used during the active task."""
        if self.current_task is None:
            raise RuntimeError("No active task")

        event = {
            "type": hint_type,
            "at": self._now(),
        }

        self.current_task["hints_used"] += 1
        self.current_task["hint_events"].append(event)

    def record_attempt(
        self,
        passed=False,
        score=None,
        max_score=None,
        elapsed_seconds=None,
    ):
        """Record one validation attempt for the active task."""
        if self.current_task is None:
            raise RuntimeError("No active task")

        attempt = {
            "attempt": self.current_task["attempts"] + 1,
            "passed": bool(passed),
            "score": score,
            "max_score": max_score,
            "elapsed_seconds": elapsed_seconds,
            "at": self._now(),
        }

        self.current_task["attempts"] += 1
        self.current_task["attempt_log"].append(attempt)

        return deepcopy(attempt)

    def finish_task(
        self,
        passed=False,
        score=None,
        max_score=None,
        persistence_passed=None,
        elapsed_seconds=None,
    ):
        """
        Finish the active task and move its evidence to task_history.
        """
        if self.current_task is None:
            raise RuntimeError("No active task")

        finished_at = self._now()
        task = self.current_task
        task["finished_at"] = finished_at

        if elapsed_seconds is None:
            elapsed_seconds = self._elapsed_seconds(
                task["started_at"],
                finished_at,
            )

        task["elapsed_seconds"] = elapsed_seconds
        task["result"] = {
            "passed": bool(passed),
            "score": score,
            "max_score": max_score,
            "persistence_passed": persistence_passed,
        }

        self.task_history.append(deepcopy(task))

        task_id = task.get("task_id")
        if task_id and task_id not in self.completed_task_ids:
            self.completed_task_ids.append(task_id)

        self.current_task = None
        return deepcopy(task)

    def finish_session(self):
        """Mark the session as finished."""
        if self.finished_at is None:
            self.finished_at = self._now()

    def to_dict(self):
        """Return a JSON-serializable snapshot of this context."""
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "mode": self.mode,
            "variant": self.variant,
            "vm_id": self.vm_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "unlocked_chapters": list(self.unlocked_chapters),
            "studied_objectives": list(self.studied_objectives),
            "completed_task_ids": list(self.completed_task_ids),
            "current_task": deepcopy(self.current_task),
            "task_history": deepcopy(self.task_history),
        }

    @classmethod
    def from_dict(cls, data):
        """Reconstruct a context from a serialized snapshot."""
        if not isinstance(data, dict):
            raise TypeError("Session context must be a dictionary")

        context = cls(
            mode=data.get("mode"),
            session_id=data.get("session_id"),
            vm_id=data.get("vm_id"),
            variant=data.get("variant"),
        )

        context.schema_version = data.get(
            "schema_version",
            cls.SCHEMA_VERSION,
        )
        context.started_at = data.get(
            "started_at",
            context.started_at,
        )
        context.finished_at = data.get("finished_at")
        context.unlocked_chapters = list(
            data.get("unlocked_chapters", [])
        )
        context.studied_objectives = list(
            data.get("studied_objectives", [])
        )
        context.completed_task_ids = list(
            data.get("completed_task_ids", [])
        )
        context.current_task = deepcopy(
            data.get("current_task")
        )
        context.task_history = deepcopy(
            data.get("task_history", [])
        )

        return context
