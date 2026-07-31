## 背景与目标

冻结轨道 A Provider v1 接口与 Bridge 错误契约。在 Day 1/2 已确认的 Embedding SDK 宿主证据之上，定义 EmbeddingProvider、ExtractionProvider 的输入输出接口、C++ Bridge 错误码体系、超时/取消/模型状态契约，并建立 21 项防御性测试条目。

## 修改范围

- 新增 `cpp-bridge/bridge_error_contract.h`：Bridge 错误契约（15 个错误码 + BridgeResult + AtomicCancelToken + BridgeStatus）
- 新增 `docs/day3/06_provider_contract_v1.md`：Provider v1 接口冻结文档（EmbeddingProvider + ExtractionProvider + 错误码映射表 + 错误处理原则）
- 新增 `docs/day3/07_defensive_test_matrix.md`：防御性测试矩阵（21 条目，14 项 HOST_VERIFIED，1 项 SOURCE_VERIFIED，5 项 UNTESTED）

## 明确不修改范围

- 不包含 Provider 实现代码（仅接口冻结）
- 不包含 Bridge 实现代码（仅契约头文件）
- 不包含 Python-C++ FFI 绑定策略
- 不包含并发/线程安全的实现（仅在测试矩阵中定义条目）

## 关联任务与技术债

- 任务卡：A 轨 Day3 Provider 契约 + Bridge 错误码冻结
- 依赖：Day 1 证据基线（embedding_abi_symbols.log、runtime_identity.log）、Day 2 边界测试结果
- 技术债：无新增

## 架构与能力边界依据

- `docs/baseline/01_sdk_model_abi_baseline.md`（SDK/模型/ABI 基线）
- `docs/baseline/03_defensive_checklist.md`（防御性检查清单）
- `cpp-bridge/embedding_abi_compat.h`（Day 1 ABI 兼容声明）
- `docs/day2/05_day2_smoke_test.md`（Day 2 边界测试结果）

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `cpp-bridge/bridge_error_contract.h` | 新增 142 行：Bridge 错误契约 |
| `docs/day3/06_provider_contract_v1.md` | 新增 252 行：Provider 接口冻结文档 |
| `docs/day3/07_defensive_test_matrix.md` | 新增 309 行：防御性测试矩阵 |

## 数据库与配置变化

无。

## 测试结果

### L0 静态检查

```
g++ -std=c++17 -I. -fsyntax-only cpp-bridge/bridge_error_contract.h
→ HEADER_SYNTAX_EXIT=0                                             # 麒麟 VM 2026-07-30

g++ -std=c++17 -I. cpp-bridge/bridge_error_contract.h cpp-bridge/embedding_abi_compat.h
→ JOINT_SYNTAX_EXIT=0                                               # 联合编译无冲突

g++ -std=c++17 -I. /tmp/test_error_codes.cpp -ldl -o /tmp/test_error_codes && /tmp/test_error_codes
→ 错误码无重叠: PASS
→ ok.is_ok()=1, ok.value=768
→ fail.is_fail()=1, fail.error=257
→ ERROR_CODE_TEST_EXIT=0                                            # 麒麟 VM 2026-07-30
```

### L1 组件集成

```
g++ -std=c++17 /tmp/test_day3_errors.cpp -ldl -o /tmp/test_day3_errors
LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH /tmp/test_day3_errors
→ [DF-L1-001] 不存在的.so路径: PASS
→ [DF-L1-002] 不存在符号名: PASS
→ [对照] 正常调用: dim=768
→ ERROR_TEST_EXIT=0
```

### 安全与假实现审查

- 无 Mock 冒充 Runtime 测试，所有新增宿主证据来自麒麟 VM 真实运行
- 无 API Key 或密钥泄露
- 契约头文件仅定义接口，不含可执行逻辑

### L2 麒麟虚拟机证据

环境：银河麒麟桌面 V11 2603 x86_64, VirtualBox 7.2.14
快照：Kylin-V11-2603-Memory-Runtime-Passed

| 测试ID | 测试内容 | 结果 |
|--------|---------|:----:|
| DF-L1-001 | .so 不存在 → dlopen 错误 | ✅ HOST_VERIFIED |
| DF-L1-002 | dlsym 不存在符号 → NULL | ✅ HOST_VERIFIED |
| DF-L1-003/007a | Runtime kill → SDK 自动重连 6 次后成功 | ✅ HOST_VERIFIED |
| DF-L1-006 | init_model(错误名) → errorCode=10, 自动 fallback | ✅ HOST_VERIFIED |
| DF-L1-015 | 4 线程并发调用 → 全部 dim=768 | ✅ HOST_VERIFIED |
| bridge_error_contract.h | 头文件语法 + 联合编译 + 错误码无重叠 | ✅ HOST_VERIFIED |

### L3 全链路验收

不适用（Memory Service 尚未实现）。

## 性能影响

本 PR 不涉及性能优化。批量超时默认值（30000ms）标注为占位值，待 Provider 封装后实测调整。

## 已知限制

- 超时测试（L1-011）和取消测试（L1-012）需 Provider/Bridge 封装完成后才能执行
- Runtime 永久停用场景（DF-L1-003b）需在隔离环境中测试
- 批量超时（L1-017）需 embed_batch 实现完成后测试
- `ModelInfo.ondevice` 标注为 ASSUMED（未经 SDK API 验证）
- embed_batch 并行策略未定，当前默认顺序调用

## 回滚方式

`git revert` 本 PR 的 3 个 commit 即可。不影响已提交的 Day 1/2 证据文件。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
