# D6B 任务卡：Vector Collection Schema 与组合过滤

| 字段 | 内容 |
|---|---|
| 任务编号 | D6B |
| 责任轨道 | B（检索、索引与评测） |
| 基线 | `origin/main` `a06f8badb7f97b81e5828e7b1e33e15fa16ad2ca` |
| 目标 | 让真实 Vector Engine 的 Collection 持久化检索所需元数据，并提供 fail-closed 的用户与组合过滤。 |
| Reviewer | 一名独立、非作者 Reviewer |

## 修改范围

- `tests/vector-engine/vector_bridge_cli.cpp`：Collection Schema、写入元数据、服务端过滤、异常输入与响应一致性校验。
- `memory-service/retrieval/real_vector_provider.py`：typed filter 转发、请求与结果的 fail-closed 校验、诊断计数。
- `memory-service/tests/retrieval/` 与 `tests/vector-engine/`：L0/L2 覆盖及真实运行驱动。
- `scripts/`：既有 B 轨演示脚本补齐 D6B 需要的元数据和维度配置。
- `evidence/l2-kylin-vm/`：D6B 宿主验证报告、脱敏输出与索引。

## 明确不修改的范围

- 不实现 A、C、D、E 轨代码、业务 Schema 或契约审批。
- 不将 SQLite 的版本真相复制到 Vector filter；Vector 仅返回 `version_id`，回查层负责当前/陈旧版本判定。
- 不实现 Hybrid/RRF、并发基准、重启恢复或代次切换流程。
- 不伪造 Runtime 结果；L2 仅由隔离 Kylin VM 中的真实 Vector Engine 产生。

## 输入与输出契约

- 写入：`id`、`vector`、`user_id`、`version_id`、`scene_id`、`memory_status`、`is_deleted`。
- 查询过滤：调用方必须提供由策略层构造的 typed `RetrievalFilter`（`user_id` 必填）；仅接受 `allowed_scene_ids`、`include_unscoped`、`allowed_memory_statuses` 与 `exclude_deleted` 四个可选键，Provider 不为缺失策略猜测默认范围。
- 场景过滤遵循 PR #63 中 D/E 冻结的方案 B：`allowed_scene_ids` 是允许的 scoped scene 集合，`include_unscoped` 独立决定无场景记录是否可见；空集合不是通配。故 `[] + false` 零命中，`[] + true` 仅允许无场景记录。
- 删除态始终由服务端过滤：调用方传入 `exclude_deleted=false` 也不得返回已删除项。
- 返回：命中必须携带同一 `user_id`、有效 `version_id` 与有限分数；不合格 SDK 命中丢弃并计数，不得污染正常结果。

## 验收与验证

- L0：输入验证、异常命中丢弃、空场景 allowlist 的 `[] + false` / `[] + true` 透传回归、降级与历史 B 轨脚本回归。
- L1：`memory-service/tests/retrieval` 全组通过。
- L2：Kylin V11 真实 Vector Engine 覆盖 metadata 写入、用户隔离、场景/状态/删除过滤、未知键拒绝和 Python provider 端到端；最终绑定 `tested_commit` 的证据见 [D6B L2 报告](../../evidence/l2-kylin-vm/d6b_vector_schema_filter_20260828.md)。

## 安全与失败语义

- 空用户、空/非有限/维度不符向量、非法 `top_n` 与未知过滤键均失败关闭。
- 用户边界与删除门禁在 C++ 服务端执行，Python 侧再校验返回命中，形成双层约束。
- 测试二进制只在隔离 VM 的测试帐户目录构建；不改系统包或服务配置。

## 已知限制与技术债

- `TD-018`：真实 `filter_fingerprint` 尚待 D5 接线提供密钥和 canonical digest。
- `TD-020`：绝对 `deadline_at` 预算递减尚未接入。
- `TD-027`：真实 provider 尚未接入 D 轨管理的 serving `index_generation` 上下文，不能把 `None` 伪装为已验证代次。

## 回滚

回滚本批次提交即可恢复为默认分支已合并的检索实现；VM 测试 Collection 均以 `d6b_` 前缀创建并由 runner 清理，不影响基础虚拟机或正式 Collection。
