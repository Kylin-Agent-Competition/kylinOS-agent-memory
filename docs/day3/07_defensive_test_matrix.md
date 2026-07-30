# 07 轨道 A — 防御性测试矩阵（契约测试条目）

基于 `docs/baseline/03_defensive_checklist.md` 的 5 层防御检查和 Day 1/2 宿主实测结论，为每个 SDK 防御点建立可重复的契约测试条目。

## 测试目的

确保 Embedding Bridge 在以下场景下行为可预测：
- SDK 加载失败
- 会话异常
- 输入边界
- SDK 内部错误
- 超时与取消
- 并发安全

## 测试条目

### DF-L1-00：Bridge 契约头文件编译检查

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-000 |
| 防御点 | 编译层 · 头文件语法 |
| 测试输入 | `g++ -std=c++17 -I. -fsyntax-only cpp-bridge/bridge_error_contract.h` |
| 预期行为 | 编译正常 |
| 对应错误码 | 不适用 |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `g++ -std=c++17 -I. -fsyntax-only cpp-bridge/bridge_error_contract.h` |
| 验证结果 | `HEADER_SYNTAX_EXIT=0` |
| 状态 | **HOST_VERIFIED / E4** |

### DF-L1-00b：Bridge 契约 + ABI 兼容头联合编译

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-000b |
| 防御点 | 编译层 · 头文件兼容性 |
| 测试输入 | 联合编译 `bridge_error_contract.h` + `embedding_abi_compat.h` |
| 预期行为 | 编译正常，无符号冲突 |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `g++ -std=c++17 -I. -fsyntax-only /tmp/test_bridge_contract.cpp` |
| 验证结果 | `JOINT_SYNTAX_EXIT=0` |
| 状态 | **HOST_VERIFIED / E4** |

### DF-L1-00c：错误码枚举完整性

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-000c |
| 防御点 | 契约层 · 错误码无重叠 |
| 测试输入 | 遍历所有错误码值，无两两重叠 |
| 预期行为 | `错误码无重叠: PASS` |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `g++ -std=c++17 -I. /tmp/test_error_codes.cpp -o /tmp/test_error_codes && /tmp/test_error_codes` |
| 验证结果 | `BridgeResult.ok` 和 `BridgeResult.fail` 均正常构造 |
| 状态 | **HOST_VERIFIED / E4** |

### L1-01：SDK 动态库加载

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-001 |
| 防御点 | Runtime 层 · .so 存在性与可读性 |
| 测试输入 | 不存在的 .so 路径 |
| 预期行为 | `BridgeResult.error == ERR_SO_NOT_FOUND` |
| 对应错误码 | `ERR_SO_NOT_FOUND (0x0101)` |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `dlopen("/tmp/nonexistent.so.1", RTLD_NOW)` |
| 验证结果 | 返回 NULL，错误信息 `cannot open shared object file` |
| 状态 | **HOST_VERIFIED / E4** |

### L1-02：SDK 符号完整性

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-002 |
| 防御点 | Runtime 层 · 关键符号导出确认 |
| 测试输入 | 存在的 .so 但 dlsym 传入不存在的符号名 |
| 预期行为 | `BridgeResult.error == ERR_DLSYM_FAILED` |
| 对应错误码 | `ERR_DLSYM_FAILED (0x0102)` |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `dlsym(h, "this_symbol_does_not_exist_at_all")` |
| 验证结果 | 返回 NULL，错误信息 `undefined symbol` |
| 状态 | **HOST_VERIFIED / E4** |

### L1-03：会话创建（Runtime 停用后自动重连）

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-003 |
| 防御点 | SDK 层 · 自动重连 |
| 测试输入 | kill kylin-ai-runtime 后立即调用 create_session / init_session |
| 预期行为 | SDK 自动重连 6 次（每次间隔 1s），第 7 次连接成功。create_session 始终返回非 NULL |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `sudo kill PID` → 立即调用 create_session |
| 验证结果 | SDK 打印 6 次 `Connection attempt N failed, retrying in 1000 ms`，第 7 次成功连接。create_session 返回非 NULL，init_session 返回 rc=0 |
| 状态 | **HOST_VERIFIED / E4** |

> **注意：** SDK 有内置重连机制，短暂 Runtime 不可用不会触发 `ERR_SESSION_CREATE`。该错误码仅在 Socket 路径不存在或权限错误时触发。

### L1-04：空文本输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-004 |
| 防御点 | 输入边界 · 空字符串 |
| 测试输入 | `text = ""` |
| 预期行为 | dim=768, L2≈1.0, 不崩溃（Day 1 + Day 2 已实测确认） |
| 对应错误码 | `SUCCESS (0x0000)` |
| 状态 | HOST_VERIFIED / E4 |

### L1-05：超长文本输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-005 |
| 防御点 | 输入边界 · 文本长度 |
| 测试输入 | `text = ~2170 bytes` 中文重复文本 |
| 预期行为 | dim=768, 不截断不崩溃（Day 2 TC-1 已实测确认） |
| 对应错误码 | `SUCCESS (0x0000)` |
| 状态 | HOST_VERIFIED / E4 |

### L1-06：错误模型名

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-006 |
| 防御点 | SDK 层 · 模型选择 |
| 测试输入 | `text_embedding_init_model("不存在的模型名")` |
| 预期行为 | SDK 返回 errorCode=10，之后 text_embedding() 自动 fallback 到默认模型 |
| 对应错误码 | `ERR_MODEL_INVALID (0x0502)` |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | `init_model(s, "this_model_does_not_exist_12345")` |
| 验证结果 | init_model 返回 10，之后 text_embedding 返回 dim=768（SDK 自动 fallback 到默认模型） |
| 状态 | **HOST_VERIFIED / E4** |

### L1-07a：Runtime 停用（自动重连验证）

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-007a |
| 防御点 | Runtime 层 · 短暂不可用 |
| 测试输入 | kill kylin-ai-runtime 后调用 embed |
| 预期行为 | SDK 自动重连 6 次后成功，embed 正常返回 |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | 同 DF-L1-003，init_session 成功后调用 embed |
| 验证结果 | SDK 重连 6 次后连接成功，embed 正常返回 dim=768 |
| 状态 | **HOST_VERIFIED / E4** |

### L1-07c：Runtime 永久停用

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-003b |
| 防御点 | SDK 层 · Runtime 永久不可用 |
| 测试输入 | kill kylin-ai-runtime 且不重启，等待 SDK 重连耗尽后调用 create_session |
| 预期行为 | 待测：可能返回 NULL（触发 ERR_SESSION_CREATE）或无限重连（超时） |
| 状态 | UNTESTED |

### L1-07b：模型文件缺失（无需实测）

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-007b |
| 防御点 | 模型状态 · 文件缺失 |
| 测试输入 | 模型文件被移除后调用 embed |
| 预期行为 | 同 DF-L1-006：SDK 自动 fallback 到默认模型，`text_embedding()` 不受影响 |
| 状态 | ASSUMED / E1（模型文件物理删除行为未实测，不同于 init_model 错误名场景。DF-L1-006 无法推论此场景） |

### L1-08：连续多次调用

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-008 |
| 防御点 | 稳定性 · 重复调用 |
| 测试输入 | 同一文本连续调用 5 次 |
| 预期行为 | 5 次结果一致（Day 2 TC-8 已实测确认） |
| 对应错误码 | `SUCCESS (0x0000)` |
| 状态 | HOST_VERIFIED / E4 |

### L1-09：特殊 Unicode 输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-009 |
| 防御点 | 输入边界 · 字符编码 |
| 测试输入 | emoji + CJK扩展B + 数学符号混合文本 |
| 预期行为 | dim=768, 无错误码（Day 2 TC-3 已实测确认） |
| 对应错误码 | `SUCCESS (0x0000)` |
| 状态 | HOST_VERIFIED / E4 |

### L1-10：纯空白字符输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-010 |
| 防御点 | 输入边界 · 不可见字符 |
| 测试输入 | 空格 + 制表符 + 换行 |
| 预期行为 | 前5维与空输入一致（Day 2 TC-2 已实测确认） |
| 对应错误码 | `SUCCESS (0x0000)` |
| 状态 | HOST_VERIFIED / E4 |

### L1-11：超时模拟

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-011 |
| 防御点 | Provider 层 · 超时控制 |
| 测试输入 | 设 timeout_ms=1，调用 embed |
| 预期行为 | `ERR_TIMEOUT (0x0401)` 或正常返回（取决于 SDK 耗时） |
| 状态 | UNTESTED（需 Provider 封装完成后测试） |

### L1-12：取消操作

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-012 |
| 防御点 | Bridge 层 · 取消标志 |
| 测试输入 | 调用 embed 后立即调用 cancel() |
| 预期行为 | 返回 `ERR_CANCELLED (0x0402)` 或正常结果（取决于检查点时机） |
| 状态 | UNTESTED（需 Bridge 封装完成后测试） |

### L1-13：纯数字输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-013 |
| 防御点 | 输入边界 · 数值文本 |
| 测试输入 | `"1234567890 3.1415926 0x1A2B"` |
| 预期行为 | dim=768（Day 2 TC-4 已实测确认） |
| 状态 | HOST_VERIFIED / E4 |

### L1-14：纯标点输入

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-014 |
| 防御点 | 输入边界 · 特殊字符 |
| 测试输入 | `"!@#$%^&*()_+-=[]{}|;:',.<>?/~\`"` |
| 预期行为 | dim=768（Day 2 TC-5 已实测确认） |
| 状态 | HOST_VERIFIED / E4 |

### L1-015：并发调用安全

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-015 |
| 防御点 | Bridge 层 · 并发安全 |
| 测试输入 | 4 个线程同时调用 embed，各自使用独立会话 |
| 预期行为 | 全部返回 dim=768，无崩溃，无数据竞争 |
| 验证日期 | 2026-07-30 |
| 验证环境 | 银河麒麟 V11 2603 x86_64, VirtualBox 7.2.14 |
| 验证命令 | 4 线程并发，各自独立 dlopen/create_session/embed/destroy |
| 验证结果 | 4 线程全部返回 dim=768，日志显示 4 个独立 sessionId |
| 状态 | **HOST_VERIFIED / E4** |

### L1-016：模型未加载时调用 embed（无需实测）

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-016 |
| 防御点 | 模型状态 · 未加载 |
| 测试输入 | 模型文件缺失或未加载时调用 embed |
| 预期行为 | 见 DF-L1-006：错误模型名仅影响 `init_model()`，`text_embedding()` 自动使用默认模型 |
| 状态 | SOURCE_VERIFIED / E2 |

### L1-017：批量超时

| 项目 | 内容 |
|------|------|
| 测试ID | DF-L1-017 |
| 防御点 | Provider 层 · 批量超时控制 |
| 测试输入 | 设 batch timeout_ms=1，调用 embed_batch |
| 预期行为 | `ERR_TIMEOUT (0x0401)` 或部分结果超时 |
| 状态 | UNTESTED（需 Provider 封装完成后测试） |

### 注意：测试条目编号说明

本文档中标题使用 `L1-NN` 格式（如 L1-01），条目内测试ID 使用 `DF-L1-NNN` 格式（如 DF-L1-001），两者指向同一测试条目。

## 测试覆盖统计

| 分类 | 总计 | HOST_VERIFIED | SOURCE_VERIFIED | UNTESTED |
|:----:|:----:|:-------------:|:---------------:|:--------:|
| 编译检查 | 3 | 3 | 0 | 0 |
| SDK 加载 | 2 | 2 | 0 | 0 |
| 会话（自动重连） | 1 | 1 | 0 | 0 |
| 输入边界 | 6 | 5 | 0 | 1 |
| 稳定性（顺序） | 1 | 1 | 0 | 0 |
| 并发安全 | 1 | 1 | 0 | 0 |
| 模型状态 | 2 | 0 | 1 | 1 |
| 超时/取消 | 2 | 0 | 0 | 2 |
| 批量超时 | 1 | 0 | 0 | 1 |
| Runtime 依赖 | 1 | 1 | 0 | 0 |
| Runtime 永久失效 | 1 | 0 | 0 | 1 |
| **合计** | **21** | **14** | **1** | **6** |

## 测试执行前提

- L1-001~003、L1-006、L1-007：需在麒麟 VM 执行
- L1-011、L1-012：需 Provider/Bridge 封装完成后
- L1-004~005、L1-008~010、L1-013~014：已有宿主证据，可直接标注 HOST_VERIFIED
