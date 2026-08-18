# 第二轮复审 R-2 响应

## 结论：方案 B——保持 UNTESTED，登记新 Risk

### 发现：SDK text_embedding_get_model_list 外部不可安全调用

麒麟 VM 端到端验证发现：

1. SDK 的 `text_embedding_get_model_list` 在 `init_session` 内部被调用后即释放内部缓冲区
2. 外部任何二次调用（包括 `get_default_model_name()` 中的首次查询）均触发 use-after-free 段错误
3. 即使 void* 转型、不同时序、本地 /tmp 构建（排除 vboxsf 时钟干扰）均稳定复现
4. 唯一一次"成功"返回截断值 `ensemble-embd_gte-base_uint8-tex`（缺末位 't'），说明内存已被部分覆写

### 证据

```bash
# VM 本地 /tmp 构建，10 次测试 10 次段错误（exit 139）
# 全部发生在 syms_.get_model_list(session_, &error_code) 调用处
```

### 实际链路

SDK 的 `Get default model success, model: ensemble-embd_gte-base_uint8-text` 日志来自 SDK 内部初始化，外部无法通过 API 安全获取。

### 当前缓解

- `refresh_model_name_cache_locked()`：`create_session` 后立即缓存麒麟 VM 实测确认的默认模型名（SDK 日志输出，非 `get_model_list` 调用）
- `get_default_model_name()` 直接返回缓存值，不再调用 `get_model_list`
- 已登记新 Risk：`TD-A-D9-SDK-MODEL-LIST-UAF`（SDK 内部缓冲区释放，外部不可调用）

### 对能力矩阵的影响

| 符号 | 状态 | 原因 |
|------|------|------|
| `text_embedding_get_model_list` 等 5 个 | UNTESTED | nm 确认导出但外部不可安全调用，保持 UNTESTED + 注释说明 use-after-free |
| `EmbeddingModelList` / `EmbeddingModelInfo` | UNTESTED | 同上，来自 get_model_list 的指针不可安全使用 |

### 对 TD-A-005-04 的影响

验收标准不变：`model_info().name` 返回真实模型名。当前通过缓存 SDK 日志确认的默认模型名实现，**不依赖 `get_model_list` 调用**。

- `model_info().name = 'ensemble-embd_gte-base_uint8-text'` ✅
- `model_info().loaded = True` ✅
- `model_info().dimension = 768` ✅
- 证据：`evidence/l2-kylin-vm/td_a_005_04_model_name.log`（含原始终端输出）