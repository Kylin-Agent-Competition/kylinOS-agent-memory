# 13 轨道 C — OS Agent 契约验证报告

> **结论：`PASS_LOCAL / BLOCKED_FOR_HOST_AND_REVIEW`**

- 日期：2026-08-14
- 任务：D3-C
- 分支：`feat/C-d3-host-contract-v1`
- 基线：`origin/main@d37fb95eca9083eb480491cda2464ebe8515477d`
- 验证对象：Qt/C++ 值对象、JSON、枚举、错误、示例和文档
- 不在验证范围：生产 Hook、官方 AI 助手构建/安装、Kaiming/KYSEC、麒麟 L2、D/E 人工审查

## 1. 验证环境

| 项目 | 实际环境 |
|---|---|
| CMake | Visual Studio 2022 随附 CMake 3.31.6 |
| C++ | MSVC 19.44，C++17 |
| Qt | Qt 5.15.2 MSVC 2019 x64，隔离安装于工作区辅助依赖目录 |
| Qt 模块 | QtCore；测试开启时额外 QtTest |
| 构建配置 | Debug、Release、`BUILD_TESTING=OFF` Release |

隔离 Qt 只用于本地 L0/L1 构建验证，不进入仓库交付物，也不替代目标麒麟宿主 Qt/ABI 验证。

## 2. TDD 证据摘要

| 切片 | 红灯 | 绿灯 |
|---|---|---|
| `MemoryQuery` 往返 | 公开 `memoryQueryFromJson/toJson` 不存在，测试编译失败 | 已知良好 Payload 往返通过 |
| 必填字段 | 公开 `validate` 不存在 | C++ 值对象与 JSON 缺字段均返回结构化错误 |
| `MemoryContext` | 对象、解析器和状态枚举不存在 | 往返、预算/计数和未知状态通过 |
| `ToolExecutionEvent` | 五态枚举和对象不存在 | 五态解析、未知状态和脱敏事件往返通过 |
| `TurnFinalizedEvent` | 对象和解析器不存在 | 往返、自重试和 Tool 关联通过 |
| 版本 | `2.0` 四对象和 `v1` 均被错误接受：19 pass / 5 fail | `1.x` 兼容、未知主版本/格式拒绝 |
| 边界加固 | 24 pass / 6 fail | 空字段、负计数、时间线、成功结果、重复 ID 全部通过 |
| 正式示例 | 30 pass / 4 fail，四文件尚不存在 | 四个示例与独立固定字面值一致 |
| required key | 34 pass / 6 fail，Qt 默认值掩盖缺 key | 六类缺 key 统一返回 `required` |
| JSON 类型 | 40 pass / 4 fail | 基础类型统一返回 `invalid_type` |
| 复合类型 | 44 pass / 3 fail | 数组元素与整数精度检查通过 |
| C++ 必填布尔/枚举在场性 | 直接构造对象时缺值未报错 | `injection_status`、`execution_status`、`side_effect`、`is_final` 改用 `optional`，公开 `validate` 可报 `required` |
| D2 共享事件元数据 | 三类事件缺少必填 key，新增 6 组缺字段用例失败 | `EventMetadata` 与共享缺失/类型/转换规则通过 |
| 无来源字段 | 旧示例仍要求 `user_confirmed` / `source_trace_id` | 强类型字段移除，`source_trace_id` 统一映射为公共 `trace_id` |
| 正式示例返工 | 共享元数据加入后 3 个示例与实现不一致 | 三个示例重新通过独立固定字面值比对 |
| 测试对象分派 | 三处重复 `switch` 分派 | 测试侧收敛为一个 `parseContractObject` 辅助 seam，行为不变 |
| 可选元数据规范输出 | 2 pass / 1 fail，缺省 key 被写回空字符串 | 省略规则收敛到 `eventMetadataToJson`，针对用例 3 pass / 0 fail |

红灯输出保存在 `辅助生成文件/临时文件/`，不属于仓库正式交付物。

## 3. 最终命令与结果

### 3.1 带测试配置

```text
cmake -S os-agent-integration -B <build-dir> -DBUILD_TESTING=ON -DQt5_DIR=<Qt5Config-directory>
```

结果：配置与生成通过。

```text
cmake --build <build-dir> --config Debug --target test_memory_event_contract_v1
cmake --build <build-dir> --config Release --target test_memory_event_contract_v1
```

结果：Debug、Release 均通过；MSVC `/W4 /permissive- /utf-8` 下无编译警告。

```text
ctest --test-dir <build-dir> -C Debug --output-on-failure
ctest --test-dir <build-dir> -C Release --output-on-failure
```

结果：返工后两种配置均 `1/1 passed`。直接运行 QtTest 明细为：

```text
Debug: 77 passed, 0 failed, 0 skipped, 0 blacklisted
Release: 77 passed, 0 failed, 0 skipped, 0 blacklisted
```

### 3.2 无测试配置

```text
cmake -S os-agent-integration -B <no-test-build-dir> -DBUILD_TESTING=OFF -DQt5_DIR=<Qt5Config-directory>
cmake --build <no-test-build-dir> --config Release --target os_agent_memory_contract_v1
```

结果：通过；生产消费者不要求 QtTest，只要求 QtCore。

### 3.3 数据与文本检查

- 四个 `contracts/examples/*.json` 均通过独立 JSON 解析；
- 正式示例与测试中的独立固定字面值逐对象一致；
- 所有正式/任务卡文本无行尾空白且以 LF 结束；
- 新增文件的凭据模式扫描无命中；
- `git diff --check` 通过；本轮 Review 返工未暂存、未提交、未推送（分支已有 4 个 D3-C 候选历史提交）。

## 4. 范围检查

本批次只修改/新增：

- `.scratch/d3-c-host-contract/` 本地任务卡；
- `docs/day3/10`–`13` D3-C 文档；
- `os-agent-integration/README.md`；
- `os-agent-integration/CMakeLists.txt`；
- `os-agent-integration/contracts/`；
- `os-agent-integration/tests/test_memory_event_contract_v1.cpp`。

未修改 B 轨检索/索引代码，未修改 D/E 契约或生产实现，未修改官方 AI 助手源码。

## 5. 未完成与阻断

| 项目 | 状态 | 后续责任/条件 |
|---|---|---|
| `MemoryContext` 真实请求前注入 | `BLOCKED / TD-008` | C/D 在目标宿主 instrument 并完成三路隔离对照 |
| 真实结构化 Tool 事件 | `BLOCKED / TD-007/009` | C 取证；无原生事件时提交具体 Adapter 等待 D/E 批准 |
| Turn Stop/Retry/续轮与唯一性 | `BLOCKED / PARTIAL` | C/D/E 完整 L2 Gate |
| 合规生产 Hook 路径 | `NOT_FOUND / BLOCKED` | 只能在受支持扩展点取证后提案；官方源码补丁不在当前范围 |
| 备用路径 | `NO_APPROVED_BACKUP` | D/E 书面批准后才能启用 |
| `TurnExtractionAdapter` | `NOT_IMPLEMENTED / BLOCKED_BY_HOST_MAPPING` | 后续通过受控 resolver 桥接 C++ 元数据事件与 Python Provider；本批次不修改 `memory-service` |
| 人工审查 | `PENDING` | D 主审，用户交互/安全由 E 补审 |
| commit/push/PR | `NOT_AUTHORIZED` | 分别等待用户后续明确授权 |

## 6. 双轴 Review 返工结果

| 轴线 | 初次发现 | 增量复审 |
|---|---|---|
| Spec | D2 公共字段缺失、Provider 映射未定义、无来源字段、C++ required 在场性缺失 | 工作树无新或剩余 finding |
| Standards | 源码补丁边界冲突、测试分派重复、文档状态漂移、可选元数据策略分散 | 工作树 finding 全部关闭 |
| 提交历史 | 4 个既有提交的 subject 不符合中文和允许前缀规则 | 仍待用户单独授权后 reword；不属于当前工作树修复 |

## 7. 交接结论

D3-C 已达到本地人工审查入口：公共契约、示例、路径决策和本地测试完整且一致。它尚未达到最终
冻结或生产合并资格；宿主证据与 D/E 审查缺口必须继续保留，不能以本地 Qt 测试替代。
