# RHCSA Simulator Unified Roadmap

**Updated:** 2026-11-21  
**Target:** RHCSA EX200 on RHEL 10  
**Primary branch:** `develop`  
**Reference analysis:** `docs/EXTERNAL-SIMULATOR-GAP-ANALYSIS.md`

> This roadmap supersedes the original V3 plan. Most modules listed in the old
> plan already exist, while several old items such as RAID, SMB/CIFS, MBR, and
> server-side services are not part of the current RHEL 10 EX200 core.
> They may be Challenge content but must not be counted as exam coverage.

## Product goal

Build one safe, reproducible, exam-realistic RHCSA platform that supports:

1. learning concepts;
2. guided hands-on practice;
3. adaptive spaced repetition;
4. full mock exams;
5. advanced challenge scenarios;
6. measurable study progress;
7. real reboot persistence validation;
8. optional two-node exam simulation.

The current Red Hat objective page is the source of truth:

- https://www.redhat.com/en/services/training/ex200-red-hat-certified-system-administrator-rhcsa-exam

## Current baseline

| Area | Current state |
|---|---|
| Content | 188 advertised tasks, 25 categories, 8 RHEL 10 domains |
| Modes | Learn, Practice, Adaptive, Quick Practice, Mock Exam |
| Progress | SQLite history, dashboard, SM-2 state, portable progress code |
| Validation | Safe read-only executor with timeouts and partial-credit checks |
| Storage practice | Loop devices and authorized real-disk mode |
| Safety | Mounted/system/shared-VG/partition ownership wipe protections |
| Remote lab | Linked lab machine, NFS provisioning, remote tasks, Boot Rescue |
| Browser panel | Token-protected tasks, timer, marks, results, reset, disputes |
| Reboot | Simulation only; no real reboot/resume/regrade workflow |
| Multi-node | Partial; no unified two-node paper, lifecycle, or report |
| Offline repositories | No complete RHEL DVD/Flatpak workflow |
| Tests | Unit and E2E suites, with strong disk-safety coverage |

## Delivery rules

- RHEL 10 objective coverage takes priority.
- RHEL 9 remains a compatibility track.
- Challenge-only topics never count toward EX200 coverage.
- New features use Python and the current registry/validator architecture.
- No destructive action bypasses the existing authorization and disk guards.
- Every feature is delivered through its own branch and pull request.
- Every task requires setup, validator, cleanup, persistence metadata, and tests.
- Substantial adapted MIT code retains the required notices.
- Task wording is written from public objectives, not copied from exam dumps.

---

# Milestone 1 — Five modes and Study Tracker

**Priority:** P0  
**Dependency:** current safety baseline  
**Status:** next planned work

## 1.1 Formalize the five-mode model

The public product model will be:

1. **Learn** — concepts, commands, examples, and exam tips.
2. **Practice** — guided tasks, hints, retries, and immediate feedback.
3. **Adaptive** — SM-2 selection of weak and overdue categories.
4. **Exam** — timed, aid-free, weighted, reproducible mock exams.
5. **Challenge** — troubleshooting, advanced variants, and non-core topics.

`Quick Practice` becomes a Practice preset rather than a sixth pillar.
Boot Rescue remains a specialized lab launched from Practice or Challenge.

### Acceptance criteria

- One consistent menu and CLI vocabulary.
- Each task declares eligible modes.
- Exam mode never exposes hints or solutions.
- Challenge content is visibly separated from RHEL 10 objective coverage.
- Existing results remain readable after the mode migration.

## 1.2 Study Tracker

Create one learning record that combines:

- completed study sessions;
- time spent per domain/category;
- accuracy and partial-credit history;
- SM-2 next-review date;
- weak areas and repeated mistakes;
- bookmarked tasks;
- mock-exam scores and readiness trend;
- daily/weekly study targets;
- notes and command-review queue;
- export to Markdown, CSV/JSON, and an Anki-friendly format;
- portable backup through the existing progress-code mechanism.

### Acceptance criteria

- The tracker survives reinstall and schema upgrades.
- Dashboard values are derived from recorded evidence.
- Import supports preview plus merge/replace.
- The next recommended session is generated from weak, overdue, and uncovered
  objectives.
- Unit tests cover migrations, merge behavior, and corrupted input.

---

# Milestone 2 — Objective manifest and Doctor

**Priority:** P0  
**Dependency:** Milestone 1 data model

## 2.1 RHEL 10 objective manifest

Add a machine-readable objective manifest, for example
`config/objectives_rhel10.json`, mapping:

`objective -> category -> task IDs -> mode -> persistence -> lab requirements`

Add an audit command that reports:

- objectives with no task;
- objectives with only one scenario;
- duplicate or near-duplicate task IDs;
- Challenge tasks incorrectly counted as exam coverage;
- tasks missing cleanup, persistence metadata, or tests.

Do not advertise 100% coverage until the manifest passes.

## 2.2 `doctor` command

Expand the existing preflight into a non-mutating readiness command:

- supported distribution and detected RHEL major version;
- Python and required commands;
- root/systemd/SELinux state;
- free space and loop-device support;
- authorized practice-device state;
- mounted filesystem/PV/VG safety;
- required packages by selected mode;
- local ISO/repository availability;
- optional NFS and linked-machine reachability;
- SSH trust for two-node work;
- browser-panel bind/firewall warning;
- clear green/yellow/red remediation output.

## 2.3 Automatic version detection

- Detect RHEL/Rocky/Alma/CentOS Stream major version.
- Default content to the installed OS version.
- Retain `--exam-version` only as an explicit development/test override.
- Refuse incompatible destructive tasks.

### Acceptance criteria

- `doctor` never modifies the host.
- Tests cover RHEL 9/10, unsupported systems, missing packages, unsafe disks,
  absent ISO, and unreachable lab machines.
- Objective audit is deterministic and CI-friendly.

---

# Milestone 3 — Real post-reboot grading

**Priority:** P0  
**Dependency:** Doctor and stable session state

Replace the current simulated reboot with an opt-in real workflow while keeping
simulation available for fast Practice sessions.

## Components

1. Serialize the exam, generated parameters, initial results, deadline, and
   expected persistence checks to a root-owned state file.
2. Install a tightly scoped systemd one-shot resume/grading service.
3. Request explicit confirmation before reboot.
4. Reboot normally and resume without regenerating tasks.
5. Revalidate persistent tasks after the host returns.
6. Record lost points and boot blockers.
7. Generate a recovery command if automatic resume fails.
8. Remove transient service/state safely after completion.

## CLI target

- `rhcsa-simulator --exam --real-reboot`
- `rhcsa-simulator --resume-exam`
- `rhcsa-simulator --exam --simulate-reboot`

### Acceptance criteria

- The task set and random values remain unchanged across reboot.
- The timer uses monotonic/boot-safe accounting.
- A correct persistent configuration passes after a real reboot.
- A transient-only configuration loses the correct checkpoints.
- Interrupted grading can be resumed idempotently.
- No credentials are stored world-readable.
- E2E validation is performed on a disposable RHEL 10 VM.

---

# Milestone 4 — Safe two-node exam controller

**Priority:** P0  
**Dependency:** real reboot state model and linked-machine safety

Extend the existing linked lab machine rather than importing the reference
controller unchanged.

## Components

- explicit node1/controller and node2/worker roles;
- safe SSH trust setup and verification;
- two-node exam blueprint;
- node-specific task groups and generated parameters;
- remote setup, validation, cleanup, and restore;
- independent reboot/resume on each node;
- combined score and per-node evidence;
- reachability/timeouts and partial-failure handling;
- safe reset that preserves real users, network, SSH, and system disks;
- optional node status/reboot controls in the browser panel.

## Initial remote task expansion

- SSH key authentication between nodes;
- secure copy and rsync;
- hostname and hosts-file resolution;
- user/group management;
- timezone/time-client configuration;
- NFS client and autofs tasks;
- selected service/firewall/SELinux scenarios.

### Acceptance criteria

- One controller command starts, grades, reports, and resets both nodes.
- Node2 never needs the full simulator installed unless explicitly selected.
- Combined reports retain per-node checkpoint detail.
- A failed/unreachable node does not corrupt the controller state.
- Reset previews every remote action and touches only simulator-owned artifacts.

---

# Milestone 5 — Offline RHEL repositories

**Priority:** P1  
**Dependency:** Doctor

## Components

- detect a matching RHEL DVD ISO/CD-ROM;
- mount it read-only;
- create simulator-owned BaseOS/AppStream repo definitions;
- validate `dnf repolist` and package installation;
- restore/remove only simulator-owned repo files;
- prepare or document an offline Flatpak repository workflow;
- integrate repository state into Doctor and exam prerequisites;
- never commit or redistribute Red Hat ISO/package content.

### Acceptance criteria

- A disconnected disposable RHEL 10 VM can complete package tasks.
- Existing user repositories are preserved.
- Cleanup removes only files tagged/owned by the simulator.
- Wrong-version media is rejected clearly.

---

# Milestone 6 — Deterministic exam composition

**Priority:** P1  
**Dependency:** objective manifest

Adapt the best composition ideas from the reference simulator:

- deterministic `--seed` support;
- versioned exam blueprints and domain weighting;
- no repeated task/scenario in one session;
- unique generated users, groups, ports, paths, and output files;
- generic conflict groups;
- device-slot allocation;
- at most one destructive whole-disk task per approved device;
- RHEL-version and lab-requirement filtering;
- reproducible paper export for debugging without exposing solutions.

### Acceptance criteria

- The same version/seed/blueprint produces the same paper.
- Different seeds produce meaningful variation.
- No generated identifiers collide.
- Storage, network, service, and remote tasks cannot corrupt each other's setup.
- Blueprint validation runs in CI.

---

# Milestone 7 — RHEL 10 task-depth expansion

**Priority:** P1  
**Dependency:** objective audit and composition engine

The 281 reference directories are a research pool, not a target count.
Candidates are implemented only after semantic duplicate review.

## Batch A — Essential tools

- grep context/count/invert variants;
- find by mtime/name/type/size;
- head/tail ranges;
- sed replacement and uniq counting;
- bzip2-focused archive workflow;
- explicit documentation lookup using man/info/`/usr/share/doc`;
- create/edit text-file scenario.

## Batch B — Scripting

- argument-count validation;
- arithmetic;
- backup-directory script;
- file tests;
- find/process script;
- standard-input processing;
- summation loop;
- user-existence check;
- while-read loop.

## Batch C — Running systems and services

- independent CPU-hog and memory-hog diagnosis;
- failed-unit diagnosis;
- journal priority filtering;
- specific tuned-profile selection;
- secure directory synchronization;
- normal reboot/shutdown lifecycle task where safe.

## Batch D — Storage, filesystems, NFS

- filesystem labels and label-based persistent mounts;
- `nofail` behavior;
- direct and wildcard autofs maps;
- read-only NFS client mount;
- UUID-based LV/filesystem workflow;
- swap by label/UUID and swap priority;
- multi-partition GPT workflow;
- PV and VG removal tasks.

## Batch E — Networking and remote access

- persistent static route;
- secondary address;
- NetworkManager autoconnect behavior;
- cross-node SSH key task;
- cross-node secure-copy/rsync task;
- explicit SELinux process-context inspection.

## Batch F — Users, privilege, security

- forced password change and minimum age;
- custom home and primary/supplementary-group variants;
- group modify/delete tasks;
- command-scoped sudo, group sudo, and NOPASSWD variants;
- system-wide and per-user umask;
- SELinux equivalent-context and context-copy variants.

## Batch G — Challenge-only backlog

- LVM snapshot/rename, PV move, custom VG extent size;
- NFS/repository/NTP server scenarios;
- firewall masquerading and sysctl;
- faillock, immutable files, restrict-su, SELinux user mapping;
- RAID and SMB/CIFS if still useful for broader administration practice.

### Acceptance criteria per task

- official-objective or Challenge classification;
- no semantic duplicate;
- randomized but reproducible values;
- safe setup and teardown;
- read-only validation;
- persistence metadata;
- unit tests;
- golden-path integration test;
- verified on RHEL 10.

---

# Milestone 8 — Reports, browser controls, and integration testing

**Priority:** P2  
**Dependency:** two-node controller and expanded content

## Reports

- combined node1/node2 score;
- per-checkpoint evidence;
- pre/post-reboot comparison;
- objective-coverage and weak-area summaries;
- Markdown/HTML/JSON export;
- Study Tracker linkage.

## Browser panel

- node status and reachability;
- safe reboot/shutdown controls with confirmation;
- combined results;
- recovery instructions;
- no unauthenticated state-changing endpoint;
- bind to localhost by default, with token required for every action.

## Golden-path testing

Adapt the reference solver concept into our test architecture:

- one known-correct solution driver per high-risk task family;
- negative test for common false positives;
- setup -> solve -> validate -> reboot/persist -> cleanup lifecycle;
- RHEL 10 VM integration matrix;
- RHEL 9 compatibility regression subset;
- storage tests only on disposable authorized devices.

### Acceptance criteria

- Every P0/P1 feature has unit and E2E coverage.
- High-risk task families pass a real VM golden-path run.
- Reports reconcile exactly with stored checkpoint results.
- Browser controls cannot bypass CLI safety checks.

---

# Immediate execution queue

Complete these in order, one focused unit at a time:

1. Run and record the complete current unit/E2E baseline.
2. Define the five-mode contract and migration plan.
3. Implement/finish Challenge classification and mode eligibility.
4. Design the Study Tracker schema and migration.
5. Implement Study Tracker recording, dashboard, and exports.
6. Add the RHEL 10 objective manifest.
7. Add the objective coverage audit command.
8. Implement the read-only `doctor` command.
9. Design the real-reboot state machine and threat model.
10. Implement real reboot/resume behind an explicit experimental flag.
11. Extend the linked machine into the two-node controller.
12. Add combined reports.
13. Add offline DVD repositories.
14. Add deterministic seeds, conflicts, and blueprints.
15. Begin task expansion in the batches above.

## Definition of the “super repo”

The unified repository is complete when it provides:

- the five learning/exam modes;
- a durable Study Tracker;
- verified RHEL 10 objective coverage;
- real post-reboot grading;
- optional safe two-node exams;
- offline package practice;
- deterministic and conflict-free papers;
- broad task variation without duplicate inflation;
- strong unit, E2E, and golden-path validation;
- safe cleanup that preserves everything not owned by the simulator.
