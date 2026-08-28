# D7B PR 描述：偏好结构化过滤、场景匹配与检索解释

## 摘要

**建议 PR 标题**：`feat: 完成 D7B 偏好检索过滤与解释`

本 PR 在既有融合接缝内完成 D7B：偏好候选必须通过当前版本、UTC 有效期、场景和作用域硬过滤，并返回与 `rrf-v1` 排序同源的确定性解释。当前文件为提交前草稿；测试结果绑定未提交工作区，待取得 commit 授权后补充提交哈希。

## 背景与目标

施工台账要求 D7B 完成偏好结构化过滤、场景匹配、当前版本/作用域/失效时间验证和检索解释。冻结检索契约同时要求全部硬过滤发生在 RRF 聚合前，SQLite 是正文与版本真源。

## 修改范围

1. `TruthRecord` 承载可选 `valid_from` / `valid_to`，拒绝 naive datetime 并统一转为 UTC。
2. 偏好在聚合前执行 current version、半开有效期、scene 与 scope terms 过滤。
3. 多个 current 偏好版本失败关闭，同时用回归测试锁定 Knowledge 既有行为不变。
4. 偏好候选输出 RRF 分项、过滤策略版本、通过项、降级通道和重排版本。
5. 抽取共享 `rrf_terms(...)`，让排序总分与解释使用同一冻结公式。
6. 增加 8 项回归测试，覆盖边界、失败关闭和解释确定性。

## 明确不修改范围

- 不实现或修改 A、C、D、E 轨交付物。
- 不新增 SQLite 版本指针、版本链、Migration、Repository、IPC 或 Outbox。
- 不改变 Knowledge 的 D8 语义，不实现 D9 重排或预算。
- 不创建假宿主结果，不把本地测试标记为 L2/L3。

## 关联任务与技术债

- 任务卡：`docs/day7/06_d7b_task_card.md`
- 权威台账：D7B 三项交付与“仅返回当前有效、场景匹配版本”验收口径
- 跨轨依赖：D 轨 `current_version` / `previous_version_id` 持久化与事务证据尚未落地；不由本 PR 代做

## 架构与能力边界依据

- `docs/day3/08_vector_retrieval_contract_v1.md` §7–§9
- `docs/adr/001-application-layer-rrf.md`
- `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`
- `docs/day7/05_pr58_day7e_description.md`（E 轨业务边界和未实现的 D 轨持久化状态）

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `memory-service/retrieval/fusion.py` | 修改 | 偏好 UTC、版本、有效期、场景、作用域过滤与解释 |
| `memory-service/retrieval/rrf.py` | 修改 | 新增共享 RRF 分项纯函数 |
| `memory-service/tests/retrieval/test_v006_fusion.py` | 修改 | 当前版本、有效期、UTC、scene、scope、解释回归 |
| `memory-service/tests/retrieval/test_w2_degradation.py` | 修改 | 偏好降级通道解释回归 |
| `docs/day7/06_d7b_task_card.md` | 新增 | D7B 范围、契约、验收和依赖 |
| `docs/day7/07_d7b_pr_description.md` | 新增 | 本 PR 描述草稿 |

## 数据库与配置变化

无。没有 Schema、Migration、配置或外部资源变更。

## 测试结果

### L0（单元测试 + 静态检查）

```text
相关 RRF / fusion / degradation：36 passed in 0.91s
git diff --check：PASS
```

### L1（检索组件回归）

```text
memory-service/tests/retrieval：217 passed in 1.12s
基线：209 passed in 1.22s
增量：8 个 D7B 回归用例，无检索回退
```

### 全服务诊断

```text
memory-service/tests：950 passed, 49 skipped, 33 failed, 10 errors in 114.14s
```

失败均未触及本 PR 修改文件：主要为 Windows 缺少 AF_UNIX / `os.getuid`、默认目录写权限、迁移/SQLAlchemy 环境差异；另有既有 `tests/test_extraction_provider_d7.py::test_cache_ttl_zero_expires_immediately` 可独立复现失败。按 B 轨边界，本 PR 记录为跨轨/环境阻塞，不修改相关实现。

### 安全与假实现审查

- 用户、状态、敏感度、对象类型、版本、有效期、场景、作用域和冲突均在聚合前硬过滤。
- scope 缺键、scene 未授权和偏好 current 不唯一时失败关闭。
- explanation 不含正文、可执行过滤表达式或 Provider 异常文本。
- 无密钥、硬编码生产配置或 Mock 冒充 Runtime。
- Standards 与 Spec 双轴本地独立预审均为 `0 findings / PASS`；不替代 GitHub 非作者人工批准。

### L2 麒麟虚拟机证据

不适用于本次不含 SDK、数据库或宿主接线的纯融合实现。完整 current-version 持久化链仍依赖 D 轨实现和真实宿主验证，因此本 PR 不声明 L2/L3 通过。

### L3（全链路验收）

未执行；受 D 轨版本持久化缺口阻塞。

## 性能影响

- current-version 扫描保持 O(n)，偏好重复 current 检测只增加按 memory key 的小型集合。
- 场景查找为 allowlist 成员检查；scope 检查按声明 key/value 线性求交。
- explanation 复用已计算 ranks，不增加 Provider、SQLite 或网络调用。

## 已知限制

1. 调用方必须提供可信的 SQLite `is_current` 真值；默认分支尚未实现 D 轨持久化指针和版本链。
2. 本地 Windows 无法证明 Linux UDS/宿主集成；全服务诊断中的既有失败未在本 PR 越轨修复。
3. D9 重排和 token 预算未实现，`rerank_version` 固定为 `null`。

## 回滚方式

回滚本 PR 的单一提交即可恢复默认分支 D6 融合行为；无数据库、配置或外部数据回滚步骤。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
