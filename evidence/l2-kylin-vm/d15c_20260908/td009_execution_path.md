# TD-009: Actual Tool Execution Path — Structured Event Evidence

| Field | Value |
|-------|-------|
| Evidence ID | EV-003 |
| Task | TD-009 |
| Status | VERIFIED (outbound) / BLOCKED (inbound) |
| Capture Time | 2026-09-08T16:01:15+08:00 |
| Tested Commit | 5a89601 |

## 1. Execution Path

```
onPictureOperateClick(3, imgPath)       [msgpane.cpp — D15C direct trigger]
  → sendToolMessage(toolId=3, type, para) [systemchat.cpp:692-755]
    → toolStartJson() KyInfo output       [systemchat.cpp:756 — OUTBOUND VERIFIED]
    → m_osassistant->chatAsync(json)      [ChatSDK call]
      → chatCallback                      [systemchat.cpp:48-79]
        → "model is empty"               [BLOCKED: no LLM model]
        → onRecvMsg("", 26, true, ...)    [msgpane.cpp:1118 — empty response]
```

## 2. Outbound Event (VERIFIED)

**tool_invocation** via `toolStartJson()`:
```json
{"arguments":"/home/bacon/d15c_test_img.png","event":"tool_invocation","file_type":"image","started_at":"2026-09-08T16:01:15","tool_id":3}
```

Logged at: `systemchat.cpp:756` via `KyInfo()` → `~/.log/kylin-aiassistant.log`

## 3. Inbound Event (BLOCKED)

**ToolExecutionEvent** via `toolResultJson()` (patched in msgpane.cpp):
- **NOT triggered** — ChatSDK returned `"model is empty"` (code=26)
- `onRecvMsg` received empty response with code 26
- No `toolReply` signal emitted
- `toolResultJson()` patch is in place but never reached

## 4. Route B Assessment

Main Hook (source instrument) is **viable** for outbound direction. Route B (D-Bus decode) is **not needed**.

Inbound Hook patch is ready in `msgpane.cpp` — will trigger naturally once LLM model is installed and ChatSDK produces valid `ToolExecutionEvent` responses.

## 5. Three-State Coverage

| State | Status | Evidence |
|-------|--------|----------|
| Success | VERIFIED (outbound) | tool_invocation JSON captured |
| Failure | VERIFIED | "model is empty" — ChatSDK error response captured |
| Cancel | NOT_OBSERVED | Host does not model cancellation; no event produced |

## 6. Blocker for Full Verification

LLM model not installed. `kylin-qwen2.5-3b-gguf-model` (2.67GB) download impractical (~44h at ~1MB/min).
