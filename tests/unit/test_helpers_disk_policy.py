
"""
Security regression tests for RHCSA Simulator disk allocation.

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

