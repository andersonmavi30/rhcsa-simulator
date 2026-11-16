
"""
RHCSA Simulator - Disk Wipe Error Tests.

Verify that wipe_disk reports failures from wipefs and pvremove.

All subprocess calls are mocked.
No real disks are accessed or modified.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


CONFIG = {
    "mode": "real",
    "devices": ["/dev/sdb"],
}


def fake_wipefs_failure(command, **kwargs):
    """Simulate a non-LVM disk where wipefs fails."""

    if command[0] == "lsblk":
        if "MOUNTPOINT" in command:
            return subprocess.CompletedProcess(command, 0, "\n", "")
        return subprocess.CompletedProcess(command, 0, "sdb\n", "")

    if command[0] == "pvs":
        return subprocess.CompletedProcess(command, 0, "", "")

    if command[0] == "wipefs":
        return subprocess.CompletedProcess(
            command, 1, "", "Device or resource busy"
        )

    if command[0] == "blockdev":
        return subprocess.CompletedProcess(
            command, 0, "104857600\n", ""
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def fake_pvremove_failure(command, **kwargs):
    """Simulate an authorized LVM PV where pvremove fails."""

    if command[0] == "lsblk":
        if "MOUNTPOINT" in command:
            return subprocess.CompletedProcess(command, 0, "\n", "")
        return subprocess.CompletedProcess(command, 0, "sdb\n", "")

    if command[0] == "pvs":
        if "pv_name,vg_name" in command:
            return subprocess.CompletedProcess(
                command, 0, "/dev/sdb vg_lab\n", ""
            )
        return subprocess.CompletedProcess(
            command, 0, "vg_lab\n", ""
        )

    if command[0] == "pvremove":
        return subprocess.CompletedProcess(
            command, 5, "", "PV removal failed"
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_wipefs_failure_must_fail_disk_cleanup():
    """A wipefs error must result in failure."""

    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=CONFIG,
        ),
        patch(
            "utils.disk_safety.is_system_disk",
            return_value=False,
        ),
        patch(
            "utils.disk_safety.is_explicit_real_disk",
            return_value=True,
        ),
        patch("subprocess.run", side_effect=fake_wipefs_failure),
    ):
        success, messages = helpers.wipe_disk("/dev/sdb")

    assert success is False
    assert messages


def test_pvremove_failure_must_fail_disk_cleanup():
    """A pvremove error on a confirmed PV must result in failure."""

    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=CONFIG,
        ),
        patch(
            "utils.disk_safety.is_system_disk",
            return_value=False,
        ),
        patch(
            "utils.disk_safety.is_explicit_real_disk",
            return_value=True,
        ),
        patch("subprocess.run", side_effect=fake_pvremove_failure),
    ):
        success, messages = helpers.wipe_disk("/dev/sdb")

    assert success is False
    assert messages

