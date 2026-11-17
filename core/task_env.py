"""Shared task-environment lifecycle for training sessions (practice + adaptive).

Exam mode already resets the box and prepares each task's preconditions
(reset practice disks + clean lab leftovers at start; inject_fault /
setup_environment per task; restore_fault / teardown_environment after). These
helpers expose that exact behavior so practice and adaptive modes get the same
real system changes and per-iteration reset — otherwise positive-config tasks
pass on default state and leftover artifacts from the previous task pollute the
next one.

Nothing new is invented here; it just calls the same functions exam.py uses.
"""

import logging
from utils import formatters as fmt

logger = logging.getLogger(__name__)


def _report_cleanup_error(operation, error, verbose=True):
    """Log cleanup failures and show a concise warning to interactive users."""
    logger.error("%s failed: %s", operation, error)
    if verbose:
        print(fmt.warning(f"  {operation} failed; the environment may not be clean."))


def session_reset(verbose=True):
    """Start-of-session reset: fresh practice disks + remove leftover artifacts.

    Mirrors ExamSession.start(): helpers.reset_practice_loops() followed by
    lab_cleanup.clean(). Returns the cleaned artifact list, as before. Failures
    are reported instead of being silently hidden.
    """
    from utils import helpers

    # First restore any faults/preconditions still active from a previous
    # session — exams deliberately leave the environment in place for review
    # and disputes, so the NEXT session is where it gets undone.
    try:
        from tasks.troubleshooting import restore_any_active_fault
        restore_any_active_fault()
    except Exception as exc:
        _report_cleanup_error("Restoring a previous troubleshooting fault", exc, verbose)

    try:
        helpers.reset_practice_loops()
    except Exception as exc:
        _report_cleanup_error("Resetting practice disks", exc, verbose)

    # Clear a stale exam countdown left by an interrupted exam.
    try:
        from core import exam_clock
        exam_clock.stop()
    except Exception as exc:
        logger.warning("Could not stop a stale exam clock: %s", exc)

    try:
        from core import lab_cleanup
        done = lab_cleanup.clean(dry_run=False)
    except Exception as exc:
        _report_cleanup_error("Cleaning leftover lab artifacts", exc, verbose)
        done = []

    if verbose and done:
        print(fmt.dim(f"Cleaned {len(done)} leftover lab artifact(s) from a previous session."))
    return done


def prepare_session(tasks, verbose=True):
    """Start-of-session prep shared by the training modes: reset the box to a
    clean state, then offer to install any packages the drawn tasks rely on
    (consent-gated — nothing installs silently)."""
    session_reset(verbose=verbose)
    try:
        from core import preflight
        preflight.offer_task_packages(tasks)
    except Exception as exc:
        logger.warning("Task package preflight failed: %s", exc)
        if verbose:
            print(fmt.warning("Package preflight failed; check the log if a task needs missing software."))


def setup_task(task, verbose=True):
    """Change the system for one task before the candidate works on it.

    Runs the task's own inject_fault() (break something to fix) and/or
    setup_environment() (establish a negative precondition so a positive-config
    task can't pass on default state) — the same calls exam.py makes. Returns a
    small state dict for teardown_task() to reverse.

    Console output stays GENERIC: the injection/setup message spells out
    exactly what was broken (i.e. the answer), so it goes to the log only.
    """
    state = {'fault': False, 'setup': False}

    if getattr(task, 'has_fault_injection', False):
        try:
            ok, msg = task.inject_fault()
            state['fault'] = ok
            logger.info("fault %s: %s: %s", "armed" if ok else "skipped", task.id, msg)
            if verbose:
                print(fmt.dim("  Scenario prepared — the described symptom is live.") if ok
                      else fmt.warning("  Scenario could not be set up (details in the log) — task is descriptive only."))
        except Exception as e:
            logger.warning("fault error: %s: %s", getattr(task, 'id', '?'), e)
            if verbose:
                print(fmt.warning("  Scenario setup error (details in the log)."))

    if getattr(task, 'has_setup', False):
        try:
            ok, msg = task.setup_environment()
            state['setup'] = ok
            # A False result just means no precondition was needed; stay quiet.
            logger.info("precondition %s: %s: %s", "set" if ok else "not needed", task.id, msg)
            if verbose and ok:
                print(fmt.dim("  Starting state prepared."))
        except Exception as e:
            logger.warning("setup error: %s: %s", getattr(task, 'id', '?'), e)
            if verbose:
                print(fmt.warning("  Starting-state setup error (details in the log)."))

    # Sanity check: with setup done and nothing done by the candidate yet, the
    # task must NOT already be passing. If it is, the fault/precondition no-op'd
    # (or it passes on default state) and the candidate would get a free pass.
    try:
        from core import task_sanity
        warning = task_sanity.check_task(task)
        if warning:
            logger.warning("SANITY: %s", warning)
            if verbose:
                print(fmt.warning(f"  ⚠ {warning}"))
    except Exception as e:
        logger.debug("sanity check skipped for %s: %s", getattr(task, 'id', '?'), e)

    return state


def teardown_task(task, state, verbose=True):
    """Reverse setup_task(): restore_fault() + teardown_environment()."""
    if not state:
        return
    if state.get('fault'):
        try:
            ok, msg = task.restore_fault()
            if verbose:
                print(fmt.dim(f"  {msg}") if ok else fmt.error(f"  Restore error: {msg}"))
        except Exception as exc:
            logger.exception("Could not restore injected fault for %s", getattr(task, 'id', '?'))
            if verbose:
                print(fmt.error("  Could not restore the task fault; check the log."))
    if state.get('setup'):
        try:
            task.teardown_environment()
        except Exception:
            logger.exception("Could not tear down task environment for %s", getattr(task, 'id', '?'))
            if verbose:
                print(fmt.error("  Could not restore the task starting state; check the log."))


def reset_after_task(task):
    """Between iterations, reset practice disks if the task consumed one.

    Non-disk tasks skip this (nothing to reset), keeping the session snappy.
    Returns True when no reset was needed or the reset completed; False when
    cleanup failed, so callers can report that the next task may inherit state.
    """
    if getattr(task, 'disk_slots', 0) <= 0:
        return True
    from utils import helpers
    try:
        helpers.reset_practice_loops()
        return True
    except Exception as exc:
        logger.exception("Could not reset practice disks after task %s", getattr(task, 'id', '?'))
        print(fmt.warning("  Practice disk reset failed; the next task may inherit disk state."))
        return False


def session_teardown(tasks, verbose=True):
    """End-of-session cleanup — call this on EVERY exit path (finished, quit, or
    Ctrl-C) so returning to the menu leaves a clean box.

    It (1) reverses every task's injected fault / negative precondition, then
    (2) removes leftover lab artifacts and resets practice disks (same as the
    start-of-session reset). Safe to call even if setup never ran.
    """
    if verbose:
        print(fmt.dim("Restoring the machine to a clean state..."))
    for task in tasks or []:
        if getattr(task, 'has_fault_injection', False):
            try:
                task.restore_fault()
            except Exception:
                logger.exception("Could not restore injected fault for %s", getattr(task, 'id', '?'))
        if getattr(task, 'has_setup', False):
            try:
                task.teardown_environment()
            except Exception:
                logger.exception("Could not tear down task environment for %s", getattr(task, 'id', '?'))
    # Remove candidate-created artifacts (files, mounts, swap, units, …) and
    # reset practice disks so the box is back to a clean, vanilla state.
    session_reset(verbose=False)
