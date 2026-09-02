# D12B 收尾工作清单（2026-09-02）

> 状态：本地实现进行中，待提交/审查。
> 基线：`origin/main@29b46ea`（含 D12B PR #119 合并）。
> 范围：仅 B 轨检索/索引收尾；不代行 A/C/D/E 轨实现，不把未接线/未验证路径伪装为完成。

## 背景

台账 D12-B（功能冻结、联调缓冲与缺陷清理）主交付 PR #119 已 APPROVED 并合并（TD-029 关闭）。
本清单对总账中仍由 B 轨负责、且落在 D12-B 任务 1/2（分析失败查询/删除残留/索引恢复；修复性能与过滤错误）领域的 Open 项逐条核对当前代码状态，给出处置。

## 逐项核对与处置

| TD | 严重度 | 标题 | 当前代码证据（2026-09-02, main@29b46ea） | 处置 |
|---|---|---|---|---|
| TD-030 | Low | TruthRecord 未在构造边界拒绝倒置有效期 | `memory-service/retrieval/fusion.py::TruthRecord.__post_init__` 仅校验时区/UTC 归一化，未拒绝 `valid_from > valid_to` | **本批关闭（已实现）**：构造期拒绝倒置；新增 `tests/retrieval/test_truth_record_validity.py` 7 例（倒置/相等/单侧/半开/naive/UTC） |
| TD-018 | Medium | 检索命中 filter_fingerprint 使用固定假值 | `retrieval/fts5.py:137` 与 `retrieval/real_vector_provider.py:336` 仍写死 `hmac-sha256:k1:+a*64`；**无任何非测试消费方**（检索生产编排/接线未合入 main） | **保持 Open**：替换真 digest 属「接线时」动作；检索 search 编排合入后再关，避免产生无消费方的未验证改动 |
| TD-019 | Medium | VectorCliClient.search 硬编码 `version_id="v1"` | main 非测试代码未发现 search 侧硬编码 `"v1"`；`VectorSearchRequest.filter.knowledge.version_ids` 由请求携带；硬编码 `source_generation="v1"` 仅存在于 outbox consumer（A/D 轨 `#109/#110` 文件） | **保持 Open**：需在检索生产接线（含 SQLite 真源 current-version 回源）批次一并验证/关闭，本批无独立可验证面 |
| TD-020 | Medium | Vector 客户端 timeout 硬编码、无 deadline 递减 | D10B `SqliteVectorProvider`（delete/rebuild）已实现 `deadline_at` 校验与 `DEADLINE_EXCEEDED`；`real_vector_provider.VectorCliClient._run` 仍硬编码 `timeout=120`、`search(timeout=5000)` | **保持 Open**：生产 search 编排接线后统一 deadline 递减语义；现仅存在于 L2/测试路径，单独改造无生产验证面 |
| TD-027 | Medium | RealVectorProvider 未注入 serving `index_generation` | D10B `SqliteVectorProvider` 已按 `vector_index_generations`/`required_generation` 管理代次与 serving 路由（delete/rebuild）；检索 search 编排与 D 轨索引状态注入尚未合入 main | **保持 Open**：依赖 D 轨索引状态/路由层与检索接线，B 跟踪 |
| TD-032 | Medium | Knowledge 真值元数据未接通生产索引写入方 | `VectorCliClient.insert` 已支持 knowledge 元数据；生产写入方（outbox index consumer 接线）属 A/D 轨 `#109/#110`，`#110` 已合入但待 VM 验证 | **保持 Open**：跨轨（D/A 接线 + VM），B 跟踪 |
| TD-033 | Medium | Vector bridge D8-B ABI 需与目标宿主重编译并绑定 L2 | 属麒麟 VM 编译/证据任务，非代码 PR 可关 | **保持 Open**：需 VM 会话，B 跟踪 |
| TD-054 | Low | D11B filter_diagnostics 跨边界契约未冻结 | Issue #117；首次跨 IPC/C/D/OS Agent/用户接口接线前关闭 | **保持 Open**（B 主跟踪，D/E 契约冻结） |
| TD-055 | Low | D11B 服务/OS 重启与 D→C 端到端 UNVERIFIED | Issue #118；责任 D/C | **保持 Open**（跨轨，B 只跟踪） |

## 本批交付物

1. TD-030 修复：`retrieval/fusion.py` TruthRecord 构造期拒绝倒置有效期（`valid_from > valid_to` → ValueError），保留 UTC 归一化与单侧开放语义。
2. 回归测试：`tests/retrieval/test_truth_record_validity.py`（7 passed）。
3. 本清单：其余项逐条核对结果与依赖（不关闭、不伪装）。
4. 验证：`tests/retrieval + evaluation/test_d9_retrieval_gold_spec.py` 391 passed（基线 384 + 新增 7）。

## 不纳入本批的原因（边界声明）

- TD-018/019/020/027 的验收语义绑定「检索生产接线/编排」；main 上 gateway `memory.retrieve` 仍未接入检索编排（D11B Review 亦确认），在本批修改会产生无生产消费方、无法运行时验证的改动，违反「不新增未验证路径」。
- TD-032/033/054/055 属跨轨/VM/契约冻结责任，B 不代行。
- 技术债登记表更新（TD-030 → Resolved 等）在 PR 编号确定后随最终提交一并回填。