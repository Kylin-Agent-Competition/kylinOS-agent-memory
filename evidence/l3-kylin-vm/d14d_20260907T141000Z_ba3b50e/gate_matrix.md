# Gate Matrix

| Gate | Status | Evidence |
|---|---|---|
| G0 baseline | PASS | `raw/g0_baseline.log`, `raw/g0_packages.log` |
| G1 clean snapshot | PASS | `raw/g0_baseline.log` positive gate, `raw/g1_negative_gate.log` fail-closed proof |
| G2 package audit | PASS | `raw/g2_package_audit.log`, `raw/g2_dependency_audit.log`, `raw/g2_targeted_path_audit.log` |
| G3 install | PASS | `raw/g3_install.log` |
| G4 real SDK | PASS | `raw/g4_embed_server_start.log`, `raw/g4_verify.log` |
| G5 service restart | PASS | `raw/g5_service_restart.log` |
| G6 OS reboot | PASS | `raw/g6_reboot_issued.log`, `raw/g6_post_reboot.log`, `raw/g6_post_reboot_detail.log` |
| G7 upgrade | NOT_RUN / N/A | D-09 arbitration; must not be marked PASS |
| G8 performance | NOT_RUN | D-10 arbitration; package-only runner and thresholds were not approved |
| G9 evidence | READY_FOR_REVIEW | This immutable evidence root and its checksums |

`L3_READY` remains `NO` until an independent non-author review approves this
evidence root.
