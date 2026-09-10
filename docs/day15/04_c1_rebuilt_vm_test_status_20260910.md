# C-1 重建 VM 测试状态（2026-09-10）

## 目的与结论边界

本文记录为推进 C 轨收口而重建的本地 Kylin 测试 VM 及已完成的可重复检查。
这些结果用于确认客户端构建、单元测试和本地 UDS 基线，不等同于 D14C formal
runtime evidence，也不改变 C-1 文档中 `BLOCKED / UNVERIFIED` 的结论。

```text
EVIDENCE_GRADE = LOCAL_OBSERVATION / NOT_FORMAL / NOT_REVIEW_VERIFIED
FORMAL_GATE_CONSUMABLE = NO
HOST_VERIFIED = NO
L3_GATE_CONSUMABLE = NO
```

本记录不得被后续 D14C G4-G8、`HOST_VERIFIED` 或 L3 Gate 直接消费。任何 formal
结论必须在正式 D14C runtime run 中重新采集，并写入唯一 formal evidence root
与对应 evidence index。

## 环境与来源

| 项目 | 记录 |
| --- | --- |
| VM | `Kylin-C1-20260910`，由本地已登记的 `Kylin-V11-2603-BTrack-Base` 的 `D14C` 快照创建 linked clone |
| SSH | NAT 转发到宿主机端口 `2240`；测试完成后已关闭 clone，基础 VM 未修改 |
| 被测源码 | VM 内工作树 HEAD `ba3b50e1bdeea185bca9daee9d1d45958f62a636`，工作树干净 |
| 依赖准备 | 仅在 clone 内通过临时 OSTree unlock / mount namespace 安装 Qt5、CMake 等构建依赖 |

## 已完成检查

### MemoryClient / QML

从零配置并构建：

```text
cmake -S memory-client -B memory-client/build-c1-20260910 \
  -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON \
  -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build memory-client/build-c1-20260910 -j2
QT_QPA_PLATFORM=offscreen ctest --test-dir memory-client/build-c1-20260910 -j2
```

结果：**14/14 PASS**。覆盖 QML 加载、D13C 稳定性、turn extraction 和
production source resolver；resolver 测试报告 29 个断言通过。

### 真实本地 UDS 基线

- `kylin-memory.service` active，socket 为 `/run/user/1000/kylin-memory/memory.sock`。
- `scripts/benchmark_ipc.py --method health --requests 1 --concurrency 1 --warmup 0 --pid <MainPID>`：1/1 成功，PID / socket identity 校验通过。
- `scripts/benchmark_ipc.py --method memory.retrieve --requests 1 --concurrency 1 --warmup 0 --deadline-ms 2000 --pid <MainPID>`：1/1 成功。

第二项仅是 `gateway_empty_context_ipc_baseline`，不是知识检索命中，也不是
Host Chat 注入、Tool 回程或 Chat DB identity 证据。

### Python memory-service 回归

完整命令首次失败前已有 **391 passed**。首个失败为
`tests/test_business_boundaries_d4e.py::test_no_memory_service_evaluation_dir`：
当前 HEAD 追踪了 `memory-service/evaluation/` 文件，而测试仍要求该目录不存在，
属于仓库基线矛盾，不是本 C-1 文档变更引入。随后以排除该文件的方式运行长回归，
因无完成摘要而主动停止；该结果不得记为全量通过。

## 未完成与阻塞

- 本地 clone 中不存在可运行的 `/usr/bin/kylin-aiassistant`，也没有可用的 Kaiming
  Assistant 应用实例。
- 因此尚未取得真实 AI Assistant Chat / Tool round-trip、MemoryContext 注入、Tool
  返回和 Chat DB identity 时序证据。
- D14C formal runtime、`HOST_VERIFIED`、L3 PASS、`D14C_COMPLETE` 与
  `C_TRACK_COMPLETE` 仍保持 `BLOCKED / UNVERIFIED`，不能据此完成 C 轨最终锁定。

## 与既有结论的关系

本记录补充了可复现的 VM、构建、客户端测试和 UDS 基线事实；没有提升任何正式
准入状态，也没有替代真实 Host 证据或 D 轨 trusted identity 批准。
