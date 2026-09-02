# D12B 收尾工作清单（2026-09-02，v2：范围扩大 TD-018/019/020/027）

> 状态：本地实现进行中，待提交/审查。
> 基线：`origin/main@29b46ea`（含 D12B PR #119 合并）。
> 范围：仅 B 轨检索/索引收尾；不代行 A/C/D/E 轨实现，不把未接线/未验证路径伪装为完成。

## 背景

台账 D12-B（功能冻结、联调缓冲与缺陷清理）主交付 PR #119 已 APPROVED 并合并（TD-029 关闭）。
本批次按 D12-B 任务 1/2（分析失败查询/删除残留/索引恢复；修复性能与过滤错误）对总账中 B 轨相关 Open 项逐条处理。

## 逐项处置（2026-09-02，基于 main@29b46ea 代码核对）

| TD | 严重度 | 处置 | 证据 |
|---|---|---|---|
| TD-030 | Low | **关闭（代码）** | `fusion.py::TruthRecord.__post_init__` 拒绝 `valid_from > valid_to`；`tests/retrieval/test_truth_record_validity.py` 7 passed |
| TD-018 | Medium | **关闭（代码）** | `contracts.filter_fingerprint_digest` 以请求过滤器 canonical-json/v1 生成指纹；`fts5.py`/`real_vector_provider.py` 命中不再使用固定假值；`test_td018_filter_fingerprint.py` 8 passed（helper 确定性/区分 + FTS5/Vector 双层） |
| TD-019 | Medium | **关闭（证据 + 回归测试）** | main 检索代码不再硬编码 `version_id="v1"`：VectorCliClient.search 透传引擎 version；fusion 以 SQLite 真源 `is_current` 剔除陈旧版本（既有语义）。`test_td019_version_truth.py` 3 passed 锁定 |
| TD-020 | Medium | **关闭（代码）** | `VectorCliClient` search/insert/delete 接受绝对 `deadline_at`，剩余预算逐层递减（subprocess timeout 与 CLI 搜索 timeout(ms)），过期/naive fail-closed；`test_td020_deadline.py` 8 passed |
| TD-027 | Medium | **保持 Open** | 代次/required_generation 的 search provider 消费点未合入 main：`VectorSearchRequest.required_generation` 仅定义于 contracts，生产 search 编排（D 轨路由注入 serving generation）仍缺；delete/rebuild/get_index_state 已实现代次账本与 serving 路由（D10B）。本批不改未接线面 |
| TD-032 | Medium | 保持 Open | 生产索引写入方接线属 A/D 轨（#109/#110），B 跟踪 |
| TD-033 | Medium | 保持 Open | 麒麟 VM bridge 重编译 + L2，非代码 PR |
| TD-054 | Low | 保持 Open | 跨边界契约冻结需 D/E（Issue #117） |
| TD-055 | Low | 保持 Open | D/C 服务/OS 重启端到端（Issue #118） |

## 本批交付物（v1 + v2）

1. TD-030：`fusion.TruthRecord` 拒绝倒置有效期（commit `b88c5da`）。
2. TD-018：`contracts.filter_fingerprint_digest` + `fts5.py`/`real_vector_provider.py` 真实过滤器指纹。
3. TD-019：版本真源语义回归测试（无硬编码 "v1" + fusion current-version 剔除）。
4. TD-020：`VectorCliClient` 绝对 deadline 语义（search/insert/delete + 剩余预算递减 + 过期 fail-closed）。
5. 本清单（v2）：TD-027 及跨轨项保持 Open 的原因与依赖。

## 验证

- `pytest tests/retrieval + evaluation/test_d9_retrieval_gold_spec.py -q`：**410 passed**（基线 384 + TD-030 7 + TD-018 8 + TD-019 3 + TD-020 8）
- `py_compile`（fusion/contracts/fts5/real_vector_provider）EXIT=0；`git diff --check` EXIT=0；行尾按 `.editorconfig`（LF）规范化。

## 边界声明

- TD-027/032/033/054/055 不因本批代码改动而关闭；登记原因与依赖如上，未投机关闭未接线/跨轨项。
- 技术债登记表更新（TD-018/019/020/030 → Resolved）在 PR 编号确定后随最终提交回填。