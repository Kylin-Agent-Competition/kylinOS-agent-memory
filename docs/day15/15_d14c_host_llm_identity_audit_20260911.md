# D14C Host Chat LLM Identity Audit

Date: 2026-09-11
Status: `P0_3_INPUT_PARTIAL / D14C_REMAINS_BLOCKED`
Scope: Real Host Chat LLM availability and deployed-artifact identity only.

## Current Evidence

PR #183 was merged into main at `b1de5389b5f1162615529aac0030b69ee2cdfa0c`.
The RC3 evidence under
`evidence/l2-kylin-vm/host-memory-e2e-20260911/rework-rc3` records:

- `SOURCE_COMMIT=c5eca9e81248243529178d2e22b7722ca45d89c6`
- `SOURCE_PACKAGE_SHA256=63941062159437202ce293a72c335d04cce55c6b46ad771611b509a7559db069`
- Assistant PID `62697`
- three `chatAsync injected=1` events in `prechat-full.log`
- Memory Service, Host Bridge, and Context Sync services active
- `INTERNAL_CONTEXT_DB_ROWS=0` in the Chat DB check
- active context limited to an already-saved preference and current-request priority

The RC2 evidence additionally records the deployed assistant binary:

```text
/usr/bin/kylin-aiassistant
86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6
```

## P0-3 Field Audit

| Required field | Current status | Evidence gap |
|---|---|---|
| Package identity | Partial | RC3 records source/package SHA but not an explicit Host Chat LLM package name/version |
| Binary identity | Partial for RC3 | RC3 says assistant binary identity preflight PASS but does not record the deployed SHA; RC2 has a SHA for an earlier PID |
| Model/runtime version | Missing | No RC3 file records the chat model or runtime version |
| Usability evidence | PASS | RC3 has a real Host Chat round with `chatAsync injected=1` and a valid model response |

## Conclusion

P0-3 has usable Host Chat evidence but is not yet a complete formal Host Chat
LLM identity input. D14C must remain blocked until an authority accepts the
existing identity as sufficient or supplies the missing package, binary, model,
and runtime identity for the exact RC3 round.

This audit does not change the D14C formal result, does not create a D14C
evidence root, and does not claim `release_ready=true` or
`production_ready=true`.
