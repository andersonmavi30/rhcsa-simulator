
"""
RHCSA Simulator - Mounted Disk Safety Test

Verify that mounted disks are rejected before modification.

All system commands are mocked.
No real disks are accessed or modified.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    """Simulate a disk with a mounted partition."""

    if command[:3] == ["lsblk", "-rno", "NAME"]:
        return subprocess.CompletedProcess(
            command, 0, "sdb\nsdb1\n", ""
        )

    if command[0] == "lsblk" and "MOUNTPOINT" in command:
        return subprocess.CompletedProcess(
            command, 0, "\n/mnt/important\n", ""
        )

    if command[0] == "pvs":
        return subprocess.CompletedProcess(
            command, 0, "", ""
        )

    raise AssertionError(
        f"Mounted disk triggered unexpected command: {command}"
    )


def test_mounted_disk_must_be_rejected():
    """Never modify a disk containing mounted filesystems."""

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

