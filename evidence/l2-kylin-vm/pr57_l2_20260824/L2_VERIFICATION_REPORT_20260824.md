# PR#57 麒麟宿主 L2 验证报告（2026-08-24）

- **依据清单**：`deliverables/PR57_L2_VERIFICATION_CHECKLIST_20260824.md`
- **验证环境**：银河麒麟 V11 x86_64（`6.6.0-76-generic`）VirtualBox 虚拟机，SSH `127.0.0.1:2222`，用户 `kylin-agent`
- **分支 / 基线 Commit**：`feat/d4-phase0-ipc-alignment` / `ec3a91e5858f1e7fe210a9850e5c9d54fdc9b109`（主证据；L2-A3 补充重采证 HEAD=`0e07950`，见 `L2-A3_rerun_20260824.md`）
- **被测代码**：以 HEAD 为真源的 `memory-service/`（含修复 Commit `740bb62` 全部改动），上传至 VM 干净工作区 `/home/kylin-agent/l2-verify-pr57/`
- **真实 SDK**：`libkylin-coreai-embedding 1.2.0.0-0k0.4`（`/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0`）；kylin-ai-runtime pid=9434 正常运行
- **执行驱动**：`evidence/l2-kylin-vm/run_l2_verify.py`（可复现）
- **原始证据**：`evidence/l2-kylin-vm/pr57_l2_20260824/pr57_l2_evidence.jsonl` + `PR57_L2_RESULTS_20260824.md`

---

## 一、结果汇总表（逐项回填清单「结果」列）

| 编号 | 验证项 | 结果 | 证据 | 说明 |
|------|--------|:---:|------|------|
| L2-A1 | ALIGN-005 active socket 拒绝 unlink | **PASS** | `PR57_L2_RESULTS_20260824.md` §L2-A1 | 抛 `RuntimeError: active socket already listening: ...memory.sock; refusing to unlink`，原 socket/进程未被抢占 |
| L2-A2 | stale socket 清理后正常 bind | **PASS** | §L2-A2 | stale 残留被清理，bind+listen 成功，`memory.embed` 返回 `status:"ok"` + `dimension:768` + `l2_norm≈1.0` |
| L2-A3 | socket 父目录 per-user 隔离（0700） | **PASS** | §L2-A3 + L2-A3_rerun | 现存 `0755` 以新 HEAD `0e07950` 启动后幂等收敛为 `0700`；`/var/tmp`（1777）与家目录（0700）未被改动；新建目录亦 0700 |
| L2-B1 | 真实 SDK 下新 envelope 断言（pytest） | **PASS** | §L2-B1 | `KYLIN_L2=1` pytest `test_embedding_service_real.py` **10 passed in 0.92s** |
| L2-B2 | 错误码语义分类端到端 | **PASS** | §L2-B2 | unknown→`UNSUPPORTED_METHOD`；缺字段→`INVALID_REQUEST`；超长帧→`PROTOCOL_ERROR`；版本不匹配→`PROTOCOL_ERROR` |
| L2-B3 | 真实客户端字段兼容性 | **PASS** | §L2-B3 | 真实 C++ `echo_client`（含 request_id/trace_id/deadline_ms/payload）对 embedding server 发 `memory.ping` → `status:"ok"`，未被 INVALID_REQUEST 误拒 |
| L2-C1 | Embedding 异常输入降级 `degraded_reason` 保留 | **PASS** | §L2-C1 | 移走 `.so` 后 `memory.embed` → `status:"ok"` + `vector:[]` + `dimension:0` + `degraded:true` + `degraded_reason.code="ERR_SDK_NOT_LOADED"` 完整保留；`.so` 已还原 |
| L2-C2 | 空输入 / 非法输入 | **PASS** | §L2-C2 | 空串→`status:"ok"`（768 维，B1 中 `test_real_embed_empty_string` 亦证）；非 str→`INVALID_REQUEST`（不崩溃） |
| L2-D1 | 证据收集器脱敏 + HEAD 绑定 | **PASS** | §L2-D1 + `evidence/phase0/phase0_vm_evidence.md` | `[servicekey] key=REDACTED`（无明文数字）；头部含 project/task/branch/commit_sha/result/limitations；`commit_sha` 正确绑定 `ec3a91e` |

> **P0 认证纪律核验**：`IPC-001`（UDS，L2-B2/B3）、`EMB-T03`（Embedding 异常输入，L2-C1/C2）均在麒麟宿主 L2 通过，满足「冻结接口前须 P0 认证通过」[01 §12.1]。

---

## 二、各验证项关键证据摘录

### L2-A1：active socket 拒绝 unlink（PASS）
```text
# exit=1
Traceback (most recent call last):
  File ".../embedding/server.py", line 86, in _remove_stale_socket
    raise RuntimeError(
RuntimeError: active socket already listening: /run/user/1000/kylin-memory/memory.sock; refusing to unlink (avoid stealing socket ownership)
# 验证后：受控 listener（pid=328939）与原 memory.sock 监听者仍存活，socket 未被抢占
```

### L2-A2：stale socket 清理后正常 bind（PASS）
```json
{"protocol_version": "1.0", "request_id": "req-l2", "trace_id": "trc-l2",
 "status": "ok",
 "data": {"vector": [...768 项...], "dimension": 768, "l2_norm": 1.0000001615645466}}
```

### L2-A3：现存目录 0755 → 收敛为 0700（PASS）+ 新建目录 0700（PASS）
```text
# 现存（遗留进程创建，0755）：以新 HEAD 0e07950 启动 embedding server 前
drwxr-xr-x 2 kylin-agent kylin-agent  /run/user/1000/kylin-memory
# 启动后 _ensure_socket_dir 幂等收敛：
drwx------ 2 kylin-agent kylin-agent  /run/user/1000/kylin-memory      # 0700 ✓
# 未被改动：/var/tmp（drwxrwxrwt, 1777）与家目录 /home/kylin-agent（drwx------, 0700）前后一致
# 新建目录：drwx------ /tmp/l2-a3-fresh/sub                             # 0700 ✓
# 完整原始证据：evidence/l2-kylin-vm/pr57_l2_20260824/L2-A3_rerun_20260824.md
```

### L2-B1：真实 SDK pytest（PASS）
```text
tests/test_embedding_service_real.py::test_real_embed_returns_768_dim PASSED
tests/test_embedding_service_real.py::test_real_embed_chinese PASSED
tests/test_embedding_service_real.py::test_real_embed_empty_string PASSED
tests/test_embedding_service_real.py::test_real_embed_batch PASSED
tests/test_embedding_service_real.py::test_real_service_handle_request_ping PASSED
tests/test_embedding_service_real.py::test_real_service_handle_request_embed PASSED
tests/test_embedding_service_real.py::test_real_service_health PASSED
tests/test_embedding_service_real.py::test_degraded_when_so_missing PASSED
tests/test_embedding_service_real.py::test_td_005_09_sdk_missing_degrades PASSED
tests/test_embedding_service_real.py::test_td_005_09_sdk_missing_no_crash_on_server PASSED
============================== 10 passed in 0.92s ==============================
```

### L2-B2：错误码语义分类（PASS）
| 输入 | 实际 `error_code` | 期望 |
|---|---|---|
| `memory.unknown` | `UNSUPPORTED_METHOD` | UNSUPPORTED_METHOD |
| 缺 request_id/trace_id/deadline_ms | `INVALID_REQUEST` | INVALID_REQUEST |
| 帧声明长度 70000（>65536） | `PROTOCOL_ERROR` | PROTOCOL_ERROR |
| protocol_version `"9.9"` | `PROTOCOL_ERROR` | PROTOCOL_ERROR |

### L2-C1：降级 `degraded_reason` 保留（PASS）
```json
{"status": "ok",
 "data": {"vector": [], "dimension": 0, "l2_norm": 0.0, "degraded": true,
          "degraded_reason": {"code": "ERR_SDK_NOT_LOADED",
                              "message": "[ERR_SDK_NOT_LOADED] Embedding SDK 缺失（kylin_embedding 模块不可用）"}}}
```
（测试后已 `sudo mv` 还原 `.so`，`ls` 复核 `366624` 字节原样。）

### L2-D1：证据脱敏 + HEAD 绑定（PASS）
```text
- **branch**: feat/d4-phase0-ipc-alignment
- **commit_sha**: ec3a91e5858f1e7fe210a9850e5c9d54fdc9b109
[servicekey]
key=REDACTED        # 无明文数字
```

---

## 三、发现与建议（诚实声明）

1. **L2-A3（已解决，原 DEBT）**：`_ensure_socket_dir` 原只对**新建**目录生效；已由 Commit `0e07950`（受保护幂等 chmod 现存目录 0700，跳过 `_EXCLUDED_CHMOD_DIRS` 系统/共享目录与家目录）修复，并经麒麟宿主重采证 PASS：现存 `/run/user/1000/kylin-memory`（0755）以新 HEAD 启动后收敛为 `0700`，`/var/tmp`（1777）与家目录（0700）未被改动（证据 `L2-A3_rerun_20260824.md`）。
2. **测试过程观察**：本次验证前 VM 上遗留的旧 memory-service（pid=3107，`feat/d4d-ipc-db-outbox` 分支的 `app.py`）监听 `/run/user/1000/kylin-memory/memory.sock`，其 socket 路径曾在并发运行中被 unlink（孤儿 inode）。这印证了 ALIGN-005 所针对的「多进程抢占 socket 路径」风险真实存在；修复后（L2-A1）`embedding.server` 对 active socket 正确拒绝 unlink，不再抢占。
3. **限制**：L2 为宿主级功能验证；性能/并发/超时（FRZ-IPC-004 TD-IPC-003）、幂等落库（FRZ-IPC-005，待 D4-D）、真实 Kaiming Hook 端到端不在本清单范围，仍属后续 L3/实现阶段。

---

## 四、完成后的产出状态（对照清单「三」）

- [x] 逐项回填结果表（见上）并附证据路径
- [x] 更新 `evidence/index.yaml`（新增 `PR57-L2-001` / `PR57-L2-IPC001-001` / `PR57-L2-EMBT03-001`，IPC-001 与 EMB-T03 回写为 `HOST_VERIFIED` / E4，`tested_commit=ec3a91e`；同步回写 `PHASE0-ALIGN005-001` 的 HEAD/checksum）—— Reviewer 核签待审
- [ ] 回写能力矩阵 `IPC-001`/`EMB-T03` → HOST_VERIFIED —— 待人工核签（能力矩阵 01 文档另行回写）
- [ ] ADR-008 提交 Reviewer E 签署 —— 待人工核签
- [ ] 提交完整测试与证据后请求 Reviewer 发起 PR#57 下一轮复审 —— 待人工发起

> 本报告所有原始命令、exit code、stderr、响应 JSON 均已回收于 `pr57_l2_evidence.jsonl`，绑定当前 HEAD `ec3a91e`。
