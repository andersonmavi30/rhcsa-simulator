
"""
RHCSA Simulator - Disk Safety

Centralized authorization checks for practice disks.
This module does not modify disks or execute destructive commands.
"""

import os
import re
import subprocess

from utils.system_id import is_system_disk


LOOP_DIRECTORY = "/var/lib/rhcsa-simulator/loops"


def _run_readonly(command):
    """Run a read-only inspection command. Fail closed on errors."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def _canonical_device(device):
    """Validate and normalize a block-device path."""
    if not isinstance(device, str):
        return None

    if not re.fullmatch(r"/dev/[A-Za-z0-9_./+-]+", device):
        return None

    normalized = os.path.normpath(device)

    if not normalized.startswith("/dev/"):
        return None

    return os.path.realpath(normalized)


def is_owned_loop(device):
    """Allow only loop devices backed by simulator-owned images."""
    device = _canonical_device(device)

    if not device or not re.fullmatch(r"/dev/loop[0-9]+", device):
        return False

    output = _run_readonly(["losetup", "-n", "-O", "BACK-FILE", device])

    if output is None:
        return False

    backing_file = output.strip().removesuffix(" (deleted)")
    backing_file = os.path.abspath(backing_file)

    return (
        backing_file.startswith(LOOP_DIRECTORY + os.sep)
        and backing_file.endswith(".img")
    )


def is_explicit_real_disk(device, configured_devices):
    """Check explicit authorization without trusting disk names alone."""
    device = _canonical_device(device)

    if not device:
        return False

    configured = {
        _canonical_device(item)
        for item in configured_devices
    }

    if device not in configured:
        return False

    if is_system_disk(device):
        return False

    device_type = _run_readonly(["lsblk", "-dn", "-o", "TYPE", device])

    return device_type is not None and device_type.strip() == "disk"


def is_authorized_device(device, mode, configured_devices):
    """Validate a device against the selected practice-disk mode."""
    if mode == "loop":
        return is_owned_loop(device)

    if mode == "real":
        return is_explicit_real_disk(device, configured_devices)

    return False


def is_safe_initial_candidate(device):
    """
    Preliminary check before a user explicitly selects a real disk.

    This is NOT sufficient authorization to erase the disk.
    """
    device = _canonical_device(device)

    if not device or is_system_disk(device):
        return False

    device_type = _run_readonly(["lsblk", "-dn", "-o", "TYPE", device])

    if device_type is None or device_type.strip() != "disk":
        return False

    mounts = _run_readonly(["lsblk", "-nr", "-o", "MOUNTPOINT", device])

    if mounts is None:
        return False

    if any(line.strip() for line in mounts.splitlines()):
        return False

    return True

