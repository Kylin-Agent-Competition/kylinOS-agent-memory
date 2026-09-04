# D11E 麒麟 VM E2E 业务场景实测（2026-09-03，validation profile，合成数据）

## 概览

- VM/提交/环境同 `docs/day11/09_...` 与 `11_...`：`Kylin-V11-2603-D11E-0820036-Test`，被测提交 `f4d9a00`（运行时 = `main@b70827c`），`kylin-memory.service` 以 test/validation profile（drop-in `--register-*`）运行，DB 已迁移到 head。
- 方式：UDS 长度前缀 JSON 信封客户端，直接调用真实网关（`/run/user/1000/kylin-memory/memory.sock`）。
- 数据：仅合成/脱敏样例（`user_d11e_rc01` 等），不引入真实用户内容。

## 场景与结果

| 用例 | 方法/输入（合成） | 结果 |
|---|---|---|
| P 偏好创建（RC-01 正向） | `preference.create`：user_d11e_rc01 / meeting_archive / topic / 「按议题归档」（active） | ok：created=true，action=create，preference_version_id=1，version=1 |
| P 偏好列表（回读） | `preference.list`（同 user） | ok：items=1（memory_item_id=1，current v1 active） |
| F 遗忘预览（RC-05） | `forget.preview`：single_item / preference / target_id=1（幂等键+确认要求） | ok：status=awaiting_confirmation，resolved_target_ids=[1]，affected_count=1，credential TTL=300s，delete_mode=soft |
| F 遗忘执行（RC-05） | `forget.execute`（携带 preview 返回 confirmation_token） | ok：status=completed，executed_count=1，delete_mode=soft，audit_id 返回；执行后该条目 current memory_status=removed（version=2） |
| F 负向：未知目标 | `forget.preview`：target_id=999 | ok：awaiting_confirmation，resolved=[]，affected_count=0（允许零结果） |
| F 负向：错误凭据（待确认态） | `forget.execute`：对 awaiting 计划用错误 token | error `INVALID_REQUEST`：confirmation credential mismatch（fail-closed） |
| F 负向：非待确认态执行 | 对已完成计划再 execute | error：forget plan is not awaiting confirmation |
| 隔离：跨用户 | `preference.list`（user_d11e_rc06_other） | ok：items=[]（零泄漏） |

## 观察 / 待确认项

- 软删除后 `preference.list` 仍返回该条目的 `removed` 当前版本（version=2）。标准检索/MemoryContext 的排除（SEC-FORGET-05）依赖 `memory.retrieve` 主链，当前返回 `retrieval main chain pending`，**尚未在本 VM 验证**；`preference.list` 是否应过滤 removed 属 D7C 编辑器语义口径，建议与 C/D 轨书面确认，不作为本批缺陷结论。
- 遗忘执行为 soft delete（has_vector_cleanup=false）；硬删除与 Vector/FTS5 明文残留验证依赖 B 轨删除链路，仍 `UNVERIFIED`。
- 本批为 validation profile（生产默认不注册 E 业务方法，日志注明 `BLOCKED_BY_HOST_MAPPING`），仅供测试/验证。

## 结论口径

- 已达成（VM 实测）：偏好「创建→列表」与遗忘「预览→确认→执行（软删）」在真实服务+SQLite 上闭环；目标解析/凭据/审计/幂等门禁行为正确；跨用户零泄漏；错误凭据 fail-closed。
- 未达成（保持 `UNVERIFIED`）：`memory.retrieve`/MemoryContext 主链排除、硬删除无明文残留、C 轨 QML 主演示与 A 轨真实 SDK 同 Commit 端到端——对应工作清单项 5 的完整 RC-01..07 尚未跑完。
