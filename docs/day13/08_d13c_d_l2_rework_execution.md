# D13C D Track L2 Rework Execution

- Task source: `08_d13c_l2_requirements_d_track.md` supplied on 2026-09-05.
- Local implementation baseline: record `git rev-parse HEAD` immediately before deployment.
- Current VM observation: the deployed service is `053754d611801548fdac59b2894c6862bf85cf56`; it must not be used as evidence for a later local commit.

## Scope And Boundaries

This batch adds only a read-only L2 evidence collector and its L1 tests. It
does not change FRZ-IPC-001 through FRZ-IPC-007, error codes, database schema,
or the production handler activation policy.

`turn.finalized` and `forget.preview` / `forget.execute` remain blocked until
their separately approved C host mappings are production-ready. The collector
must report those requirements as `BLOCKED`; it must not enable the validation
flags to obtain a misleading production conclusion.

`memory.retrieve` currently returns `data.context=[]`. That is incompatible
with D13C D-L2-04/05 and the stricter C-side candidate parser. Do not replace
it with only the three D13C-named fields: C/D/E must first freeze the complete
empty `MemoryContext` response mapping, including payload identity validation,
`context_version`, timestamps, token budget and the safe `skipped` status.
Until that ADR is approved and implemented, D-L2-04/05 are `BLOCKED` for
release, even though the current baseline collector records them as `FAILED`.

## 2026-09-05 VM Baseline

The disposable VM copy ran the collector against its clean deployed
`053754d611801548fdac59b2894c6862bf85cf56`, not against this working tree.
Its raw host-runner evidence is outside this repository at
`E:\Kylin-memory-dev\evidence\l2-kylin-vm\runs\d13c_rework_baseline_collect_20260905.log`
with SHA-256 `80d04feeae50eb9eabfcecb3b5b47e71830ddb5c13766c2ce5a7173759129b84`.

Observed results: D-L2-01/02/03/06 were `VERIFIED`; retrieve latency was
30 samples, p50 1.703ms and p95 3.656ms. D-L2-04/05 were `FAILED` because
the deployed response was `context=[]`. D-L2-07 through D-L2-20 remained
`BLOCKED` for the reasons recorded by the collector. These are baseline facts,
not evidence for a later commit.

The same VM then ran `PYTHONPATH=memory-service
/home/kylin-agent/d4d-venv/bin/python -m pytest
memory-service/tests/test_gateway_server_d4d.py -q` against that same clean
commit: `12 passed`. The test module covers UDS framing, default routing,
server-side deadline-to-`TIMEOUT`, and stop cleanup. Its host-runner log is
`E:\Kylin-memory-dev\evidence\l2-kylin-vm\runs\d13c_rework_gateway_uds_d4dvenv_053754d_20260905.log`.
This establishes only the existing D service-side behavior; it does not cover
the C++ client's 5000ms state transition or any candidate write handler.

## L2 Procedure

1. Deploy the exact reviewed commit through the existing D deployment process.
   Record its full SHA, service unit content, OS release, SQLite version, and
   `systemctl --user is-active kylin-memory.service` output.
2. Confirm the active socket and database paths without changing them:

```bash
stat -c '%a %n' "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"
systemctl --user is-active kylin-memory.service
```

3. Copy `scripts/d13c_l2_collect.py` from that same commit to the VM checkout
   and run it against the deployed service. The database is opened read-only.

```bash
python3 scripts/d13c_l2_collect.py \
  --socket "$XDG_RUNTIME_DIR/kylin-memory/memory.sock" \
  --db "$HOME/.local/share/kylin-memory/kylin_memory.db" \
  --output-dir "evidence/l2-kylin-vm/d13c_<UTC_RUN_ID>" \
  --tested-commit "<FULL_DEPLOYED_SHA>"
```

4. Verify every file in `SHA256SUMS`, then add an `evidence/index.yaml` entry
   pointing to the report, JSONL envelope log and checksum manifest. Only
   mark `VERIFIED` when the report itself has that status.
5. Run the C-track client deadline and five-round orchestration checks only
   after the C host mappings are activated by their approved change. Attach
   their raw client state and Chat DB query results to the same evidence batch.

## Acceptance Mapping

| Requirement group | Collector coverage | Current expected state |
| --- | --- | --- |
| D-L2-01 to D-L2-03 | socket permission, UDS connection, framed echo | directly testable |
| D-L2-04 to D-L2-05 | complete empty MemoryContext response mapping | BLOCKED pending C/D/E ADR; current `[]` is a known failure |
| D-L2-06 | retrieve latency percentiles | directly testable |
| D-L2-07 to D-L2-10 | Chat DB write and event field persistence | BLOCKED by `turn.finalized` host mapping |
| D-L2-11 to D-L2-12 | client and Gateway deadline behavior | requires C client / approved slow-handler case |
| D-L2-13 to D-L2-17 | precise-forget transactions and ViewModel cleanup | BLOCKED by forget host mapping and C ViewModel |
| D-L2-18 to D-L2-20 | five-step client orchestration and reset | requires C-track deployed pipeline |

## L1 Command

```powershell
& 'C:\Users\jackb\AppData\Local\Programs\Python\Python313\python.exe' -m py_compile scripts\d13c_l2_collect.py
& 'C:\Users\jackb\AppData\Local\Programs\Python\Python313\python.exe' -m pytest memory-service\tests\test_d13c_l2_collect.py -q
```

No L1 result in this document is a Kylin runtime conclusion.
