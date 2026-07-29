# 05 Embedding SDK 验证发现与待办清单

> 基于麒麟 VM (银河麒麟桌面 V11 2603 x86_64) 实测结果  
> SDK 版本：libkylin-coreai-embedding 1.2.0.0-0k0.4  
> Runtime 版本：kylin-ai-runtime 1.2.0.4-0k0.1（内部报告 1.3.0）  
> 验证日期：2026-07-29

---

## 一、已验证通过项

| 检查项 | 验证方式 | 结果 | 证据 |
|--------|---------|:----:|------|
| Runtime 安装 | `dpkg -l kylin-ai-runtime` | ✅ | ii 1.2.0.4 |
| 依赖库 | `ls /usr/lib/kylin-ai/depends/` | ✅ | libcurl 等 |
| LD_LIBRARY_PATH | `echo $LD_LIBRARY_PATH` | ✅ | 含 kylin-ai/depends |
| SDK .so 存在 | `ls /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1` | ✅ | 文件存在 |
| SDK .so 可读 | `test -r` | ✅ | 权限正常 |
| 17 个符号 nm 确认 | `nm -D` 遍历每个符号 | ✅ | 全部导出为 T 符号 |
| 模型 GTE 主模型 | `ls /usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text` | ✅ | 目录存在 |
| 模型 Ensemble | `ls ensemble-embd_gte-base_uint8-text` | ✅ | 目录存在 |
| 模型 分词器 | `ls tokenizer_gte-base_uint8-text` | ✅ | 目录存在 |
| kytensor-server | `dpkg -l kytensor-server` | ✅ | 2.49.0.6 |
| kytensor-client | `dpkg -l kytensor-client` | ✅ | 2.49.0.6 |
| 端口 8000 | `ss -tlnp` grep 8000 | ✅ | HTTP 监听中 |
| 端口 8001 | `ss -tlnp` grep 8001 | ✅ | gRPC 监听中 |
| ldd 依赖 | `ldd libkysdk-coreai-embedding.so.1` | ✅ | 无缺失 |
| text_embedding 中文 | `"你好世界"` → 768 维向量 | ✅ | 前5值：-0.0034 0.0366 -0.0618 0.0225 -0.0486 |
| text_embedding 英文 | `"Hello world"` → 768 维向量 | ✅ | 前5值：-0.0399 0.0504 -0.0357 0.0012 -0.0234 |
| text_embedding 单字符 | `"A"` → 768 维向量 | ✅ | 正常 |
| text_embedding 空字符串 | `""` → 768 维向量 | ✅ | 正常（不崩溃） |
| 异步回调 | `text_embedding_async` | ✅ | 回调正常触发 |
| init_model（禁调） | 传入错误模型名 `"gte-base"` | ✅ | 不 segfault，返回 errorCode=10 |

---

## 二、发现问题

### 2.1 运行时版本不匹配

| 项目 | 包版本 | 内部版本 | 影响 |
|------|--------|---------|------|
| kylin-ai-runtime | 1.2.0.4-0k0.1 | **1.3.0** | 不一致，Bridge 应以运行时报告为准 |
| libkylin-coreai-embedding | 1.2.0.0-0k0.4 | — | 无内部版本对比 |

**来源**：init 日志 `Runtime version is 1.3.0 InitEngine call new init_v2`  
**风险编号**：R11  
**缓解措施**：Bridge 初始化时记录运行时版本字符串

### 2.2 初始化走 `init_v2` 路径

```
info  Runtime version is  1.3.0 InitEngine call new init_v2
info  Proxy init success, sessionId is: 1695534058
```

内部调用的是 `init_v2` 而不是旧版 `init`。已确认后续 `text_embedding` 调用正常。  
**风险编号**：R12

### 2.3 "文档禁调"函数实际情况不符

| 函数 | 文档标注 | 实测结果 | 新结论 |
|------|---------|---------|--------|
| `text_embedding_init_model` | 禁调 | SDK 日志建议调用： *"Consider calling text_embedding_init_model() to load a specific model"* | **应调用**（传正确模型名） |
| `text_embedding_get_model_list` | 禁调 | 未运行验证 | 状态待确认 |

**影响**：头文件和文档需要更新，取消"禁调"标注。

### 2.4 `text_embedding_get_model_info` 符号存在但头文件未包含

`nm -D` 确认此符号在 `.so` 中导出，但 `embedding_api.h` 未声明此函数。  
调用者只能通过 `dlsym` 手动解析，无法类型安全地调用。

### 2.5 `default_model.yaml` 不存在

`/usr/share/kylin-ai/model-repository/model_bank/` 目录下只有 `config.pbtxt`（protobuf 格式），没有 `default_model.yaml`。  
SDK 仍能正常加载默认模型，不影响功能。

---

## 三、未解决的关键问题

### 3.1 异步回调结果内存所有权未定义

```c
// 同步：调用者通过双指针获得所有权
bool text_embedding(..., EmbeddingResult **result);
void embedding_result_destroy(EmbeddingResult **result);  // 调用者释放

// 异步：回调接收单指针
typedef void (*TextEmbeddingResultCallback)(EmbeddingResult *result, void *userdata);
void text_embedding_async(..., callback, userdata);
```

**问题**：回调中的 `EmbeddingResult*` 由谁释放？  
- 如果是 SDK 释放：用户必须在回调返回前读取/复制数据  
- 如果是用户释放：签名是 `*` 而非 `**`，无法直接调用 `destroy(&result)`  

**建议**：编写一个额外测试，在回调中尝试 `destroy`，观察是否 double-free 崩溃。

### 3.2 异步入队失败无法检测

`text_embedding_async` 返回 `void`，如果 SDK 内部队列满或参数无效，调用者永远不知道。  
回调可能永远不会触发。

**建议**：Bridge 层对异步调用加超时机制，超时后做降级处理。

### 3.3 无线程安全保证

SDK 头文件和文档中均未说明线程安全模型。  
`text_embedding_enable_internal_event_loop` 的存在暗示内部有事件循环线程，但不知道锁模型。

**建议**：Bridge 层假设 `TextEmbeddingSession` **非线程安全**，每个线程使用独立 Session，或加外部锁。

### 3.4 异步进行中销毁 Session 可能 UAF

如果在 `text_embedding_async` 回调触发前调用 `destroy_session`，可能 use-after-free。

**建议**：Bridge 层在回调完成前保持 Session 存活，或在销毁前取消未完成的异步调用。

### 3.5 `embedding_model_list` 无释放函数

```c
EmbeddingModelList *text_embedding_get_model_list(TextEmbeddingSession *session, int *error_code);
// 没有对应的 destroy 函数
// embedding_model_list_get_model 返回的 EmbeddingModelInfo* 也没有释放函数
```

如果调用 `get_model_list`，返回的列表无法释放，导致内存泄漏。

**建议**：当前不用模型枚举功能，如需使用则通过 `dlsym` 查找非标准释放函数。

### 3.6 `create_session` 失败无错误原因

```c
TextEmbeddingSession *text_embedding_create_session();
```

返回 `NULL` 时无法知道失败原因（内存不足？Runtime 未启动？D-Bus 不可达？）。

---

## 四、待办清单

| 优先级 | 待办事项 | 对应问题 | 预计耗时 |
|:------:|---------|---------|:--------:|
| P0 | 在麒麟 VM 上运行 `capture_embedding_evidence.sh`，将证据保存到 `evidence/` | 证据捕获 | 1 分钟 |
| P0 | 测试异步回调中调用 `destroy` 是否导致 double-free | 3.1 | 5 分钟 |
| P1 | 用正确模型名测试 `init_model("ensemble-embd_gte-base_uint8-text")` | 2.3 | 2 分钟 |
| P1 | 测试 `text_embedding_async` 的超时行为 | 3.2 | 5 分钟 |
| P1 | 确认 `text_embedding_get_model_list` 是否真的"禁调" | 2.3 | 5 分钟 |
| P2 | 决定 `text_embedding_get_model_info` 是否应加入头文件 | 2.4 | — |
| P2 | 创建 Bridge 层的简化 C++ 封装（RAII 资源管理） | — | 待定 |
| P2 | 在龙芯环境复测 ABI | R10 | 待定 |

---

## 五、已知风险清单（汇总）

| 编号 | 风险 | 严重程度 | 状态 |
|:----:|------|:--------:|:----:|
| R01 | 空输入导致 SDK 崩溃 | Medium | ✅ 实测不崩，已降级 |
| R02 | NULL 指针传给 SDK | High | 未测试 |
| R03 | init_session 返回非 0 | High | 实测返回 0 |
| R04 | text_embedding 返回 NULL | Medium | 实测返回非 NULL |
| R05 | 向量维度不是 768 | Medium | ✅ 实测维度=768 |
| R06 | 连续 3 次失败需重连 | Medium | 未测试 |
| R07 | ABI 不匹配 | Medium | ✅ 17 个符号全部 nm 确认 |
| R08 | Kytensor 服务未启动 | Medium | ✅ 端口监听中 |
| R09 | 长文本超时 >180ms | Low | 未测试 |
| R10 | 龙芯实机 ABI 不同 | Medium | 未测试 |
| R11 | 包版本 vs 内部版本不一致 | Medium | ✅ 已确认，记录 |
| R12 | init_v2 路径 | Medium | ✅ 已确认 embed 正常 |
| R13 | ldd 依赖 | — | ✅ 全部满足 |

---

## 六、文件清单

| 文件 | 说明 |
|------|------|
| `cpp-bridge/include/embedding_api.h` | 官方 SDK 头文件（来源 gitee commit 63aed6f3） |
| `docs/baseline/01_sdk_model_abi_baseline.md` | SDK / 模型 / ABI 基线清单 |
| `docs/baseline/03_defensive_checklist.md` | 防御性检查清单 + 风险登记册 |
| `docs/baseline/04_minimal_embedding_call.md` | 最小 Embedding 调用脚本 |
| `docs/baseline/05_verification_findings.md` | **本文** — 验证发现与待办清单 |
| `scripts/00_one_click_verify.sh` | 一键检查脚本（17 符号） |
| `scripts/check_kylin_environment.sh` | 环境信息采集脚本 |
| `scripts/capture_embedding_evidence.sh` | 证据采集脚本（VM 运行） |
| `scripts/verify_repository_baseline.sh` | 仓库基线结构验证 |
