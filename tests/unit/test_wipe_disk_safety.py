
"""
Security regression tests for wipe_disk().

All destructive subprocess calls are blocked.
"""

from unittest.mock import patch

from utils import helpers


def block_commands(*args, **kwargs):
    raise AssertionError(
        "Unauthorized disk triggered a system command"
    )


def test_wipe_disk_rejects_unconfigured_device():
    """A disk outside the configured allowlist must be rejected."""

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
            "subprocess.run",
            side_effect=block_commands,
        ),
    ):
        success, messages = helpers.wipe_disk("/dev/sdc")

    assert success is False
    assert messages


def test_wipe_disk_rejects_system_device():
    """A system disk must be rejected even if configured."""

    config = {
        "mode": "real",
        "devices": ["/dev/sda"],
    }

    with (
        patch.object(
            helpers,
            "get_practice_device_config",
            return_value=config,
        ),
        patch(
            "utils.disk_safety.is_system_disk",
            return_value=True,
        ),
        patch(
            "subprocess.run",
            side_effect=block_commands,
        ),
    ):
        success, messages = helpers.wipe_disk("/dev/sda")

    assert success is False
    assert messages

