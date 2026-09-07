# PR #143 Schema Guard L2 Evidence

- Tested commit: `0baba38712c78211e76b1de4d641a1405d9c3293`
- Environment: Kylin V11 (`VERSION_ID=v11`), kernel `6.6.0-76-generic`, Python 3.12.3 from existing `/home/kylin-agent/d4d-venv`
- Source binding: Git archive created from the tested commit, SHA-256 `e39bfb4c4c0d6e1b7420c2e704419cd2b9ad706128c00de187e86efdcc9c7c1e`
- Raw log: `pr143_schema_guard_0baba38_20260905.log`, SHA-256 `cdc175228f8b89afe2a83a9cc4b49e8edfbfc37ba354d44ff53001bd1fed522c`

## Commands And Results

1. `PYTHONPATH=. /home/kylin-agent/d4d-venv/bin/python -m pytest tests/test_event_ingest_d6d.py -q`: `35 passed`.
2. Started the isolated service with `app.py --socket /tmp/pr143-dc87657-l2-final/memory.sock --db /tmp/pr143-dc87657-l2-final/event-ingest.sqlite3 --register-event-ingest --no-outbox`.
3. Sent length-prefixed JSON `event.ingest` requests over that real UDS socket. Legacy-only timestamp, legacy `failure`, placeholder actor, placeholder source type, and C-only `queued` status each returned `INVALID_REQUEST` with `source_events=0` and `idempotency_cache=0` before the positive request.
4. A valid `captured_at` plus malformed legacy `collected_at` succeeded, leaving exactly `source_events=1` and `idempotency_cache=1`.

## Scope And Limitations

This is a Kylin VM L2 validation-profile result. `event.ingest` was explicitly registered for the test and ran with `trusted_identity=None`; production still does not register this method. It does not certify a real C-to-D host adapter, a production deployment, or a TD-060 C/D enum mapping freeze.
