
"""
RHCSA Simulator - Non-PV Disk Safety Test.

Verify that pvremove is never called on devices
that are not LVM physical volumes.

All system commands are mocked.
"""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    if command[:4] == ["lsblk", "-rno", "NAME", "/dev/sdb"]:
        return subprocess.CompletedProcess(
            command, 0, "sdb\n", ""
        )

    if command[0] == "lsblk" and "MOUNTPOINT" in command:
        return subprocess.CompletedProcess(command, 0, "\n", "")

    if command[0] == "pvs":
        return subprocess.CompletedProcess(command, 0, "", "")

    if command[0] == "pvremove":
        raise AssertionError(
            "pvremove must not run on a non-PV device"
        )

    if command[0] == "blockdev":
        return subprocess.CompletedProcess(
            command, 0, "104857600\n", ""
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_non_pv_disk_skips_pvremove():
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

    assert success is True
    assert messages

