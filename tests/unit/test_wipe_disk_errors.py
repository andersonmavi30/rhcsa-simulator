
"""
RHCSA Simulator - Disk Wipe Error Tests

Regression tests for destructive command failures.

All subprocess calls are mocked.
No real disks are accessed or modified.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    """Simulate disk commands and a wipefs failure."""

    if command[0] == "lsblk":
        return subprocess.CompletedProcess(
            command, 0, "sdb\n", ""
        )

    if command[0] == "pvs":
        return subprocess.CompletedProcess(
            command, 0, "", ""
        )

    if command[0] == "blockdev":
        return subprocess.CompletedProcess(
            command, 0, "104857600\n", ""
        )

    if command[0] == "wipefs":
        return subprocess.CompletedProcess(
            command, 1, "", "Device or resource busy"
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_wipefs_failure_must_fail_disk_cleanup():
    """wipe_disk must report failure when wipefs fails."""

    config = {
        "mode": "real",
        "devices": ["/dev/sdb"],
    }

    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=config,
        ),
        patch(
            "utils.disk_safety.is_system_disk",
            return_value=False,
        ),
        patch(
            "utils.disk_safety.is_explicit_real_disk",
            return_value=True,
        ),
        patch("subprocess.run", side_effect=fake_run),
    ):
        success, messages = helpers.wipe_disk("/dev/sdb")

    assert success is False
    assert messages


def test_pvremove_failure_must_fail_disk_cleanup():
    """wipe_disk must report failure when pvremove fails."""

    def fake_pvremove_failure(command, **kwargs):
        if command[0] == "pvremove":
            return subprocess.CompletedProcess(
                command, 5, "", "PV removal failed"
            )

        if command[0] == "wipefs":
            return subprocess.CompletedProcess(
                command, 0, "", ""
            )

        return fake_run(command, **kwargs)

    config = {
        "mode": "real",
        "devices": ["/dev/sdb"],
    }

    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=config,
        ),
        patch(
            "utils.disk_safety.is_system_disk",
            return_value=False,
        ),
        patch(
            "utils.disk_safety.is_explicit_real_disk",
            return_value=True,
        ),
        patch(
            "subprocess.run",
            side_effect=fake_pvremove_failure,
        ),
    ):
        success, messages = helpers.wipe_disk("/dev/sdb")

    assert success is False
    assert messages

