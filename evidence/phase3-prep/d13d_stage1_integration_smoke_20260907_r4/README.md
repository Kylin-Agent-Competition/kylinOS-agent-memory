# D13D Stage 1 integration smoke (PREPARATION / NON-FORMAL)

- date: 2026-09-07
- branch / HEAD: `pr160-rework` / `57466ccb9504da75b5da03bbbef1f563a14b4ad4`
- guest runtime: isolated VM directory `/home/kylin-agent/d13d-stage1-integration-smoke-20260907-r4`
- result: PASS

## Verified behavior

1. Real Kylin embedding produced a finite 768-dimensional vector (`l2_norm=0.9999996748602524`).
2. `SqliteVectorProvider.upsert` drove the real `vector_bridge_cli` insert into a unique collection.
3. A same-vector query returned the target `memory_id=1` / `version_id=v1`.
4. `SqliteVectorProvider.delete` removed exactly the confirmed target and retired the ledger entry.
5. A repeat query returned zero hits.
6. The unique collection was dropped after the smoke.

## Evidence

- `integration_smoke.log` is the unmodified combined stdout/stderr transcript.
- `integration_smoke.json` is the structured result extracted from the transcript.
- `commands.log` records the archive/upload/exec command shape.
- `memory-service-head.tar.gz` is the exact PR HEAD source tree uploaded to the isolated VM directory.

This is VM preparation evidence only. It is not formal raw, Seal, Runner Gate 0-10, or `D13D_FROZEN`.
