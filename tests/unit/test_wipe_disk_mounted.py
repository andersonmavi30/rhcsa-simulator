
"""
RHCSA Simulator - Mounted Disk Safety Test.

Verify mounted disks are rejected before destructive operations.
All subprocess calls are mocked.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    if command[:3] == ["lsblk", "-rno", "NAME"]:
        return subprocess.CompletedProcess(
            command, 0, "sdb\nsdb1\n", ""
        )

    if command[:4] == ["lsblk", "-dn", "-o", "TYPE,PKNAME"]:
        if command[-1] == "/dev/sdb1":
            return subprocess.CompletedProcess(
                command, 0, "part sdb\n", ""
            )

    if command[0] == "lsblk" and "MOUNTPOINT" in command:
        return subprocess.CompletedProcess(
            command, 0, "\n/mnt/important\n", ""
        )

    raise AssertionError(
        f"Unexpected or destructive command: {command}"
    )


def test_mounted_disk_must_be_rejected():
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
    assert any("mounted" in msg for msg in messages)

