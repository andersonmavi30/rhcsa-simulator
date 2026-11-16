
"""
RHCSA Simulator - Partition Ownership Security Tests.

Verify that only direct partitions of an authorized disk
can be included in destructive operations.

All system commands are mocked.
No real disks are accessed or modified.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    """Simulate a foreign partition in the lsblk output."""

    if command[:2] == ["lsblk", "-rno"] and "NAME" in command:
        return subprocess.CompletedProcess(
            command, 0, "sdb\nsdb1\nsdc1\n", ""
        )

    if command[:4] == ["lsblk", "-dn", "-o", "TYPE,PKNAME"]:
        partition = command[-1]

        if partition == "/dev/sdb1":
            return subprocess.CompletedProcess(
                command, 0, "part sdb\n", ""
            )

        if partition == "/dev/sdc1":
            return subprocess.CompletedProcess(
                command, 0, "part sdc\n", ""
            )

        raise AssertionError(f"Unexpected partition: {partition}")

    if command[0] == "lsblk" and "MOUNTPOINT" in command:
        return subprocess.CompletedProcess(
            command, 0, "\n\n\n", ""
        )

    raise AssertionError(
        f"Unexpected or destructive command: {command}"
    )


def test_rejects_partition_from_another_disk():
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
    assert any("another disk" in message for message in messages)

