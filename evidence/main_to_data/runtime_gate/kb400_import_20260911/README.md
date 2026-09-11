# Main-E KB400 one-shot execution receipt — failed before import

## Scope

- Main tested commit: `cf741a3fb9fa706c94e703a83e4441444a0a4f33`
- Data-R reviewed package commit: `b83d0a8ed7b3bde574a74e0abd24fd45b5a4e3b9`
- K3 input: 400 records; SHA-256 `03256f4db271ad39ce9635c157b85d70641c69fffbd96ffbe5554e10fc7bcbb5`
- Frozen source SHA-256 (LF): `7ce8047fbb43eda483e4563dbfa8100c0c2fe5b2836ff742d8f51b1ac288996f`

## Result

```text
RECEIPT_STATUS = COMPLETE_FAIL
MAIN_E_EXECUTION_STATUS = FAILED
production_path_used = false
mock_used = false
exit_code = 2
```

The canonical Main `event.ingest` path fail-closed at
`data-prebinding:os_kb_0363`: its admission decision was `reject`. Therefore
the required 400 same-user `allow_extraction` source bindings were not
available and the production importer was not invoked.

No source event, production identity, or admission decision was manually
written. The isolated Main database after failure contained 303 source events,
zero knowledge rows, zero import-registry rows, and zero manifest-registry
rows. The 400 Data idempotency keys were not reassigned or consumed.

## Evidence

- `provision_stderr.log` records the fail-closed result.
- `provision_exit_code.txt` records the runner exit code.
- `state_counts.json` records the post-failure persisted-state counts.

This is a Main-E evidence receipt only. It does not declare
`KB400_PRODUCTION_BOUND = PASS` or `PR70_MERGE_READY = true`.
