
"""
Tests for the exam device pool / allocator (utils.helpers),
exam disk-budget cap (tasks.registry), and DeviceManager
disk cleanup safety.

All destructive commands are mocked.
No real disks, LVM volumes, or loop devices are modified.
"""

import logging
from unittest.mock import Mock, patch

import pytest

from utils import helpers
from tasks.registry import TaskRegistry
from device.device_manager import DeviceManager


pytestmark = pytest.mark.unit


class TestDeviceAllocator:

    def test_allocates_distinct_then_none(self):
        pool = ['/dev/loop0', '/dev/loop1', '/dev/sda']

        with patch.object(
            helpers, 'build_device_pool', return_value=pool
        ):
            helpers.begin_device_allocation()
            try:
                got = [
                    helpers.allocate_practice_device()
                    for _ in range(4)
                ]
            finally:
                helpers.end_device_allocation()

        assert got[:3] == pool
        assert got[3] is None
        assert len(set(got[:3])) == 3

    def test_inactive_by_default(self):
        assert helpers.device_allocation_active() is False
        assert helpers.allocate_practice_device() is None

    def test_get_practice_device_uses_allocator_when_active(self):
        pool = ['/dev/loopA', '/dev/loopB']

        with patch.object(
            helpers, 'build_device_pool', return_value=pool
        ):
            helpers.begin_device_allocation()
            try:
                a = helpers.get_practice_device()
                b = helpers.get_practice_device()
            finally:
                helpers.end_device_allocation()

        assert a == '/dev/loopA'
        assert b == '/dev/loopB'


class TestExamDiskBudget:

    def test_generate_exam_respects_disk_budget(self):
        TaskRegistry.initialize()

        tasks = TaskRegistry.generate_exam(
            20, disk_budget=1
        )

        used = sum(
            getattr(t, 'disk_slots', 0)
            for t in tasks
        )

        assert used <= 1, (
            f"disk_slots used ({used}) exceeded budget of 1"
        )

    def test_zero_budget_yields_no_disk_tasks(self):
        TaskRegistry.initialize()

        tasks = TaskRegistry.generate_exam(
            20, disk_budget=0
        )

        assert all(
            getattr(t, 'disk_slots', 0) == 0
            for t in tasks
        )


class TestDeviceManagerSafety:
    """
    Regression tests for destructive disk cleanup.

    All subprocess calls are mocked.
    """

    @pytest.fixture
    def manager(self):
        """
        Create an isolated DeviceManager without running
        automatic device discovery or changing the singleton.
        """
        dm = object.__new__(DeviceManager)
        dm.logger = logging.getLogger(__name__)
        dm._dry_run = False
        dm._cleanup_enabled = True
        dm._practice_device = None
        dm._tracked_resources = []
        dm._current_task_id = None
        return dm

    def test_cleanup_without_allowlist_is_blocked(self, manager):
        """
        No configured disks means no destructive cleanup.
        """
        with patch.object(
            manager, '_configured_devices', return_value=set()
        ), patch(
            'device.device_manager.subprocess.run'
        ) as run:
            result = manager._safety_cleanup()

        assert result is False
        run.assert_not_called()

    def test_unauthorized_pv_cannot_be_removed(self, manager):
        """
        A PV outside the allowlist must never be removed.
        """
        with patch.object(
            manager, '_configured_devices',
            return_value={'/dev/sdb'}
        ), patch.object(
            manager, '_is_allowed_pv',
            return_value=False
        ), patch(
            'device.device_manager.subprocess.run'
        ) as run:
            result = manager._cleanup_pv('/dev/sdc')

        assert result is False
        run.assert_not_called()

    def test_unauthorized_vg_cannot_be_removed(self, manager):
        """
        A foreign VG must never reach vgremove.
        """
        with patch.object(
            manager, '_configured_devices',
            return_value={'/dev/sdb'}
        ), patch.object(
            manager, '_authorized_vgs',
            return_value={'vg_practice'}
        ), patch(
            'device.device_manager.subprocess.run'
        ) as run:
            result = manager._cleanup_vg('vg_production')

        assert result is False
        run.assert_not_called()

    def test_unauthorized_lv_cannot_be_removed(self, manager):
        """
        An LV outside authorized VGs must never be deleted.
        """
        with patch.object(
            manager, '_configured_devices',
            return_value={'/dev/sdb'}
        ), patch.object(
            manager, '_authorized_vgs',
            return_value={'vg_practice'}
        ), patch.object(
            manager, '_source_allowed',
            return_value=False
        ), patch(
            'device.device_manager.subprocess.run'
        ) as run:
            result = manager._cleanup_lv(
                '/dev/vg_production/lv_data',
                {'vg_name': 'vg_production', 'lv_name': 'lv_data'}
            )

        assert result is False
        run.assert_not_called()

    def test_mixed_ownership_vg_blocks_safety_cleanup(self, manager):
        """
        If a VG spans an authorized and an unauthorized PV,
        refuse to clean the VG or either disk.
        """
        pvs_output = (
            "/dev/sdb vg_mixed\n"
            "/dev/sdc vg_mixed\n"
        )

        def fake_subprocess(args, **kwargs):
            if args[0] == 'pvs':
                return Mock(
                    returncode=0,
                    stdout=pvs_output
                )
            raise AssertionError(
                f"Unexpected subprocess command: {args}"
            )

        with patch.object(
            manager, '_configured_devices',
            return_value={'/dev/sdb'}
        ), patch.object(
            manager, '_is_allowed_pv',
            side_effect=lambda dev, allowed: dev in allowed
        ), patch(
            'device.device_manager.subprocess.run',
            side_effect=fake_subprocess
        ) as run:
            result = manager._safety_cleanup()

        assert result is False

        commands = [
            call.args[0][0]
            for call in run.call_args_list
        ]

        assert commands == ['pvs']
        assert not any(
            command in {
                'lvremove', 'vgremove',
                'pvremove', 'wipefs',
                'umount', 'swapoff'
            }
            for command in commands
        )

