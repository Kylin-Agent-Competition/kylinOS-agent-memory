# D6B Collection Schema 与组合过滤宿主验证

- 任务：D6B — Collection Schema、用户/场景过滤、异常与空向量验证、删除预留字段
- 结论：`HOST_VERIFIED / E4`（D6B 本轮覆盖范围，包含删除 fail-closed 加固后的最终工作树）
- 日期：2026-08-26
- 基线：`origin/main` `a06f8badb7f97b81e5828e7b1e33e15fa16ad2ca`
- 被测代码状态：基线之上的**未提交工作树**；因此本报告不声明存在 `tested_commit`，也不构成合并资格或 Review 结论。

## 范围与运行环境

在隔离的 VirtualBox 链接克隆 `Kylin-V11-2603-D6B-Test` 执行。基础虚拟机保持未改动。

- OS：Kylin V11，x86_64，kernel `6.6.0-63-generic`
- Vector Engine：`kylin-ai-vector-engine 1.2.0.1-0k0.11`
- Client SDK：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- SDK 开发包受 ostree 系统包写入保护，故在测试帐户目录构建临时 CLI；未修改系统包或服务配置。
- 测试 CLI 采用仓库现有的 `0k0.7` ABI 兼容补丁并经 KySec 对该测试二进制授权后运行。

## 最终 L2 工作树指纹

| 文件 | SHA-256 |
|---|---|
| `tests/vector-engine/vector_bridge_cli.cpp` | `3b5d61fa08e8e3b927851ea6985752ec4e2d38de5190eecfb61d635258c083e8` |
| `memory-service/retrieval/real_vector_provider.py` | `9f85a6b026c0fd59ef32deaecf545631f58d90c401146c0265d033f3efe1a8f0` |
| `tests/vector-engine/run_d6_vector_schema_filter_l2.sh` | `97d8ef07655e8ea8f1aaab21c2ab6f1f63b115367d15852048638ad9c394f8be` |
| `memory-service/tests/retrieval/run_d6_real_vector_provider_l2.py` | `2838d1425d389f53254edfd1bd68267989e683aa290bb33e0c005b446c02c442` |

## 验证结果

1. 公共 `vector_bridge_cli` 协议 runner 创建带 `user_id`、`version_id`、`scene_id`、`memory_status`、`is_deleted` 字段的 Collection，并写入六组不同用户、场景、生命周期和删除状态的数据。
2. 用户 A 的 `lab` 场景（含未设场景）只返回活跃、未删除的 `101:v1` 与 `105:v5`；用户 B 只返回自己的 `103:v3`。这同时覆盖用户隔离、场景组合、默认未删除约束和状态过滤。
3. 生命周期筛选只返回 inactive 的 `106:v6`；空用户过滤按预期被 CLI 拒绝。
4. Python runner 仅经公共 `VectorCliClient` 调用同一 CLI，确认 typed filter 被正确转发、跨用户隔离、inactive 筛选、空向量和 filter-user 不匹配均 fail-closed。
5. 删除门禁采用无条件 `is_deleted == false`。最终重跑显式伪造 `exclude_deleted=false`，仍只返回 `101:v1` 与 `105:v5`，证明删除态不能由调用参数绕过。
6. 最终 VM 重编译使用 `0k0.7` ABI 兼容脚本，二进制经 KySec 授权后执行；二进制 SHA-256 为 `d10f17c9c7371dccc4064ee9729aef6447fd7ab803e898a75dca65345c235f13`。
7. 两个 runner 使用唯一的 `d6b_` Collection 名称；CLI runner 的退出清理已调度，Provider runner 已明确完成删除。

完整的脱敏输出见 [d6b_vector_schema_filter_20260826.log](d6b_vector_schema_filter_20260826.log)，SHA-256：`7c925ef9a0b943c20e39f03831d611e8a7bf54b3d6e1f4f79f9e233b111bd336`。

## 版本语义

本任务不把 `version_id` 加入 `RetrievalFilter`。根据已合并的检索契约，Vector 命中携带 `version_id`，当前/陈旧版本判定由 SQLite 真相源在回查阶段完成。D6B 仅负责 schema 持久化和返回该字段，避免将版本真相复制到 Vector filter。

## 限制与后续门禁

- 这是单一 Kylin 克隆和 SDK `0k0.7` 兼容路径上的 E4 运行证据；不覆盖并发、性能、重启恢复或原生 Hybrid/RRF。
- 报告绑定工作树内容哈希而非提交；代码提交后必须复核差异，如被测文件改变则重新运行。
- 本机完整 `memory-service/tests` 运行得到 `792 passed, 49 skipped, 33 failed, 10 errors`。失败/错误位于 Windows 不具备 `AF_UNIX`、`os.getuid` 和 Linux XDG/UDS 运行条件的跨平台测试，不纳入 D6B 检索验收；D6B Provider 12/12、检索组 200/200 均通过。
- 仍需完成提交前人工审核；技术 PASS 不替代独立 Reviewer 审批。
