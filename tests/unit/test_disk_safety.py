
"""
Unit tests for RHCSA Simulator disk safety.

All system inspection commands are mocked.
No real disks are modified.
"""

from unittest.mock import patch

import pytest

from utils import disk_safety


pytestmark = pytest.mark.unit


class TestDiskSafety:

    def test_rejects_invalid_device_paths(self):
        assert disk_safety._canonical_device("") is None
        assert disk_safety._canonical_device("../sda") is None
        assert disk_safety._canonical_device("/tmp/disk") is None
        assert disk_safety._canonical_device(None) is None

    def test_rejects_unowned_loop(self):
        with patch.object(
            disk_safety,
            "_run_readonly",
            return_value="/tmp/unrelated.img\n"
        ):
            assert disk_safety.is_owned_loop("/dev/loop5") is False

    def test_accepts_owned_loop(self):
        with patch.object(
            disk_safety,
            "_run_readonly",
            return_value=(
                "/var/lib/rhcsa-simulator/loops/disk0.img\n"
            )
        ):
            assert disk_safety.is_owned_loop("/dev/loop5") is True

    def test_rejects_unconfigured_real_disk(self):
        with patch.object(
            disk_safety,
            "is_system_disk",
            return_value=False
        ):
            assert disk_safety.is_explicit_real_disk(
                "/dev/sdc", ["/dev/sdb"]
            ) is False

    def test_rejects_system_disk(self):
        with patch.object(
            disk_safety,
            "is_system_disk",
            return_value=True
        ):
            assert disk_safety.is_explicit_real_disk(
                "/dev/sda", ["/dev/sda"]
            ) is False

    def test_accepts_configured_real_disk(self):
        with patch.object(
            disk_safety,
            "is_system_disk",
            return_value=False
        ), patch.object(
            disk_safety,
            "_run_readonly",
            return_value="disk\n"
        ):
            assert disk_safety.is_explicit_real_disk(
                "/dev/sdb", ["/dev/sdb"]
            ) is True

    def test_rejects_unknown_mode(self):
        assert disk_safety.is_authorized_device(
            "/dev/sdb", "unknown", ["/dev/sdb"]
        ) is False

    def test_rejects_initial_candidate_with_mounts(self):
        with patch.object(
            disk_safety,
            "is_system_disk",
            return_value=False
        ), patch.object(
            disk_safety,
            "_run_readonly",
            side_effect=["disk\n", "/mnt/data\n"]
        ):
            assert disk_safety.is_safe_initial_candidate(
                "/dev/sdb"
            ) is False

