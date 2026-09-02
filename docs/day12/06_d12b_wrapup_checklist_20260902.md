# D12B 收尾工作清单（2026-09-02，v3：按 PR #121 Review REWORK 调整）

> 状态：REWORK 返工完成，待复审。
> 基线：`origin/main@29b46ea`；PR：`fix/D12B-retrieval-debt-wrapup`（#121）。
> 范围：仅 B 轨检索/索引收尾；不代行 A/C/D/E 轨实现，不把未接线/未验证路径伪装为完成。

## Review 结论（Reviewer E，2026-09-02）

- TD-030：PASS，保持 Resolved。
- HIGH-01（TD-018）：公开固定 HMAC key 与冻结 Digest 安全契约冲突 → **本批回退 TD-018 代码，保持 Open**。
- MEDIUM-01（TD-019）：production SQLite truth hydration/search orchestration 未接线 → 保留部分实现，**In Progress**。
- MEDIUM-02（TD-020）：生产调用方 deadline 未贯通、subprocess timeout 未映射 → 保留 seam + 补 TimeoutExpired 映射，**In Progress**。

## 逐项处置（v3）

| TD | 严重度 | 处置 | 证据/说明 |
|---|---|---|---|
| TD-030 | Low | **Resolved** | `fusion.py::TruthRecord.__post_init__` 拒绝 `valid_from > valid_to`；`test_truth_record_validity.py` 7 passed |
| TD-018 | Medium | **Open（代码已回退）** | 公开固定 key 方案不符 `docs/day3/08` 冻结契约（HMAC 需部署密钥防低熵枚举）。已移除 `filter_fingerprint_digest`/固定 key 与 fts5/real provider 改动；待部署密钥注入 + fingerprint mismatch fail-closed 后另行关闭 |
| TD-019 | Medium | **In Progress** | 去硬编码 v1 + Vector 版本透传 + SQLite truth current-version 裁决已完成（`test_td019_version_truth.py` 3 passed）；production search orchestration 接线后按原条件关闭 |
| TD-020 | Medium | **In Progress** | VectorCliClient search/insert/delete 绝对 `deadline_at` + 剩余预算递减 + 调用前过期 fail-closed + `subprocess.TimeoutExpired → VectorCliError(TIMEOUT)` 映射（`test_td020_deadline.py` 9 passed）；生产调用方 deadline 贯通与取消语义待接线后关闭 |
| TD-027 | Medium | Open | search provider 消费 `required_generation` 的接线未合入 main |
| TD-032 | Medium | Open | 生产索引写入方接线属 A/D 轨（#109/#110） |
| TD-033 | Medium | Open | 麒麟 VM bridge 重编译 + L2 |
| TD-054 | Low | Open | 跨边界契约冻结需 D/E（Issue #117） |
| TD-055 | Low | Open | D/C 服务/OS 重启端到端（Issue #118） |

## 本批交付物（v1+v2+v3）

1. TD-030：TruthRecord 拒绝倒置有效期（保持）。
2. TD-019：版本真源语义回归测试（保持）。
3. TD-020：VectorCliClient 绝对 deadline seam + TimeoutExpired 映射（保持/增强）。
4. 登记表：TD-030 Resolved；TD-019/020 In Progress（部分完成登记）；TD-018 Open。
5. TD-018 回退：本批不再引入公开固定 key 摘要机制。

## 验证

- `pytest tests/retrieval + evaluation/test_d9_retrieval_gold_spec.py -q`：全绿（见 PR 返工评论数字）
- `py_compile` EXIT=0；`git diff --check` EXIT=0；行尾 LF。