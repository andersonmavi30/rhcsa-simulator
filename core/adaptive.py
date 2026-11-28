"""
Adaptive practice mode for RHCSA Simulator v4.0.0

SM-2 driven adaptive practice that focuses on weak/due categories.
Selects difficulty based on historical success rate.
"""

import logging

from tasks.registry import TaskRegistry
from core.validator import get_validator
from core.results_db import get_results_db
from core.session_context import SessionContext
from core import task_env
from utils import formatters as fmt
from utils.helpers import confirm_action
from config import settings


logger = logging.getLogger(__name__)


class AdaptiveMode:
    """SM-2 driven adaptive practice session."""

    def __init__(
        self,
        gui_port=None,
        gui_bind="0.0.0.0",
        context=None,
    ):
        self.db = get_results_db()
        self.tasks_per_session = 5

        # Task panel — same window every other mode uses, on by default;
        # None (--no-gui) falls back to the terminal only.
        self.gui_port = gui_port
        self.gui_bind = gui_bind

        self.tasks = []
        self.panel = None

        self.context = context or SessionContext(mode="adaptive")

    def start(self):
        """Start an adaptive practice session."""
        TaskRegistry.initialize()

        fmt.clear_screen()
        fmt.print_header("ADAPTIVE PRACTICE MODE")

        print(
            "Adaptive mode selects tasks based on your performance history."
        )
        print(
            "It focuses on weak areas and categories due for review."
        )
        print()

        # Let the candidate size the session.
        self.tasks_per_session = self._select_task_count()

        # Determine target categories.
        categories, source = self._select_categories()

        if not categories:
            print(fmt.warning("No task categories available."))
            input("Press Enter to return...")
            return

        print(fmt.bold(f"Session focus: {source}"))

        for cat in categories:
            cat_name = fmt.format_category_name(cat)
            domain = settings.CATEGORY_TO_DOMAIN.get(cat, "?")
            print(f"  - {cat_name} [D{domain}]")

        print()

        # Generate tasks.
        tasks = self._generate_tasks(categories)

        if not tasks:
            print(
                fmt.error(
                    "Could not generate tasks for selected categories."
                )
            )
            input("Press Enter to return...")
            return

        print(fmt.info(f"Generated {len(tasks)} tasks for this session."))
        print()

        if not confirm_action("Ready to start?", default=True):
            return

        self.tasks = tasks

        from core import task_gui

        self.panel = task_gui.open_panel(
            self.tasks,
            self.gui_port,
            self.gui_bind,
        )

        # Reset the box to a clean, practice-ready state.
        print(fmt.dim("Preparing a clean practice environment..."))
        task_env.prepare_session(tasks)

        results = []

        try:
            for i, task in enumerate(tasks, 1):
                result = self._run_task(task, i, len(tasks))
                results.append((task, result))

        except StopIteration:
            print(fmt.info("\nSession ended early."))

        finally:
            # If an interruption occurred while a task was active, close it
            # as incomplete before closing the session context.
            if self.context.current_task is not None:
                self.context.finish_task(passed=False)

            self.context.finish_session()

            # Leave the machine clean regardless of how the session ended.
            task_env.session_teardown(tasks)
            task_gui.close_panel(self.panel)
            self.panel = None

        if results:
            self._show_summary(results, source)

    def _select_task_count(self):
        """Ask how many tasks this session should include."""
        from utils.helpers import select_task_count

        number = select_task_count(default=5)
        print()
        return number

    def _select_categories(self):
        """Select categories based on SM-2 data."""
        # Priority 1: categories due for spaced repetition review.
        due = self.db.get_due_categories()

        if due:
            cats = [row["category"] for row in due[:3]]
            valid = [
                cat
                for cat in cats
                if cat in TaskRegistry.get_all_categories()
            ]

            if valid:
                return valid, "Due for review (spaced repetition)"

        # Priority 2: weak categories.
        weak = self.db.get_weak_categories(0.7)

        if weak:
            cats = [row["category"] for row in weak[:3]]
            valid = [
                cat
                for cat in cats
                if cat in TaskRegistry.get_all_categories()
            ]

            if valid:
                return valid, "Weak areas (below 70% success)"

        # Priority 3: random selection from all categories.
        all_categories = TaskRegistry.get_all_categories()

        if all_categories:
            import random

            selected = random.sample(
                all_categories,
                min(3, len(all_categories)),
            )
            return selected, "Random selection (no history yet)"

        return [], "No categories available"

    def _get_adaptive_difficulty(self, category):
        """Select difficulty based on category success rate."""
        stats = self.db.get_category_stats(category)

        if not stats or stats["attempts"] < 3:
            return "exam"

        rate = stats["success_rate"]

        if rate < 0.5:
            return "easy"
        if rate < 0.75:
            return "exam"

        return "hard"

    def _generate_tasks(self, categories):
        """Generate tasks across the focus categories.

        Adaptive mode explicitly requests mode="adaptive" so challenge-only
        tasks are never selected.
        """
        import random

        target = self.tasks_per_session
        tasks = []
        seen_ids = set()

        # Focus categories first, then everything else for overflow.
        overflow = [
            cat
            for cat in TaskRegistry.get_all_categories()
            if cat not in categories
        ]
        random.shuffle(overflow)

        pool = list(categories) + overflow

        def draw(category):
            difficulty = self._get_adaptive_difficulty(category)

            task = TaskRegistry.get_random_task(
                category=category,
                difficulty=difficulty,
                mode="adaptive",
            )

            if not task:
                task = TaskRegistry.get_random_task(
                    category=category,
                    mode="adaptive",
                )

            return task

        # Pass 1: round-robin distinct tasks across the pool.
        progressed = True

        while len(tasks) < target and progressed:
            progressed = False

            for category in pool:
                if len(tasks) >= target:
                    break

                task = draw(category)

                if task and task.id not in seen_ids:
                    tasks.append(task)
                    seen_ids.add(task.id)
                    progressed = True

        # Pass 2: top up with fresh randomized instances if needed.
        guard = 0

        while len(tasks) < target and guard < target * 20:
            guard += 1
            category = random.choice(
                categories if categories else pool
            )
            task = draw(category)

            if task:
                tasks.append(task)

        return tasks

    def _run_task(self, task, current, total):
        """Run a single adaptive task. Returns ValidationResult."""
        import time

        # Change the system for this task before the candidate works on it.
        fmt.clear_screen()
        print(fmt.bold("Preparing task environment..."))
        task_env.setup_task(task)

        self.context.start_task(
            task_id=task.id,
            category=getattr(task, "category", None),
            chapter=getattr(task, "chapter", None),
            objective=getattr(task, "objective", None),
            task_source=getattr(task, "task_source", None),
        )

        time.sleep(1)

        fmt.clear_screen()
        print(f"Adaptive Practice - Task {current}/{total}")
        print("=" * 60)
        print()

        # Task info.
        print(fmt.bold("Task:"))
        print(task.description)
        print()

        cat_name = fmt.format_category_name(task.category)
        domain = getattr(task, "exam_domain", 0)
        domain_name = settings.EXAM_DOMAINS.get(domain, "")

        print(fmt.bold(f"Category: {cat_name}"))

        if domain_name:
            print(fmt.bold(f"Domain: {domain} - {domain_name}"))

        print(fmt.bold(f"Points: {task.points}"))
        print(
            fmt.bold(
                f"Difficulty: {fmt.format_difficulty(task.difficulty)}"
            )
        )

        persistence = getattr(task, "requires_persistence", False)

        if persistence:
            print(
                fmt.info(
                    "  Requires persistence (survives reboot)"
                )
            )

        print()

        # Hints.
        if task.hints and confirm_action("Show hints?", default=False):
            self.context.record_hint("task_hints")

            print()
            print(fmt.bold("Hints:"))

            for i, hint in enumerate(task.hints, 1):
                print(f"  {i}. {hint}")

            print()

        input(
            "Complete this task on your system, "
            "then press Enter to validate..."
        )

        # Validate.
        validator = get_validator()
        result = validator.validate_task(task)

        self.context.record_attempt(
            passed=result.passed,
            score=result.score,
            max_score=result.max_score,
        )

        # Display result.
        print()
        print(fmt.bold("Validation Results:"))
        print("=" * 60)

        for check in result.checks:
            fmt.print_check_result(
                check.name,
                check.passed,
                check.message,
                check.points,
                check.max_points,
            )

        print("=" * 60)
        fmt.print_result_summary(
            result.passed,
            result.score,
            result.max_score,
            result.percentage,
        )

        # Save to ResultsDB.
        self.db.save_practice_attempt(
            task_id=task.id,
            category=task.category,
            difficulty=task.difficulty,
            domain=getattr(task, "exam_domain", 0),
            score=result.score,
            max_score=result.max_score,
            passed=result.passed,
            mode="adaptive",
        )

        self.context.finish_task(
            passed=result.passed,
            score=result.score,
            max_score=result.max_score,
        )

        # Show exam tips.
        exam_tips = getattr(task, "exam_tips", [])

        if exam_tips:
            print()
            print(fmt.bold("Exam Tips:"))

            for tip in exam_tips:
                print(f"  * {tip}")

        if result.passed:
            print(fmt.success("\nGreat job!"))

        print()

        # System changes are reverted once at the end of the session.
        if getattr(task, "disk_slots", 0) > 0 and current < total:
            print(
                fmt.dim(
                    "Re-provisioning practice disks for the next task..."
                )
            )
            task_env.reset_after_task(task)

        if current < total:
            if not confirm_action(
                "Continue to next task?",
                default=True,
            ):
                raise StopIteration

        input("Press Enter to continue...")
        return result

    def _show_summary(self, results, source):
        """Show session summary with improvement indicators."""
        fmt.clear_screen()
        fmt.print_header("ADAPTIVE SESSION SUMMARY")

        total_tasks = len(results)
        passed = sum(1 for _, result in results if result.passed)
        total_score = sum(result.score for _, result in results)
        total_max = sum(result.max_score for _, result in results)
        percentage = (
            total_score / total_max * 100
            if total_max > 0
            else 0
        )

        print(fmt.bold(f"Focus: {source}"))
        print()
        print(fmt.bold("Results:"))
        print(f"  Tasks Passed: {passed}/{total_tasks}")
        print(
            f"  Total Score: {total_score}/{total_max} "
            f"({percentage:.0f}%)"
        )
        print()

        # Per-category breakdown.
        category_results = {}

        for task, result in results:
            category = task.category

            if category not in category_results:
                category_results[category] = {
                    "passed": 0,
                    "total": 0,
                    "score": 0,
                    "max": 0,
                }

            category_results[category]["total"] += 1
            category_results[category]["score"] += result.score
            category_results[category]["max"] += result.max_score

            if result.passed:
                category_results[category]["passed"] += 1

        print(fmt.bold("By Category:"))

        for category, stats in category_results.items():
            cat_name = fmt.format_category_name(category)
            category_percentage = (
                stats["score"] / stats["max"] * 100
                if stats["max"] > 0
                else 0
            )

            # Show historical stats for comparison.
            db_stats = self.db.get_category_stats(category)
            history = ""

            if db_stats and db_stats["attempts"] > 1:
                historical_rate = db_stats["success_rate"] * 100
                history = f" (historical: {historical_rate:.0f}%)"

            print(
                f"  {cat_name}: "
                f"{stats['passed']}/{stats['total']} passed, "
                f"{stats['score']}/{stats['max']} pts "
                f"({category_percentage:.0f}%){history}"
            )

        print()

        # Next review information.
        print(fmt.bold("Next Steps:"))
        due = self.db.get_due_categories()
        weak = self.db.get_weak_categories(0.7)

        if weak:
            print(f"  Weak areas remaining: {len(weak)}")

        if due:
            print(f"  Categories due for review: {len(due)}")

        if not weak and not due:
            print(fmt.success("  All categories are on track!"))

        print()
        input("Press Enter to return to menu...")


def run_adaptive_mode(gui_port=None, gui_bind="0.0.0.0"):
    """Run adaptive mode (convenience function)."""
    mode = AdaptiveMode(
        gui_port=gui_port,
        gui_bind=gui_bind,
    )
    mode.start()
