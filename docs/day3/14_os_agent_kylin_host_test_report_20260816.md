# 14 轨道 C — Kylin 宿主独立复验报告（B 代替 C 测试）

> 结论：`PASS（L0 契约测试 83/83）`，补齐 Reviewer D/E 要求的 GCC/Kylin 独立复验证据。

- 日期：2026-08-16
- 任务：D3-C
- 分支：`feat/C-d3-host-contract-v1`
- 复验对象：`os-agent-integration`（Qt/C++/JSON v1 候选契约与示例）
- 执行说明：C 轨负责人暂缺，由 B 代替 C 在 Kylin 宿主复验，结果标注“B 代替 C 测试”。

## 1. 复验环境

| 项目 | 值 |
|---|---|
| 系统 | 银河麒麟桌面操作系统 V11（VERSION_ID=v11） |
| 内核 | 6.6.0-63-generic |
| GCC / G++ | 12.3.0（openKylin 12.3.0-1ok3k0.1） |
| CMake | 3.28.3 |
| Qt | 5.15.19（/usr/lib/x86_64-linux-gnu） |
| Git | 2.43.0 |
| 虚拟机 | VirtualBox D3-C（4 vCPU / 4 GiB / EFI / 80 GiB） |

## 2. 结果

| 配置 | 结果 |
|---|---|
| Debug + `BUILD_TESTING=ON` | CTest `1/1 passed`；QtTest `83 passed, 0 failed, 0 skipped, 0 blacklisted` |
| Release + `BUILD_TESTING=ON` | CTest `1/1 passed`；QtTest `83 passed, 0 failed, 0 skipped, 0 blacklisted` |
| Release + `BUILD_TESTING=OFF` | 生产静态库 `libos_agent_memory_contract_v1.a` 构建通过 |
| 正式 JSON 示例 | 4/4 独立 `python3 -m json.tool` 解析通过 |

构建无编译警告（GCC `-Wall -Wextra -Wpedantic`）。

## 3. 结论

Kylin/GCC/Qt 宿主的 L0 契约测试独立复跑结果与 Windows/MSVC 本地结果一致（83/83），
`GCC/Kylin 独立复验` 由 `REQUIRES_INDEPENDENT_RERUN / ENVIRONMENT_BLOCKED` 更新为 `DONE`。

以下 L2 项仍维持 `BLOCKED`，不因本次 L0 复验通过而改变：
- `MemoryContext` 真实请求前注入（TD-008）
- 真实结构化 Tool 事件（TD-007/009）
- Turn Stop/Retry/续轮与唯一性
- 合规生产 Hook 路径
- `TurnExtractionAdapter`（未实现）
