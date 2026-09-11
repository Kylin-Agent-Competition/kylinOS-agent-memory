# PR70 KB400 retry evidence (Main-E)

This directory records the reproducible summary of the successful retry after
the canonical source-admission path falsely classified a bare device term as
high-sensitivity identity data.  The full machine-readable evidence bundle is
kept outside the repository at:

`D:\插件\河工大\Agent\辅助生成文件\临时文件\PR70_MainE_KB400_complete_evidence`

The retry used a newly migrated isolated SQLite Main environment and the
canonical `event.ingest` → M2 binding → M2 import route.  It did not use a mock
or direct `source_events` insertion.  This evidence is not a claim that a
remote host deployment has been validated.

## Source snapshot

- Base commit: `cf3cda380e67bcb823f8687ce26b9fe662bce45c`
- Applied source patch SHA-256: `967cdacb49803eda094cfddcb1e52354b7c27293536a3dab9dd3e7961cbb3c6e`
- K3 input SHA-256: `03256f4db271ad39ce9635c157b85d70641c69fffbd96ffbe5554e10fc7bcbb5`
- Final RC SHA-256: `a823d1d356da2a8a619c724b30a195e70840248fa44196ee2d68fd52b470969b`
- RFC8785 source-manifest SHA-256: `451af04658dd58f3244fabc834676c9746cfc6421789f8196924f244018c4d41`

## Verified outcomes

| Check | Result |
| --- | --- |
| Canonical source events admitted | 400 / 400 `allow_extraction` |
| Same-user bindings | 400 / 400 |
| Binding failures | 0 (cross-user / unadmitted / descriptor mismatch / fabricated event all 0) |
| First import | 400 accepted, 0 rejected |
| Main-generated identities | 400 unique knowledge IDs and 400 unique memory IDs |
| Identical replay | 400 / 400 replayed, no new identity |
| Same-key/different-request probe | 400 / 400 `idempotency_conflict`, zero extra state |
| Authorized readback | 400 / 400 |

Final state after first import, replay, and conflict probe was unchanged at
400 knowledge rows, 400 evidence relations, 400 import-registry rows, 400
manifest-registry rows, and 400 outbox rows.

The full human-readable receipt is located at
`D:\插件\河工大\Agent\可直接查看\PR70_Main-E_KB400_Production_Execution_回执_成功重跑_20260911.md`.
