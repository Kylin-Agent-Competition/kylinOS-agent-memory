# TD-008: chatAsync Input Capture Analysis

| Field | Value |
|-------|-------|
| Evidence ID | EV-002 |
| Task | TD-008 |
| Status | AMBIGUOUS |
| Capture Time | 2026-09-08T16:01:15+08:00 |
| Tested Commit | 5a89601 (kylin-aiassistant V11 3.0.67) |
| PID | 177446 |

## 1. Hook Point A

`SystemChat::sendToolMessage` (systemchat.cpp:692-755) constructs a JSON payload and calls `m_osassistant->chatAsync(jsonDoc.toJson().toStdString())`.

## 2. Captured chatAsync Input (Outbound JSON)

```json
{"arguments":"/home/bacon/d15c_test_img.png","event":"tool_invocation","file_type":"image","started_at":"2026-09-08T16:01:15","tool_id":3}
```

## 3. Field Check

| Injection Field | Present? | Notes |
|----------------|----------|-------|
| memory_context | NO | Not in sendToolMessage payload |
| context | NO | Not in sendToolMessage payload |
| history | NO | Not in sendToolMessage payload |
| session_id | NO | Not in sendToolMessage payload |
| trace_id | NO | Not in sendToolMessage payload |

## 4. ChatSDK Callback

`chatCallback` (systemchat.cpp:79) returned immediately:
```
2026-09-08 16:01:15,031 | chatCallback | model is empty
```

The ChatSDK did not process the request — no chat LLM model is installed. The request never reached the kytensor inference server.

## 5. Conclusion: AMBIGUOUS

- **Source-level**: `sendToolMessage` payload does NOT contain `memory_context` / `context` / `history`.
- **Runtime-level**: ChatSDK returned `"model is empty"` immediately; cannot confirm if ChatSDK injects context internally before forwarding to kytensor.
- **Full confirmation requires**: LLM model installation (kylin-qwen2.5-3b-gguf-model, 2.67GB) to observe complete round-trip.

## 6. Upgrade Conditions

- If ChatSDK does not inject memory_context → upgrade to `NOT_IMPLEMENTED_IN_HOST`
- If ChatSDK injects memory_context → upgrade to `INJECTED` and locate injection code

## 7. Blocker

No chat LLM model installed on VM. Available packages:
- `kylin-qwen2.5-3b-gguf-model` (2.67GB, ~44h download at current speed)
- `ai-kylin-qwen-plus-cloud-model` (4KB, but cloud API not accessible from VM)
