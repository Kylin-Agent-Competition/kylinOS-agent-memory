# D11D 麒麟 VM L2 证据：Embedding/SDK 真实调用验证（reboot 后，情况 B）（2026-09-02）

> 对应 Reviewer D 第三轮 MEDIUM：新 HEAD reboot 后 Embedding Runtime UDS 状态与工作项 8 一致性验证。被测 HEAD `c18184a`。

## 执行（最小等价验证：EmbeddingService.start() → health() → embed()）

- HEAD：`c18184a9816d04a20fec95e8c535816dc8acae22`
- SDK：`/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` 存在（`libkylin-coreai-embedding 1.2.0.0-0k0.3`）
- A 轨 C++ bridge：`cpp-bridge/build` 不存在（`kylin_embedding` pybind11 模块未构建）

## 结果

| 检查 | 结果 |
|---|---|
| Runtime UDS `core-textembedding.sock`（调用前） | **存在**（本次启动自动拉起；12:09 复验时缺失为瞬时启动条件） |
| health | `service=ok / provider=ready / bridge_loaded=false / bridge_has_session=false / degraded=true / sdk_missing=true / model={}` |
| embed | `ok=true / degraded=true / dimension=0 / vec_len=0`（**降级空向量，非真实 SDK 调用**） |
| Runtime UDS（调用后） | 存在 |

## 判定（情况 B）

- **真实 Embedding/SDK 调用在 D11D VM 未成功**：A 轨 C++ bridge 未在本 VM 构建（属 A 轨实现/构建交付），EmbeddingService 进入降级（sdk_missing=true）。
- 按 Reviewer 指示不越轨修复 A 轨；**工作项 8 收缩为 `PARTIAL / BLOCKED_BY_A_RUNTIME`**：
  - D11D 已完成：memory-service / vector-engine / systemd / 诊断的统一环境验证（同 Commit 同 VM 启动可追踪）。
  - 待 A 轨闭环：bridge 构建后真实 Embedding/SDK 调用与 Runtime reboot 恢复（A 轨输入为 A 轨 VM 47af2fa 实测）。
- Runtime UDS 按需拉起机制在本次启动成立（调用前后均存在），但真实 embed 依赖 bridge。

## 证据
- 原始日志：`evidence/l2-kylin-vm/d11d_vm_embed_reboot_verify_20260902.log`（SHA-256 `486c372c4140ed6e58273e365617ca0950408665c9b3ecea8654b8904377b0c2`，LF 归一化）。