"""
Task registry system for RHCSA Simulator v4.0.0
Auto-discovers task modules using pkgutil.iter_modules().
"""

import random
import logging
import pkgutil
import importlib
from collections import defaultdict
from typing import List, Optional

from config import settings


logger = logging.getLogger(__name__)


class TaskRegistry:
    """Central registry for all task classes using auto-discovery."""

    _instance = None
    _tasks = defaultdict(list)
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, category):
        """Decorator to register task classes."""

        def wrapper(task_class):
            cls._tasks[category].append(task_class)
            logger.debug(
                f"Registered task: {task_class.__name__} in category {category}"
            )
            return task_class

        return wrapper

    @classmethod
    def get_all_categories(cls):
        return list(cls._tasks.keys())

    @classmethod
    def get_tasks_by_category(cls, category):
        return cls._tasks.get(category, [])

    @classmethod
    def get_tasks_by_domain(cls, domain_number):
        """Get all task classes for a given exam domain (1-9)."""
        domain_categories = [
            cat
            for cat, dom in settings.CATEGORY_TO_DOMAIN.items()
            if dom == domain_number
        ]

        tasks = []
        for cat in domain_categories:
            tasks.extend(cls._tasks.get(cat, []))

        return tasks

    @classmethod
    def get_tasks_by_mode(cls, mode):
        """
        Return task classes allowed for a simulator mode.

        Learn, Practice, Adaptive and Exam use the official task bank.
        Challenge uses only tasks explicitly marked challenge_only.
        """
        results = []

        for category_tasks in cls._tasks.values():
            for task_class in category_tasks:
                if cls._mode_allows(task_class, mode):
                    results.append(task_class)

        return results

    @staticmethod
    def _mode_allows(task_class, mode):
        """
        Return whether a task class is allowed in the requested mode.

        The metadata is defined on BaseTask and may be overridden by an
        individual task class.
        """
        if mode is None:
            return True

        normalized = str(mode).lower()

        challenge_only = bool(
            getattr(task_class, "challenge_only", False)
        )
        exam_eligible = bool(
            getattr(task_class, "exam_eligible", True)
        )

        if normalized == "challenge":
            return challenge_only

        if normalized in {"practice", "adaptive", "exam"}:
            return exam_eligible and not challenge_only

        if normalized == "learn":
            return not challenge_only

        raise ValueError(f"Unknown simulator mode: {mode}")

    @classmethod
    def get_persistence_tasks(cls):
        """Get all task classes that require persistence validation."""
        results = []

        for category_tasks in cls._tasks.values():
            for task_class in category_tasks:
                try:
                    instance = task_class()
                    if instance.requires_persistence:
                        results.append(task_class)
                except Exception:
                    pass

        return results

    @classmethod
    def get_tasks_by_tag(cls, tag):
        """Get all task classes with a specific tag."""
        results = []

        for category_tasks in cls._tasks.values():
            for task_class in category_tasks:
                try:
                    instance = task_class()
                    if tag in instance.tags:
                        results.append(task_class)
                except Exception:
                    pass

        return results

    @classmethod
    def get_task_count(cls, category=None):
        if category:
            return len(cls._tasks.get(category, []))

        return sum(len(tasks) for tasks in cls._tasks.values())

    @classmethod
    def in_scope(cls, task_class, version=None):
        """
        True if this task belongs to the exam version being simulated.

        Two gates are used:

        1. The category must be in scope.
        2. The task's own exam_versions must allow the version.

        A task out of scope must never be drawn.
        """
        version = (
            version
            if version is not None
            else settings.get_exam_version()
        )

        allowed = getattr(task_class, "exam_versions", None)
        if allowed is not None and version not in allowed:
            return False

        category = getattr(task_class, "category", None)

        if category is None:
            try:
                category = task_class().category
            except Exception:
                return True

        return settings.category_in_scope(category, version)

    @classmethod
    def categories_in_scope(cls, version=None):
        """Registered categories that this exam version actually tests."""
        return [
            category
            for category in cls._tasks
            if settings.category_in_scope(category, version)
        ]

    @classmethod
    def get_random_task(
        cls,
        category=None,
        difficulty=None,
        skip_reboot=False,
        mode=None,
    ):
        """
        Return one generated task matching the requested filters.

        mode may be practice, adaptive, exam, challenge or learn.
        None preserves the historical unrestricted behavior.
        """
        if category:
            if not settings.category_in_scope(category):
                return None

            task_classes = cls._tasks.get(category, [])
        else:
            task_classes = []

            for category_name in cls.categories_in_scope():
                task_classes.extend(
                    cls._tasks.get(category_name, [])
                )

        if not task_classes:
            return None

        # Drop tasks outside the active exam version.
        task_classes = [
            task_class
            for task_class in task_classes
            if cls.in_scope(task_class)
        ]

        if not task_classes:
            return None

        # Apply the mode boundary before generating a task.
        task_classes = [
            task_class
            for task_class in task_classes
            if cls._mode_allows(task_class, mode)
        ]

        if not task_classes:
            return None

        # Remote tasks are only offered when a lab machine is linked.
        if any(
            getattr(task_class, "requires_lab_machine", False)
            for task_class in task_classes
        ):
            try:
                from core import lab_machine

                linked = bool(lab_machine.get_host())
            except Exception:
                linked = False

            if not linked:
                task_classes = [
                    task_class
                    for task_class in task_classes
                    if not getattr(
                        task_class,
                        "requires_lab_machine",
                        False,
                    )
                ]

                if not task_classes:
                    return None

        # NFS tasks are only offered once a real NFS server is configured.
        if any(
            getattr(task_class, "requires_nfs_server", False)
            for task_class in task_classes
        ):
            try:
                from core import nfs_server

                has_server = bool(nfs_server.load_config())
            except Exception:
                has_server = False

            if not has_server:
                task_classes = [
                    task_class
                    for task_class in task_classes
                    if not getattr(
                        task_class,
                        "requires_nfs_server",
                        False,
                    )
                ]

                if not task_classes:
                    return None

        # Tasks flagged as bad are never offered in any mode.
        try:
            from core import task_flags

            bad_ids = task_flags.flagged_ids()
        except Exception:
            bad_ids = set()

        if bad_ids:
            kept = []

            for task_class in task_classes:
                try:
                    if task_class().id not in bad_ids:
                        kept.append(task_class)
                except Exception:
                    kept.append(task_class)

            task_classes = kept

            if not task_classes:
                return None

        # Filter by difficulty.
        if difficulty:
            filtered = []

            for task_class in task_classes:
                try:
                    instance = task_class()

                    if instance.difficulty == difficulty:
                        filtered.append(task_class)
                except Exception:
                    pass

            if filtered:
                task_classes = filtered

        # Filter out tasks that require reboots.
        if skip_reboot:
            no_reboot = []

            for task_class in task_classes:
                try:
                    instance = task_class()

                    if not instance.requires_reboot:
                        no_reboot.append(task_class)
                except Exception:
                    pass

            if no_reboot:
                task_classes = no_reboot

        if not task_classes:
            return None

        task_class = random.choice(task_classes)

        try:
            task = task_class()
            task.generate()
            return task
        except Exception as exc:
            logger.error(
                f"Error creating task from "
                f"{task_class.__name__}: {exc}"
            )
            return None

    @classmethod
    def get_random_tasks(
        cls,
        count,
        categories=None,
        difficulty=None,
        exclude_ids=None,
        skip_reboot=False,
        mode=None,
    ):
        """
        Return multiple generated tasks matching the requested filters.
        """
        tasks = []
        exclude_ids = exclude_ids or []
        attempts = 0
        max_attempts = count * 10

        if categories:
            available_categories = [
                category
                for category in categories
                if category in cls._tasks
                and settings.category_in_scope(category)
            ]
        else:
            available_categories = cls.categories_in_scope()

        if not available_categories:
            return []

        while len(tasks) < count and attempts < max_attempts:
            attempts += 1

            category = available_categories[
                len(tasks) % len(available_categories)
            ]

            task = cls.get_random_task(
                category=category,
                difficulty=difficulty,
                skip_reboot=skip_reboot,
                mode=mode,
            )

            if task and task.id not in exclude_ids:
                tasks.append(task)
                exclude_ids.append(task.id)

        return tasks

    @classmethod
    def get_exam_tasks(cls, count=None):
        if count is None:
            count = settings.DEFAULT_EXAM_TASKS

        return cls.get_random_tasks(
            count,
            difficulty="exam",
            mode="exam",
        )

    @classmethod
    def generate_exam(cls, count=12, disk_budget=None):
        """
        Generate a balanced exam across all 8 domains.

        Persistence tasks are weighted according to the existing exam
        configuration. Disk tasks are capped by the available disk budget.
        """
        tasks = []
        exclude_ids = []

        if disk_budget is None:
            try:
                from utils.helpers import (
                    loop_device_capacity,
                    get_spare_real_disks,
                )

                disk_budget = (
                    loop_device_capacity()
                    + len(get_spare_real_disks())
                )
            except Exception:
                disk_budget = 0

            disk_budget = max(disk_budget, 3)

        from config.exam_objectives import get_objectives

        exam_objectives = get_objectives()
        total_weight = sum(
            data["weight"]
            for data in exam_objectives.values()
        )

        domain_counts = {}
        remaining = count

        for domain_number in sorted(exam_objectives.keys()):
            weight = exam_objectives[domain_number]["weight"]
            domain_counts[domain_number] = max(
                1,
                round(count * weight / total_weight),
            )
            remaining -= domain_counts[domain_number]

        while remaining > 0:
            for domain_number in sorted(
                domain_counts,
                key=lambda item: domain_counts[item],
            ):
                if remaining <= 0:
                    break

                domain_counts[domain_number] += 1
                remaining -= 1

        while sum(domain_counts.values()) > count:
            trimmed = False

            for domain_number in sorted(
                domain_counts,
                key=lambda item: -domain_counts[item],
            ):
                if sum(domain_counts.values()) <= count:
                    break

                if domain_counts[domain_number] > 0:
                    domain_counts[domain_number] -= 1
                    trimmed = True

            if not trimmed:
                break

        def exam_eligible(task):
            """Return True if the task may appear in an exam."""
            if task is None:
                return False

            if not getattr(task, "exam_eligible", True):
                return False

            if getattr(task, "challenge_only", False):
                return False

            if getattr(task, "requires_reboot", False):
                return False

            return True

        disk_used = 0

        for domain_number, needed in domain_counts.items():
            domain_categories = [
                category
                for category, domain in settings.CATEGORY_TO_DOMAIN.items()
                if domain == domain_number
            ]

            available_categories = [
                category
                for category in domain_categories
                if category in cls._tasks
            ]

            if not available_categories:
                continue

            used_categories = set()
            remaining_for_domain = needed
            shuffled_categories = available_categories.copy()
            random.shuffle(shuffled_categories)

            for category in shuffled_categories:
                if remaining_for_domain <= 0:
                    break

                if category in used_categories:
                    continue

                task = cls.get_random_task(
                    category=category,
                    difficulty="exam",
                    mode="exam",
                )

                if not task:
                    task = cls.get_random_task(
                        category=category,
                        mode="exam",
                    )

                if not exam_eligible(task):
                    task = None

                if task:
                    slots = getattr(task, "disk_slots", 0)

                    if disk_used + slots > disk_budget:
                        task = None

                if task and task.id not in exclude_ids:
                    disk_used += getattr(task, "disk_slots", 0)
                    tasks.append(task)
                    exclude_ids.append(task.id)
                    used_categories.add(category)
                    remaining_for_domain -= 1

        guard = 0

        while len(tasks) < count and guard < count * 20:
            guard += 1

            task = cls.get_random_task(
                difficulty="exam",
                mode="exam",
            )

            if not exam_eligible(task):
                task = None

            if task:
                slots = getattr(task, "disk_slots", 0)

                if disk_used + slots > disk_budget:
                    task = None

            if task and task.id not in exclude_ids:
                disk_used += getattr(task, "disk_slots", 0)
                tasks.append(task)
                exclude_ids.append(task.id)

        random.shuffle(tasks)
        return tasks

    @classmethod
    def get_practice_tasks(
        cls,
        category,
        difficulty="exam",
        count=None,
        skip_reboot=False,
    ):
        if count is None:
            count = settings.DEFAULT_PRACTICE_TASKS

        tasks = cls.get_random_tasks(
            count,
            categories=[category],
            difficulty=difficulty,
            skip_reboot=skip_reboot,
            mode="practice",
        )

        tasks.sort(
            key=lambda task: (
                task.task_order is None,
                task.task_order or 0,
            )
        )

        return tasks

    @classmethod
    def get_challenge_tasks(
        cls,
        count=None,
        categories=None,
        difficulty=None,
        skip_reboot=False,
    ):
        """
        Return tasks reserved exclusively for Challenge mode.
        """
        if count is None:
            count = settings.DEFAULT_PRACTICE_TASKS

        return cls.get_random_tasks(
            count,
            categories=categories,
            difficulty=difficulty,
            skip_reboot=skip_reboot,
            mode="challenge",
        )

    @classmethod
    def initialize(cls):
        """Initialize task registry by auto-discovering all task modules."""
        if cls._initialized:
            return

        logger.info("Initializing task registry (auto-discovery)...")

        import tasks as tasks_package

        package_path = tasks_package.__path__

        for importer, module_name, is_pkg in pkgutil.iter_modules(
            package_path
        ):
            if module_name in ("base", "registry", "__init__"):
                continue

            full_module_name = f"tasks.{module_name}"

            try:
                importlib.import_module(full_module_name)
                logger.debug(f"Imported {full_module_name}")
            except ImportError as exc:
                logger.warning(
                    f"Could not import {full_module_name}: {exc}"
                )
            except Exception as exc:
                logger.error(
                    f"Error importing {full_module_name}: {exc}"
                )

        cls._initialized = True

        logger.info(
            f"Task registry initialized with "
            f"{cls.get_task_count()} tasks across "
            f"{len(cls.get_all_categories())} categories"
        )

    @classmethod
    def print_statistics(cls):
        """Print task registry statistics."""
        print("\nTask Registry Statistics:")
        print("=" * 60)
        print(
            f"Total categories: "
            f"{len(cls.get_all_categories())}"
        )
        print(f"Total tasks: {cls.get_task_count()}")

        print("\nTasks by Exam Domain:")

        for domain_number, domain_name in sorted(
            settings.EXAM_DOMAINS.items()
        ):
            domain_tasks = cls.get_tasks_by_domain(domain_number)
            print(
                f"  Domain {domain_number}: "
                f"{domain_name} - {len(domain_tasks)} tasks"
            )

        print("\nTasks by Category:")

        for category in sorted(cls.get_all_categories()):
            count = cls.get_task_count(category)
            domain = settings.CATEGORY_TO_DOMAIN.get(category, "?")
            print(
                f"  {category}: {count} tasks "
                f"(Domain {domain})"
            )


_registry = TaskRegistry()


def get_registry():
    return _registry
