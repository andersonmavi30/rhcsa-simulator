
"""
RHCSA Simulator - dd Failure Regression Test

Verify that wipe_disk reports failures when dd cannot
overwrite the partition table.

All subprocess calls are mocked.
No real disks are modified.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    """Simulate commands, with dd failing."""

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

    if command[0] == "dd":
        return subprocess.CompletedProcess(
            command, 1, "", "Input/output error"
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_dd_failure_must_fail_disk_cleanup():
    """A failed dd operation must never be reported as success."""

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

