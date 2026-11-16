
"""
RHCSA Simulator - Shared VG Safety Test.

Reject a VG spanning authorized and unauthorized PVs.
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
                command,
                0,
                "/dev/sdb1 vg_shared\n"
                "/dev/sdc1 vg_shared\n",
                "",
            )

        return subprocess.CompletedProcess(
            command, 0, "vg_shared\n", ""
        )

    raise AssertionError(
        f"Unexpected or destructive command: {command}"
    )


def test_shared_vg_is_rejected_before_modification():
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
    assert any("unauthorized PVs" in msg for msg in messages)

