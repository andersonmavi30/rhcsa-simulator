"""
Base task class for all RHCSA EX200 v10 exam tasks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import logging

from config import settings


logger = logging.getLogger(__name__)


class BaseTask(ABC):
    """
    Abstract base class for all RHCSA exam tasks.

    All task categories must inherit from this class and implement
    the generate() and validate() methods.
    """

    # Number of whole practice disks this task consumes (0 = none). The exam
    # generator caps the number of disk tasks to the size of the device pool and
    # hands each one a distinct device so they never collide on the same disk.
    disk_slots = 0

    # True if this task establishes a negative precondition at exam start so
    # the candidate must actually do the work.
    has_setup = False

    # Packages this task's fault injection or scenario needs.
    required_packages = []

    # Exam versions this task is in scope for. None means both versions.
    exam_versions = None

    # True for tasks performed on the linked second lab machine.
    requires_lab_machine = False

    # True for tasks that mount or automount from a real NFS server.
    requires_nfs_server = False

    # Mode and provenance metadata.
    #
    # exam_eligible:
    #   The task may appear in Practice, Adaptive and Exam.
    #
    # challenge_only:
    #   The task may appear only in Challenge.
    #
    # task_source:
    #   Educational or functional origin of the task.
    #
    # chapter:
    #   Book or study chapter associated with the task.
    #
    # objective:
    #   RHCSA objective associated with the task.
    #
    # These are class attributes so individual task classes can override them
    # without changing every task constructor.
    exam_eligible = True
    challenge_only = False
    task_source = "official_rhcsa"
    chapter = None
    objective = None

    def __init__(self, id, category, difficulty, points):
        self.id = id
        self.category = category
        self.difficulty = difficulty
        self.points = points
        self.description = ""
        self.hints = []
        self.params = {}

        # v4.0.0 additions
        self.exam_domain = settings.CATEGORY_TO_DOMAIN.get(category, 0)
        self.requires_persistence = False
        self.persistence_checks = []
        self.exam_tips = []
        self.prerequisites = []
        self.tags = []
        self.task_order = None
        self.requires_reboot = False

    @abstractmethod
    def generate(self, **params):
        """Generate task with randomized parameters. Returns self."""
        pass

    @abstractmethod
    def validate(self):
        """Validate task completion. Returns ValidationResult."""
        pass

    def provision_devices(self):
        """Re-bind this task to freshly allocated practice devices."""
        if self.disk_slots:
            self.generate()

    def setup_environment(self):
        """Establish the negative precondition for this task at exam start."""
        return True, "no setup needed"

    def teardown_environment(self):
        """Restore whatever setup_environment() changed."""
        from tasks import env_setup
        return env_setup.restore_and_clear(self.id)

    def validate_persistence(self):
        """
        Validate that task results survive a reboot.
        """
        return self.validate()

    def get_description(self):
        return self.description

    def get_hints(self):
        return self.hints

    def get_category_display_name(self):
        from utils.formatters import format_category_name
        return format_category_name(self.category)

    def get_difficulty_display(self):
        from utils.formatters import format_difficulty
        return format_difficulty(self.difficulty)

    def get_domain_display(self):
        return settings.EXAM_DOMAINS.get(self.exam_domain, "Unknown")

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "difficulty": self.difficulty,
            "points": self.points,
            "description": self.description,
            "hints": self.hints,
            "exam_domain": self.exam_domain,
            "requires_persistence": self.requires_persistence,
            "tags": self.tags,
            "exam_tips": self.exam_tips,
            "exam_eligible": getattr(self, "exam_eligible", True),
            "challenge_only": getattr(self, "challenge_only", False),
            "task_source": getattr(self, "task_source", "official_rhcsa"),
            "chapter": getattr(self, "chapter", None),
            "objective": getattr(self, "objective", None),
        }

    def __repr__(self):
        return (
            f"<Task {self.id}: {self.category} "
            f"({self.difficulty}, {self.points}pts, D{self.exam_domain})>"
        )


class SimpleTask(BaseTask):
    """Non-abstract implementation for quick task creation."""

    def __init__(
        self,
        id,
        category,
        difficulty,
        points,
        description="",
        validation_func=None,
    ):
        super().__init__(id, category, difficulty, points)
        self.description = description
        self._validation_func = validation_func

    def generate(self, **params):
        return self

    def validate(self):
        if self._validation_func:
            return self._validation_func()

        from core.validator import ValidationResult

        return ValidationResult(
            task_id=self.id,
            passed=False,
            score=0,
            max_score=self.points,
            error_message="No validation function provided",
        )
