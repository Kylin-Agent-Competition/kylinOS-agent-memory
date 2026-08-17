# LEGACY Runner Manifest

> **Canonical evidence workflow**: `p0bc_systemd_evidence.py` (systemd path, fail-closed)
> **Generated**: 2026-08-10

All scripts listed below are **HISTORICAL / SUPERSEDED** and must NOT be used as the canonical evidence runner.

---

## Superseded — Replaced by p0bc_systemd_evidence.py

| Script | Reason | Status |
|--------|--------|:------:|
| `p05_final.py` | dev mode `/tmp/` path; superseded by systemd runner | SUPERSEDED |
| `p05_direct_test.py` | dev mode; superseded | SUPERSEDED |
| `rebuild_evidence_p05.py` | writes to `final/evidence.jsonl` (dev mode); superseded | SUPERSEDED |
| `pr21_r3_verify.py` | PR21 R3 specific; replaced by p0bc_systemd_evidence.py | SUPERSEDED |

---

## LEGACY — Historical exploration scripts (DO NOT USE as canonical evidence)

| Script | Hardcoded password placeholder | pkill -f | Status |
|--------|:---:|:---:|:------:|
| `collect_p1_p2_evidence.py` | — | YES | LEGACY |
| `collect_remaining.py` | YES | YES | LEGACY |
| `collect_uds_test.py` | YES | — | LEGACY |
| `fix_and_finalize.py` | YES | YES | LEGACY |
| `r2_standalone.py` | YES | YES | LEGACY |
| `run_all_phases.py` | YES | — | LEGACY |
| `run_d2_1_investigation_v2.py` | YES | YES | LEGACY |
| `run_d2_1_kaiming_hook_investigation.py` | YES | YES | LEGACY |
| `run_day1_kylin_runtime.py` | YES | YES | LEGACY |
| `run_day2_kylin_runtime.py` | YES | YES | LEGACY |
| `run_phase4_tests.py` | YES | — | LEGACY |
| `verify_r2_r3_fix.py` | YES | YES | LEGACY |
| `_download_r3.py` | YES | — | LEGACY |
| `vm_test_runner.py` | — | — | LEGACY |
| `_r3_test_runner.sh` | — | — | LEGACY |

---

## Active Canonical Runners

| Script | Password handling | pkill -f | Purpose |
|--------|:---:|:---:|---------|
| `p0bc_systemd_evidence.py` | `os.environ["KYLIN_VM_PASSWORD"]`, missing → exit(1) | None | **Canonical** systemd L2 evidence |
| `kylin_diag.py` | `os.environ["KYLIN_VM_PASSWORD"]`, missing → exit(1) | None | VM diagnostics |
| `test_kysec_verify.py` | N/A | None | KYSEC test |
| `run_kysec_verify.py` | N/A | None | KYSEC runner |

---

## Historical Evidence (superseded)

| Path | tested_commit | Mode | Status |
|------|---------------|------|:------:|
| `final/evidence.jsonl` | `c9c8143...` | dev | HISTORICAL |
| `systemd_evidence/evidence.jsonl` | (varies) | systemd | **Current canonical target** |
