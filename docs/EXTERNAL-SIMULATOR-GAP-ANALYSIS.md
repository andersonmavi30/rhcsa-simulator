# External RHCSA Simulator Gap Analysis

**Analysis date:** 2026-11-21  
**Primary repository:** `andersonmavi30/rhcsa-simulator`  
**Primary baseline:** `develop@a8c652a`  
**Reference fork:** `andersonmavi30/rhcsa-exam-simulator`  
**Reference baseline:** `main@bfd5fc1`

## Purpose

This document compares the reference Bash simulator with our Python simulator.
The reference repository is read-only research material: all useful capabilities
must be adapted to our architecture, safety model, tests, and RHCSA study
workflow. It is not a candidate for a wholesale merge.

The authoritative syllabus is the current Red Hat EX200 page:

- https://www.redhat.com/en/services/training/ex200-red-hat-certified-system-administrator-rhcsa-exam

As of this analysis, EX200 is based on RHEL 10 and explicitly requires
configurations to persist after reboot.

## Executive conclusion

The reference simulator is stronger in exam-environment fidelity:

- real reboot followed by automatic grading;
- first-class single-node and two-node papers;
- one controller that seeds, grades, reports, and resets both nodes;
- `doctor` readiness diagnostics;
- offline BaseOS/AppStream and Flatpak repositories from the RHEL DVD;
- 281 task directories, parameterized prompts, conflict controls, and a
  solver-based integration harness;
- combined reports and browser-based VM controls.

Our simulator is the better long-term foundation:

- modular Python architecture and task registry;
- adaptive SM-2 study workflow, history, progress snapshots, and dashboard;
- safe, timeout-protected, read-only validators;
- hardened disk authorization and reset protections;
- loop-device practice disks;
- token-protected browser panel and checker-dispute workflow;
- real boot-rescue practice on a linked lab machine;
- structured unit and E2E test suite.

The correct strategy is therefore to port selected capabilities into our
Python codebase while preserving our safety and learning model.

## Inventory snapshot

| Area | Reference fork | Our simulator |
|---|---:|---:|
| Advertised tasks | 250+ templates per release | 188 tasks |
| Concrete task directories/classes inspected | 281 directories | 185 standard registered task classes plus specialized flows |
| Main implementation | Bash + small Python UI/report layer | Python |
| Test artifacts | 281 task solvers plus harness scripts | 57 unit/E2E test files |
| Real post-reboot grading | Yes | No; currently simulated |
| Two-node controller | Yes | Partial linked-machine support |
| Adaptive spaced repetition | Weak-area selection only | Yes, SM-2 |
| Progress portability | Basic history/stats | Versioned export/import code |
| Disk/reset safety | Disposable-VM assumptions | Strong authorization and wipe guards |

Task counts are not directly comparable. The reference repository contains
legacy exam-paper variants (`e1-*`, `e2-*`, `e3-*`, `f08-*`), RHEL
9-only tasks, and near-duplicates. They must not be counted as automatic gaps.

## Capability decisions

| Capability from reference | Current state in ours | Decision | Priority |
|---|---|---|---|
| Real `grade --reboot` workflow | Simulated persistence validation | Reimplement in Python with resumable state and systemd | P0 |
| `doctor` environment diagnostics | Package preflight only | Expand into a complete non-mutating readiness command | P0 |
| Two-node paper/controller | Three remote tasks and linked lab machine | Extend current architecture; do not replace it | P0 |
| Combined two-node score/report | Missing | Add after controller protocol | P0 |
| OS/RHEL version auto-detection | Version selected by option | Auto-detect by default, retain explicit developer override | P1 |
| Offline DVD repositories | Missing as a managed workflow | Add BaseOS/AppStream and offline Flatpak preparation | P1 |
| Parameter generator | Random values exist per Python task | Standardize generators, uniqueness, seeds, and reproducibility | P1 |
| Conflict groups/resource scheduler | Partial disk-slot handling | Add generic conflicts and one destructive storage task per disk | P1 |
| Fixed exam blueprints | Dynamic exam assembly | Add versioned blueprints and deterministic random seed | P1 |
| Solver per task | Unit/E2E tests, no golden solution for every task | Add Python integration/golden-path tests | P1 |
| Browser VM controls | Secure task panel, no full node control | Extend only after safe two-node controller exists | P2 |
| Text TUI | CLI already available | Do not port separately | — |
| Weak-only practice | Adaptive mode is stronger | Keep ours | — |
| Destructive reset | Reference may delete regular users | Reject completely | — |
| Bash task-directory architecture | Different from our registry | Do not port | — |

## Task-content disposition

### A. Core RHEL 10 candidates

These reference tasks expose meaningful depth or missing variants and should be
mapped to Python tasks after verifying overlap:

- Essential tools: `grep-context`, `grep-count`, `grep-invert`,
  `find-mtime`, `find-name-type`, `find-size`, `head-tail-range`,
  `sed-replace`, `uniq-count`, `tar-bzip2`.
- Scripting: `script-argcount`, `script-arith`, `script-backupdir`,
  `script-filetest`, `script-finder`, `script-readstdin`,
  `script-sumloop`, `script-userexists`, `script-while-read`.
- Running systems: `cpu-hog-find`, `mem-hog-find`, `failed-units`,
  `journal-priority`, `tuned-specific`, `rsync-dir`.
- Filesystems/NFS: `ext4-label`, `label-mount`, `fstab-nofail`,
  `autofs-direct`, `autofs-wildcard`, `nfs-readonly`.
- Storage: `gpt-name`, `lv-fs-xfs-uuid`, `swap-by-label`,
  `swap-uuid`, `swap-priority`, `two-partitions`.
- Networking: `network-route`, `network-secondary-ip`,
  `nmcli-autoconnect`.
- Users/privilege: `password-force-change`, `password-minage`,
  `sudo-group-passwd`, `sudo-nopasswd`, `sudo-user-cmd`,
  `user-home-custom`, `user-primary-group`, `user-supplementary`.
- Security: `umask-systemwide`, `selinux-context-copy`,
  `selinux-fcontext-equal`, `ssh-key-target`, `ssh-key-peer`.

These are candidates, not an instruction to copy every prompt. Each candidate
needs an objective mapping, duplicate check, safe setup/teardown, validator,
and tests.

### B. Official-objective gaps to add even if the reference is weak

The official RHEL 10 objectives require explicit evidence for these areas:

- locate and use `man`, `info`, and `/usr/share/doc`;
- create and edit text files;
- remove physical volumes and volume groups, not only logical volumes;
- delete/modify local groups and memberships;
- install/update software from a local file or offline repository;
- inspect SELinux process contexts;
- normal boot, reboot, and shutdown operations;
- persistence after a real reboot.

### C. Challenge-mode candidates

Useful administration topics that are not required as core EX200 RHEL 10
coverage may be retained for Challenge mode:

- `lv-snapshot`, `lv-rename`, `pv-move`, `vg-pe-size`;
- `nfs-export`, `ntp-server`, `repo-server`;
- `firewall-masquerade`, `sysctl-set`;
- `file-immutable`, `faillock-config`, `restrict-su`,
  `selinux-user-map`;
- RAID and SMB/CIFS items from the old V3 plan.

Challenge content must never inflate the advertised EX200 objective coverage.

### D. Exclude from the RHEL 10 core

- all RHEL 9-only container tasks;
- MBR partitioning;
- set-GID collaboration tasks when used only for the retired RHEL 9 objective;
- server-side NFS/repository/NTP administration as required exam content;
- legacy paper duplicates prefixed `e1-`, `e2-`, `e3-`, or `f08-`;
- any reset behavior that deletes non-practice users or modifies unapproved
  storage.

## Architecture adaptation rules

1. Reimplement features in Python; do not embed the reference Bash runtime.
2. Preserve MIT copyright and license notices for any substantial copied code.
3. Rewrite task wording against public EX200 objectives rather than copying
   third-party exam language.
4. Every destructive action must pass our existing disk, mount, partition, PV,
   VG, and authorization guards.
5. Every new task requires setup, validation, teardown, persistence behavior,
   unit tests, and at least one golden-path integration test.
6. RHEL 10 is the release target. RHEL 9 remains a compatibility track, not the
   driver for new core development.
7. One feature per branch and pull request.

## Recommended implementation order

1. Complete the five-mode product model and Study Tracker already planned.
2. Add objective coverage manifest and `doctor`.
3. Replace reboot simulation with opt-in real post-reboot grading.
4. Extend linked-machine support into a safe two-node controller and combined
   report.
5. Add offline DVD repositories and Flatpak repository preparation.
6. Add deterministic seeds, conflict groups, and versioned exam blueprints.
7. Port only the approved task gaps and variants.
8. Add golden-path solver tests and RHEL 10 integration CI/lab validation.
9. Extend the browser panel with safe VM controls.

See `docs/V3-RELEASE-PLAN.md` for the actionable roadmap.
