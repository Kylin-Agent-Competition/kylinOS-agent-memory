# D3-C 双轴 Review 返工

Type: task
Status: resolved
Blocked by: none

## Outcome

关闭 `origin/main...HEAD` 双轴审查发现的契约来源、兼容性、必填状态和模块边界问题，并保持 D3-C 为候选、宿主阻断状态。

## Required work

1. 为 D2 的 14 个候选公共事件字段逐项记录 `include`、`map`、`defer` 或 `reject` 决议。
2. 明确 C 侧 `TurnFinalizedEvent` 与既有 Python Provider 输入之间的 Adapter 关系，不复制聊天原文，不修改 `memory-service`。
3. 移除没有已合并来源的 `user_confirmed`、`source_trace_id`，或在取得 E/D 决议前保持延期。
4. 通过既有公共 `validate`/`toJson`/`fromJson` seams 让 C++ 调用者能够识别 required bool/enum 是否显式提供。
5. 将官方助手源码补丁从主 Hook 路径撤下；没有合规扩展点时保持生产路径阻断。
6. 消除测试中的重复对象分派，并重新运行 Debug/Release 构建、QtTest、示例 JSON 和文本卫生检查。

## Acceptance

- 每个行为改动严格经历 red → green，测试只经过用户已确认的公共 seams。
- 不修改 B 轨、D/E 业务实现、Python Provider 或生产 Hook。
- Review 后仍未闭合的宿主证据继续标记为 `BLOCKED`/`PENDING_*`。
- 完成后重新提供 Diff、测试、风险和建议提交拆分；默认不暂存、不提交、不推送。

## Comments

- 2026-08-14：Standards 轴发现 2 个硬违规和 1 个判断项；Spec 轴发现 2 个高风险、2 个中风险问题。用户已授权按推荐方案返工。
- 2026-08-14：完成 D2 14 字段决议、`EventMetadata`、required bool/enum 在场性、Provider Adapter 边界和 Hook 路径纠偏；不修改 B 轨、`memory-service` 或生产 Hook。
- 2026-08-14：Debug/Release QtTest 各 77 项通过，CTest 各 1/1 通过，无测试 Release 纯库构建、JSON、凭据模式和 `git diff --check` 通过。
- 2026-08-14：Spec 增量复审无发现；Standards 工作树问题全部关闭。仅剩 4 个既有提交信息待用户单独授权改写历史。

## Answer

返工已完成并通过双轴增量复审。契约仍为候选，宿主映射、生产 Hook、Provider Adapter 和 D/E 决议仍按文档保持阻断/待审。
