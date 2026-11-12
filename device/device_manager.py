"""
DeviceManager - Automatic resource cleanup for RHCSA Simulator v2.0.0

This module provides centralized management of practice resources with
automatic cleanup between tasks. No more manual disk wiping!

Usage:
    from device import get_device_manager

    dm = get_device_manager()
    with dm.task_context("task_001") as ctx:
        device = dm.get_practice_device()
        # User completes task...
    # Resources automatically cleaned up here
"""

import logging
import subprocess
import time
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any
from enum import Enum
from contextlib import contextmanager

from utils.system_id import system_vgs as get_system_vgs, is_system_disk


logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of resources that can be tracked and cleaned up."""
    LOOP_DEVICE = "loop_device"
    PHYSICAL_VOLUME = "physical_volume"
    VOLUME_GROUP = "volume_group"
    LOGICAL_VOLUME = "logical_volume"
    FILESYSTEM = "filesystem"
    MOUNT_POINT = "mount_point"
    SWAP = "swap"
    FSTAB_ENTRY = "fstab_entry"
    USER = "user"
    GROUP = "group"
    FILE = "file"
    DIRECTORY = "directory"
    CRON_JOB = "cron_job"


# Cleanup order - lower numbers cleaned first
CLEANUP_ORDER = {
    ResourceType.MOUNT_POINT: 10,       # Unmount first
    ResourceType.SWAP: 15,              # Deactivate swap
    ResourceType.FSTAB_ENTRY: 20,       # Remove persistence
    ResourceType.LOGICAL_VOLUME: 30,    # Remove LVs
    ResourceType.VOLUME_GROUP: 40,      # Then VGs
    ResourceType.PHYSICAL_VOLUME: 50,   # Then PVs
    ResourceType.LOOP_DEVICE: 55,       # Loop devices
    ResourceType.FILESYSTEM: 25,        # FS signatures
    ResourceType.USER: 70,              # Users
    ResourceType.GROUP: 75,             # Groups after users
    ResourceType.FILE: 80,              # Files
    ResourceType.DIRECTORY: 85,         # Directories
    ResourceType.CRON_JOB: 90,          # Cron jobs
}


@dataclass
class TrackedResource:
    """A resource created during a task that needs cleanup."""
    resource_type: ResourceType
    identifier: str  # Device path, username, mount point, etc.
    task_id: str
    created_at: float = field(default_factory=time.time)
    cleanup_order: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.cleanup_order == 50:
            self.cleanup_order = CLEANUP_ORDER.get(self.resource_type, 50)


class DeviceManager:
    """
    Centralized device and resource management for RHCSA Simulator.

    Handles:
    - Practice device allocation
    - Resource tracking (LVM, mounts, users, etc.)
    - Automatic cleanup between tasks
    - Session state persistence

    This is a singleton - use get_device_manager() to get the instance.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.logger = logging.getLogger(__name__)
        self._tracked_resources: List[TrackedResource] = []
        self._practice_device: Optional[str] = None
        self._cleanup_enabled = True
        self._dry_run = False
        self._current_task_id: Optional[str] = None

        # Detect practice device on init
        self._detect_practice_device()

    def _configured_devices(self) -> Set[str]:
        """Fail-closed allowlist: selected real disks and simulator-owned loops only."""
        from utils.helpers import get_practice_device_config

        cfg = get_practice_device_config()
        allowed = set()
        if not isinstance(cfg, dict) or cfg.get('mode') not in ('loop', 'real'):
            return allowed
        configured = cfg.get('devices')
        if not isinstance(configured, list):
            return allowed

        for candidate in configured:
            if not isinstance(candidate, str) or not candidate.startswith('/dev/'):
                continue
            dev = os.path.realpath(candidate)
            if is_system_disk(dev):
                continue
            if cfg['mode'] == 'loop':
                if not os.path.basename(dev).startswith('loop'):
                    continue
                # Only loop images stored in our dedicated simulator directory.
                try:
                    probe = subprocess.run(
                        ['losetup', '-n', '-O', 'BACK-FILE', dev],
                        capture_output=True, text=True, timeout=5)
                    backing = probe.stdout.strip().removesuffix(' (deleted)')
                    root = '/var/lib/rhcsa-simulator/loops'
                    if (probe.returncode != 0 or not backing or
                            os.path.commonpath([os.path.realpath(backing), root]) != root):
                        continue
                except (OSError, ValueError, subprocess.SubprocessError):
                    continue
            else:
                if os.path.basename(dev).startswith('loop'):
                    continue
                # Real disks must still be present and recognized as whole disks.
                try:
                    probe = subprocess.run(
                        ['lsblk', '-dn', '-o', 'TYPE', dev],
                        capture_output=True, text=True, timeout=5)
                    if probe.returncode != 0 or probe.stdout.strip() != 'disk':
                        continue
                except (OSError, subprocess.SubprocessError):
                    continue
            allowed.add(dev)
        return allowed

    def _is_allowed_pv(self, path: str, allowed: Set[str]) -> bool:
        """Accept exact configured disks or their direct partitions, not prefixes."""
        if not path or not path.startswith('/dev/'):
            return False
        dev = os.path.realpath(path)
        if is_system_disk(dev):
            return False
        if dev in allowed:
            return True
        try:
            probe = subprocess.run(
                ['lsblk', '-dn', '-o', 'PKNAME', dev],
                capture_output=True, text=True, timeout=5)
            if probe.returncode != 0:
                return False
            parent = probe.stdout.strip()
            return bool(parent and os.path.realpath('/dev/' + parent) in allowed)
        except (OSError, subprocess.SubprocessError):
            return False

    def _authorized_vgs(self, allowed: Set[str]) -> Set[str]:
        """A VG is authorized only when ALL of its physical volumes are ours."""
        if not allowed:
            return set()
        try:
            probe = subprocess.run(
                ['pvs', '--noheadings', '-o', 'pv_name,vg_name'],
                capture_output=True, text=True, timeout=5)
            if probe.returncode != 0:
                return set()
            members = {}
            for line in probe.stdout.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    members.setdefault(parts[1], []).append(parts[0])
            return {vg for vg, pvs in members.items()
                    if vg not in get_system_vgs() and
                    all(self._is_allowed_pv(pv, allowed) for pv in pvs)}
        except (OSError, subprocess.SubprocessError):
            return set()

    def _source_allowed(self, source: str, allowed: Set[str], vgs: Set[str]) -> bool:
        """Check exact block source, LVM path or mapper path (including hyphen escape)."""
        if self._is_allowed_pv(source, allowed):
            return True
        if source.startswith('/dev/'):
            parts = source.split('/')
            if len(parts) == 4 and parts[2] in vgs:
                return True
            if source.startswith('/dev/mapper/'):
                encoded = source[len('/dev/mapper/'):]
                return any(encoded.startswith(vg.replace('-', '--') + '-') for vg in vgs)
            if source.startswith('/dev/dm-'):
                try:
                    probe = subprocess.run(
                        ['dmsetup', 'info', '-c', '--noheadings', '-o', 'name', source],
                        capture_output=True, text=True, timeout=5)
                    if probe.returncode == 0:
                        return any(probe.stdout.strip().startswith(vg.replace('-', '--') + '-')
                                   for vg in vgs)
                except (OSError, subprocess.SubprocessError):
                    return False
        return False

    def _detect_practice_device(self) -> Optional[str]:
        """Never auto-adopt an unregistered disk, even when it looks unused."""
        devices = sorted(self._configured_devices())
        self._practice_device = devices[0] if devices else None
        return self._practice_device

    def get_practice_device(self) -> Optional[str]:
        """Refresh authorization whenever a device is requested."""
        return self._detect_practice_device()

    # ===== Resource Tracking =====

    def track_resource(self, resource_type: ResourceType, identifier: str,
                       task_id: Optional[str] = None, **metadata):
        """
        Track a resource for later cleanup.

        Args:
            resource_type: Type of resource (LV, mount, user, etc.)
            identifier: Unique identifier (path, name, etc.)
            task_id: Task that created this resource (uses current if None)
            metadata: Additional info for cleanup (e.g., vg_name for LV)
        """
        task = task_id or self._current_task_id or "unknown"

        # Check if already tracked
        for res in self._tracked_resources:
            if res.resource_type == resource_type and res.identifier == identifier:
                self.logger.debug(f"Resource already tracked: {resource_type.value} {identifier}")
                return

        resource = TrackedResource(
            resource_type=resource_type,
            identifier=identifier,
            task_id=task,
            metadata=metadata
        )
        self._tracked_resources.append(resource)
        self.logger.info(f"Tracking {resource_type.value}: {identifier} for task {task}")

    def untrack_resource(self, resource_type: ResourceType, identifier: str):
        """Remove a resource from tracking."""
        self._tracked_resources = [
            r for r in self._tracked_resources
            if not (r.resource_type == resource_type and r.identifier == identifier)
        ]

    def get_tracked_resources(self, task_id: Optional[str] = None) -> List[TrackedResource]:
        """Get tracked resources, optionally filtered by task."""
        if task_id:
            return [r for r in self._tracked_resources if r.task_id == task_id]
        return self._tracked_resources.copy()

    # ===== Auto-Detection of Created Resources =====

    def scan_for_new_resources(self, task_id: str):
        """Discover LVM, mounts, and swaps only on explicitly authorized disks."""
        allowed = self._configured_devices()
        if not allowed:
            return
        vgs = self._authorized_vgs(allowed)
        try:
            result = subprocess.run(
                ['pvs', '--noheadings', '-o', 'pv_name,vg_name'],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if parts and self._is_allowed_pv(parts[0], allowed):
                        self.track_resource(ResourceType.PHYSICAL_VOLUME, parts[0], task_id)
                        if len(parts) >= 2 and parts[1] in vgs:
                            self.track_resource(ResourceType.VOLUME_GROUP, parts[1], task_id)
        except Exception as exc:
            self.logger.debug('PV scan: %s', exc)
        if vgs:
            try:
                result = subprocess.run(
                    ['lvs', '--noheadings', '-o', 'lv_path,vg_name'],
                    capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if len(parts) == 2 and parts[1] in vgs:
                            self.track_resource(ResourceType.LOGICAL_VOLUME, parts[0], task_id,
                                                vg_name=parts[1])
            except Exception as exc:
                self.logger.debug('LV scan: %s', exc)
        try:
            result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == 'on':
                        source, target = parts[0], parts[2]
                        if ((target.startswith('/mnt/') or target.startswith('/srv/'))
                                and self._source_allowed(source, allowed, vgs)):
                            self.track_resource(ResourceType.MOUNT_POINT, target, task_id)
        except Exception as exc:
            self.logger.debug('Mount scan: %s', exc)
        try:
            result = subprocess.run(['swapon', '--show=NAME', '--noheadings'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for source in result.stdout.splitlines():
                    source = source.strip()
                    if self._source_allowed(source, allowed, vgs):
                        self.track_resource(ResourceType.SWAP, source, task_id)
        except Exception as exc:
            self.logger.debug('Swap scan: %s', exc)

    # ===== Cleanup Operations =====

    def cleanup_task_resources(self, task_id: str, force: bool = False) -> bool:
        """
        Clean up all resources created by a specific task.

        Args:
            task_id: Task to clean up
            force: Continue cleanup even on errors

        Returns:
            True if all cleaned successfully
        """
        if not self._cleanup_enabled:
            self.logger.info("Cleanup disabled, skipping")
            return True

        if self._dry_run:
            self.logger.info('[DRY RUN] Skipping task cleanup and discovery')
            return True

        # First scan for any untracked resources
        self.scan_for_new_resources(task_id)

        resources = self.get_tracked_resources(task_id)
        if not resources:
            self.logger.info(f"No resources to clean up for task {task_id}")
            # Still do a safety cleanup of the practice device
            return self._safety_cleanup()

        # Sort by cleanup order
        resources.sort(key=lambda r: r.cleanup_order)

        self.logger.info(f"Cleaning up {len(resources)} resources for task {task_id}")
        all_success = True

        for resource in resources:
            try:
                success = self._cleanup_resource(resource)
                if success:
                    self.untrack_resource(resource.resource_type, resource.identifier)
                else:
                    all_success = False
                    if not force:
                        self.logger.error(f"Cleanup failed for {resource.identifier}, stopping")
                        break
            except Exception as e:
                self.logger.error(f"Error cleaning {resource.identifier}: {e}")
                all_success = False
                if not force:
                    break

        # Always do safety cleanup at the end
        return self._safety_cleanup() and all_success

    def cleanup_all_resources(self, force: bool = True) -> bool:
        """Clean up ALL tracked resources."""
        task_ids = set(r.task_id for r in self._tracked_resources)
        all_success = True
        for task_id in task_ids:
            if not self.cleanup_task_resources(task_id, force=force):
                all_success = False
        return all_success

    def _cleanup_resource(self, resource: TrackedResource) -> bool:
        """Clean up a single resource."""
        rtype = resource.resource_type
        identifier = resource.identifier

        if self._dry_run:
            self.logger.info(f"[DRY RUN] Would clean {rtype.value}: {identifier}")
            return True

        self.logger.info(f"Cleaning {rtype.value}: {identifier}")

        try:
            if rtype == ResourceType.MOUNT_POINT:
                return self._cleanup_mount(identifier)
            elif rtype == ResourceType.SWAP:
                return self._cleanup_swap(identifier)
            elif rtype == ResourceType.FSTAB_ENTRY:
                return self._cleanup_fstab(identifier)
            elif rtype == ResourceType.LOGICAL_VOLUME:
                return self._cleanup_lv(identifier, resource.metadata)
            elif rtype == ResourceType.VOLUME_GROUP:
                return self._cleanup_vg(identifier)
            elif rtype == ResourceType.PHYSICAL_VOLUME:
                return self._cleanup_pv(identifier)
            elif rtype == ResourceType.USER:
                return self._cleanup_user(identifier)
            elif rtype == ResourceType.GROUP:
                return self._cleanup_group(identifier)
            elif rtype == ResourceType.FILE:
                return self._cleanup_file(identifier)
            elif rtype == ResourceType.DIRECTORY:
                return self._cleanup_directory(identifier)
            else:
                self.logger.warning(f"Unknown resource type: {rtype}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to clean {rtype.value} {identifier}: {e}")
            return False

    def _safety_cleanup(self) -> bool:
        """Clean only explicitly authorized practice devices and their LVM."""
        if self._dry_run:
            return True
        allowed = self._configured_devices()
        if not allowed:
            self.logger.warning('Cleanup skipped: no authorized practice devices')
            return False
        # Refuse partial teardown when a VG spans practice and foreign disks,
        # or when we cannot obtain a complete PV inventory.
        try:
            inventory = subprocess.run(
                ['pvs', '--noheadings', '-o', 'pv_name,vg_name'],
                capture_output=True, text=True, timeout=5)
            if inventory.returncode != 0:
                return False
            members = {}
            for line in inventory.stdout.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    members.setdefault(parts[1], []).append(parts[0])
            for vg, paths in members.items():
                ownership = [self._is_allowed_pv(path, allowed) for path in paths]
                if any(ownership) and not all(ownership):
                    self.logger.warning('Refusing mixed-ownership VG %s', vg)
                    return False
        except Exception as exc:
            self.logger.warning('Could not verify PV inventory: %s', exc)
            return False
        vgs = self._authorized_vgs(allowed)
        success = True
        # Preserve mappings in fstab before removing the associated VGs.
        self._cleanup_practice_fstab_entries()

        def run_destructive(args):
            nonlocal success
            try:
                result = subprocess.run(args, capture_output=True, timeout=15)
                if result.returncode != 0:
                    success = False
                    self.logger.warning('Cleanup failed: %s', args)
            except Exception as exc:
                success = False
                self.logger.warning('Cleanup error %s: %s', args, exc)

        try:
            mounts = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
            if mounts.returncode == 0:
                for line in mounts.stdout.splitlines():
                    parts = line.split()
                    if (len(parts) >= 3 and parts[1] == 'on' and
                            parts[2] not in ('/', '/boot', '/boot/efi', '/home', '/var', '/tmp')
                            and self._source_allowed(parts[0], allowed, vgs)):
                        run_destructive(['umount', '-f', parts[2]])
            else:
                success = False
        except Exception:
            success = False

        try:
            swaps = subprocess.run(['swapon', '--show=NAME', '--noheadings'],
                                   capture_output=True, text=True, timeout=5)
            if swaps.returncode == 0:
                for source in swaps.stdout.splitlines():
                    source = source.strip()
                    if self._source_allowed(source, allowed, vgs):
                        run_destructive(['swapoff', source])
            else:
                success = False
        except Exception:
            success = False

        try:
            result = subprocess.run(['lvs', '--noheadings', '-o', 'lv_path,vg_name'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1] in vgs:
                        run_destructive(['lvremove', '-f', parts[0]])
            else:
                success = False
        except Exception:
            success = False

        if not success:
            return False
        for vg in sorted(vgs):
            run_destructive(['vgremove', '-f', vg])
        if not success:
            return False

        try:
            result = subprocess.run(['pvs', '--noheadings', '-o', 'pv_name,vg_name'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if parts and self._is_allowed_pv(parts[0], allowed):
                        run_destructive(['pvremove', '-f', '-y', parts[0]])
            else:
                success = False
        except Exception:
            success = False

        if not success:
            return False
        # Wipe only the configured whole devices, never unrelated /dev/loopN.
        for dev in sorted(allowed):
            run_destructive(['wipefs', '-a', dev])
        return success

    def _cleanup_mount(self, mount_point: str) -> bool:
        """Unmount a filesystem."""
        allowed = self._configured_devices()
        vgs = self._authorized_vgs(allowed)
        try:
            probe = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '--mountpoint', mount_point],
                                   capture_output=True, text=True, timeout=5)
            if (probe.returncode != 0 or mount_point in ('/', '/boot', '/home', '/var', '/tmp')
                    or not self._source_allowed(probe.stdout.strip(), allowed, vgs)):
                return False
        except Exception:
            return False
        result = subprocess.run(
            ['umount', '-f', mount_point],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_swap(self, device: str) -> bool:
        """Deactivate swap."""
        if not self._source_allowed(device, self._configured_devices(),
                                    self._authorized_vgs(self._configured_devices())):
            return False
        result = subprocess.run(
            ['swapoff', device],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_fstab(self, identifier: str) -> bool:
        """Remove an entry from /etc/fstab."""
        return self._remove_fstab_entry(identifier)

    def _cleanup_lv(self, lv_path: str, metadata: Dict) -> bool:
        """Remove a logical volume."""
        allowed = self._configured_devices()
        vgs = self._authorized_vgs(allowed)
        if not self._source_allowed(lv_path, allowed, vgs):
            return False
        # Only unmount this exact authorized LV's mount sources.
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            parts = line.split()
            if (len(parts) >= 3 and parts[1] == 'on' and
                    (parts[0] == lv_path or
                     (parts[0].startswith('/dev/mapper/') and
                      self._source_allowed(parts[0], allowed, vgs) and
                      metadata.get('lv_name') and
                      parts[0].endswith('-' + str(metadata['lv_name']).replace('-', '--'))))):
                unmount = subprocess.run(['umount', '-f', parts[2]],
                                         capture_output=True, timeout=10)
                if unmount.returncode != 0:
                    return False
        # Failure of swapoff for a non-swap LV is expected; do not block.
        subprocess.run(['swapoff', lv_path], capture_output=True, timeout=5)

        # Remove the LV
        result = subprocess.run(
            ['lvremove', '-f', lv_path],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_vg(self, vg_name: str) -> bool:
        """Remove a volume group."""
        if vg_name not in self._authorized_vgs(self._configured_devices()):
            return False
        result = subprocess.run(
            ['vgremove', '-f', vg_name],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_pv(self, device: str) -> bool:
        """Remove a physical volume."""
        if not self._is_allowed_pv(device, self._configured_devices()):
            return False
        result = subprocess.run(
            ['pvremove', '-f', '-y', device],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_user(self, username: str) -> bool:
        """Remove a user."""
        # Don't remove system users
        if username in ['root', 'austin', 'nobody', 'systemd-network']:
            return True
        result = subprocess.run(
            ['userdel', '-rf', username],
            capture_output=True, timeout=15
        )
        return result.returncode == 0

    def _cleanup_group(self, groupname: str) -> bool:
        """Remove a group."""
        # Don't remove system groups
        if groupname in ['root', 'wheel', 'users', 'nobody']:
            return True
        result = subprocess.run(
            ['groupdel', groupname],
            capture_output=True, timeout=10
        )
        return result.returncode == 0

    def _cleanup_file(self, filepath: str) -> bool:
        """Remove a file."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except Exception:
            return False

    def _cleanup_directory(self, dirpath: str) -> bool:
        """Remove a directory."""
        # Don't remove system directories
        if dirpath in ['/', '/home', '/root', '/etc', '/var', '/tmp', '/mnt']:
            return True
        try:
            if os.path.exists(dirpath):
                import shutil
                shutil.rmtree(dirpath)
            return True
        except Exception:
            return False

    def _remove_fstab_entry(self, identifier: str) -> bool:
        """Delete only fstab lines whose block sources are explicitly authorized."""
        allowed = self._configured_devices()
        vgs = self._authorized_vgs(allowed)
        try:
            with open('/etc/fstab', 'r') as fh:
                lines = fh.readlines()
            kept = []
            for line in lines:
                parts = line.split()
                if (len(parts) >= 2 and not line.lstrip().startswith('#')
                        and identifier in (parts[0], parts[1])
                        and self._source_allowed(parts[0], allowed, vgs)):
                    self.logger.info('Removing authorized fstab entry: %s', line.strip())
                else:
                    kept.append(line)
            if kept != lines:
                with open('/etc/fstab', 'w') as fh:
                    fh.writelines(kept)
            return True
        except Exception as exc:
            self.logger.error('fstab cleanup failed: %s', exc)
            return False

    def _cleanup_practice_fstab_entries(self):
        """Keep unrelated fstab entries; only remove exact authorized block sources."""
        allowed = self._configured_devices()
        vgs = self._authorized_vgs(allowed)
        if not allowed:
            return
        try:
            with open('/etc/fstab', 'r') as fh:
                lines = fh.readlines()
            kept = []
            for line in lines:
                parts = line.split()
                if (len(parts) >= 2 and not line.lstrip().startswith('#')
                        and self._source_allowed(parts[0], allowed, vgs)):
                    self.logger.info('Removing authorized fstab entry: %s', line.strip())
                else:
                    kept.append(line)
            if kept != lines:
                with open('/etc/fstab', 'w') as fh:
                    fh.writelines(kept)
        except Exception as exc:
            self.logger.error('fstab cleanup failed: %s', exc)

    # ===== Context Manager =====

    @contextmanager
    def task_context(self, task_id: str, auto_cleanup: bool = True):
        """
        Context manager for task execution with automatic cleanup.

        Usage:
            with device_manager.task_context("task_001") as dm:
                device = dm.get_practice_device()
                # User completes task
            # Automatic cleanup happens here

        Args:
            task_id: Unique identifier for the task
            auto_cleanup: Whether to clean up on exit (default True)
        """
        self._current_task_id = task_id
        self.logger.info(f"Starting task context: {task_id}")

        try:
            yield self
        finally:
            self.logger.info(f"Ending task context: {task_id}")
            if auto_cleanup and self._cleanup_enabled:
                self.cleanup_task_resources(task_id, force=True)
            self._current_task_id = None

    # ===== Configuration =====

    def enable_cleanup(self):
        """Enable automatic cleanup."""
        self._cleanup_enabled = True

    def disable_cleanup(self):
        """Disable automatic cleanup (for debugging)."""
        self._cleanup_enabled = False

    def set_dry_run(self, dry_run: bool):
        """Enable/disable dry run mode."""
        self._dry_run = dry_run

    # ===== State =====

    def get_state(self) -> Dict:
        """Get current state for session save."""
        return {
            'practice_device': self._practice_device,
            'tracked_resources': [
                {
                    'type': r.resource_type.value,
                    'identifier': r.identifier,
                    'task_id': r.task_id,
                    'metadata': r.metadata
                }
                for r in self._tracked_resources
            ]
        }

    def get_statistics(self) -> Dict:
        """Get device manager statistics."""
        return {
            'practice_device': self._practice_device,
            'tracked_resources': len(self._tracked_resources),
            'cleanup_enabled': self._cleanup_enabled,
            'resources_by_type': {
                rtype.value: len([r for r in self._tracked_resources if r.resource_type == rtype])
                for rtype in ResourceType
            }
        }


# Global instance getter
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """Get the global DeviceManager instance."""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
