
"""
RHCSA Simulator - Orphan PV Regression Test.

Verify that a PV without a VG is handled correctly.
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
            command, 0, "\n\n", ""
        )

    if command[0] == "pvs":
        if "pv_name,vg_name" in command:
            return subprocess.CompletedProcess(
                command, 0, "/dev/sdb1 \n", ""
            )

        return subprocess.CompletedProcess(
            command, 0, "\n", ""
        )

    if command[0] == "blockdev":
        return subprocess.CompletedProcess(
            command, 0, "104857600\n", ""
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_pv_without_vg_does_not_fail_preflight():
    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value={
                "mode": "real",
                "devices": ["/dev/sdb"],
            },
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

