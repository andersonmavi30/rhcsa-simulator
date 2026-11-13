
"""Regression test for an authorized disk without partitions."""

import subprocess
from unittest.mock import patch

from utils import helpers


def fake_run(command, **kwargs):
    if command[0] == "lsblk":
        if "MOUNTPOINT" in command:
            return subprocess.CompletedProcess(command, 0, "\n", "")
        return subprocess.CompletedProcess(command, 0, "sdb\n", "")

    if command[0] == "pvs":
        return subprocess.CompletedProcess(command, 0, "", "")

    if command[0] == "blockdev":
        return subprocess.CompletedProcess(
            command, 0, "104857600\n", ""
        )

    return subprocess.CompletedProcess(command, 0, "", "")


def test_authorized_disk_without_partitions():
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

