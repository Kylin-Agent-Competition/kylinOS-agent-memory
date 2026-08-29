# D7B PR 描述：偏好结构化过滤、场景匹配与检索解释

## 摘要

**建议 PR 标题**：`feat: 完成 D7B 偏好检索过滤与解释`

本 PR 在既有融合接缝内完成 D7B：偏好候选必须通过当前版本、UTC 有效期、场景和显式作用域硬过滤，并返回与 `rrf-v1` 排序同源的确定性解释。首轮 HEAD 为 `cc62f8b`；PR #66 返工已同步 `main@4926345`，最终返工 SHA 与对应测试结果在提交、推送后同步到 GitHub PR 正文和 Review 回复。

## 背景与目标

施工台账要求 D7B 完成偏好结构化过滤、场景匹配、当前版本/作用域/失效时间验证和检索解释。冻结检索契约同时要求全部硬过滤发生在 RRF 聚合前，SQLite 是正文与版本真源。

## 修改范围

1. `TruthRecord` 承载可选 `valid_from` / `valid_to`，拒绝 naive datetime 并统一转为 UTC。
2. 偏好在聚合前执行 current version、半开有效期、scene 与显式 scope identity/terms 过滤。
3. 多个 current 偏好版本失败关闭，同时用回归测试锁定 Knowledge 既有行为不变。
4. 直接复用 E 轨 `PreferenceScope` 五值，并以 `preference-scope-terms/v1` 映射必要检索 term；只有显式 global 可无 term。
5. query/truth unknown scope key、必要 term 缺失和不匹配均失败关闭；多 key 为 AND、同 key 多值为 OR。
6. 偏好候选输出 RRF 分项、过滤/作用域 Schema 版本、scope identity、通过项、降级通道和重排版本。
7. 抽取共享 `rrf_terms(...)`，让排序总分与解释使用同一冻结公式。
8. 增加 24 项 D7B 回归测试，覆盖边界、Provider 调用前验证、失败关闭和解释确定性。

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
| `memory-service/retrieval/preference_scope.py` | 新增 | E 轨五值到检索 term 的版本化映射与纯匹配 |
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
相关 RRF / fusion / degradation：52 passed in 0.68s
git diff --check：PASS
```

### L1（检索组件回归）

```text
memory-service/tests/retrieval：233 passed in 1.30s
基线：209 passed in 1.22s
增量：24 个 D7B 回归用例，无检索回退
```

### 全服务诊断

```text
memory-service/tests：990 passed, 49 skipped, 36 failed, 36 errors in 214.80s
```

失败均未触及本 PR 修改文件：主要为 Windows 缺少 AF_UNIX / `os.getuid`、默认目录写权限、迁移/SQLAlchemy 环境差异；另有既有 `tests/test_extraction_provider_d7.py::test_cache_ttl_zero_expires_immediately` 可独立复现失败。按 B 轨边界，本 PR 记录为跨轨/环境阻塞，不修改相关实现。

### 安全与假实现审查

- 用户、状态、敏感度、对象类型、版本、有效期、场景、作用域和冲突均在聚合前硬过滤。
- scope identity/必要 term 缺失、unknown key、scene 未授权和偏好 current 不唯一时失败关闭。
- Preference query 在执行 FTS5/Vector Provider 回调前验证，非法 query 不触达 Provider。
- explicit global 与 scoped preference 不再根据空 `scope_terms` 猜测，解释携带已验证的五值 identity 和 Schema 版本。
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

合并后回滚 GitHub 生成的 PR 合并提交即可移除 D7B 行为；本 PR 无数据库、配置或外部数据回滚步骤。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
