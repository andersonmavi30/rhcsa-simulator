"""
Security regression tests for RHCSA Simulator disk allocation and cleanup.

No real disks are accessed or modified.
"""

from unittest.mock import patch

import pytest

from utils import helpers


pytestmark = pytest.mark.unit


def test_unconfigured_real_disk_is_not_allocated():
    """
    A disk that was not explicitly registered must not
    be included in the exam device pool.
    """
    with (
        patch.object(
            helpers,
            "ensure_loop_devices",
            return_value=["/dev/loop0"],
        ),
        patch.object(
            helpers,
            "get_spare_real_disks",
            return_value=["/dev/sdb"],
        ),
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value={
                "mode": "loop",
                "devices": ["/dev/loop0"],
            },
        ),
    ):
        pool = helpers.build_device_pool()

    assert pool == ["/dev/loop0"]


def test_unconfigured_disk_is_rejected_without_config():
    """
    Missing configuration must never authorize
    an automatically detected real disk.
    """
    with (
        patch.object(
            helpers,
            "ensure_loop_devices",
            return_value=["/dev/loop0"],
        ),
        patch.object(
            helpers,
            "get_spare_real_disks",
            return_value=["/dev/sdc"],
        ),
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=None,
        ),
    ):
        pool = helpers.build_device_pool()

    assert "/dev/sdc" not in pool


def test_cleanup_real_disk_keeps_config_when_wipe_fails():
    """A failed authorized wipe must leave the setup available for retry."""
    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value={"mode": "real", "devices": ["/dev/sdb"]},
        ),
        patch.object(
            helpers,
            "wipe_disk",
            return_value=(False, ["Disk wipe denied: system disk"]),
        ) as wipe_disk,
        patch("utils.helpers.os.path.exists", return_value=False),
    ):
        assert helpers.cleanup_practice_devices() is False

    wipe_disk.assert_called_once_with("/dev/sdb")


def test_cleanup_loop_delegates_to_hardened_lvm_teardown():
    """Loop cleanup must remove stray VGs before detaching simulator loops."""
    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value={"mode": "loop", "devices": ["/dev/loop10"]},
        ),
        patch.object(
            helpers,
            "get_loop_devices",
            return_value=["/dev/loop10", "/dev/loop11"],
        ),
        patch.object(helpers, "_remove_stray_practice_vgs") as remove_stray,
        patch.object(helpers, "_purge_loop_device") as purge_loop,
        patch("utils.helpers.os.path.exists", return_value=False),
    ):
        assert helpers.cleanup_practice_devices() is True

    remove_stray.assert_called_once_with()
    purge_loop.assert_any_call("/dev/loop10")
    purge_loop.assert_any_call("/dev/loop11")
    assert purge_loop.call_count == 2
