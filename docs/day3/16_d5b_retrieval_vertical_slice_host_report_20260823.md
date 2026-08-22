# 16 轨道 B — D5B 检索垂直链路宿主验证报告（V002–V007）

> 结论：`B-D3-V002`–`V006` 及 D5B 边界验证（空库/服务故障/Top-K）取得麒麟 VM 宿主证据；
> `V007` 评测脚本/配置版本绑定为 `PASS_VM`，其正式量化评测仍 `DEFERRED_VM`（依赖 E 轨 Gold Label/封存集）。
> `TD-004` 已 `Resolved`：V005 已实证 SDK 无原子切换 API，routing-switch 等价方案经 D 轨（周子腾，2026-08-23）冻结为关闭路径。

- 日期：2026-08-23
- 系统：Kylin V11 x86_64，内核 `6.6.0-63-generic`
- 项目基线：`origin/main@8bf4c9b`，本分支 head `a5d8510`
- SDK 源码：`2213447ef765e709e93f94d4177f4417478fe8ea`
- 运行库包：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 运行库：`libkysdk-vector-engine-client.so.1`

## 1. V002–V007 逐项结论

| ID | 目标 Runtime 事实 | 结论 | 归档日志 |
|---|---|---|---|
| V002 | Provider v1 真实 upsert/search/delete 错误映射 | `PASS_VM`：校验类错误统一 `SERVER_FAILED(1002)`，原因在 `Message()`，未使用头文件细分码 | `v002_error_mapping_20260823.log` |
| V003 | deadline/取消在不可中断 SDK 下的真实行为 | `PASS_VM`：无 cancel/abort API；Search/Query 有 timeout（粗粒度），Insert/Upsert/Delete 无；服务停止 code=3 | `v003_deadline_cancel_20260823.log` |
| V004 | 索引新代次构建、失败保旧与恢复 | `PASS_VM`：多集合代次模式；新代次构建不干扰 serving，失败不替换旧代次，drop-old 切换 | `v004_generation_rebuild_20260823.log` |
| V005 | 原子 generation/Collection 切换能力 | `PASS_VM`（能力否定）：SDK 无 rename/swap/replace 原子 API，等价方案 routing-switch；TD-004 已 D 轨冻结 Resolved | `v005_atomic_switch_20260823.log` |
| V006 | FTS5 + Vector + rrf-v1 端到端 | `PASS_VM`：FTS5 BM25 + 真实 Vector + 应用层 RRF 在 VM 跑通 | `v006_e2e_fts5_vector_rrf_20260823.log` |
| V007 | Recall@K/MRR/nDCG/P95 | `PASS_VM`（脚本/配置就绪）：评测脚本输出三通道指标；正式量化评测仍 `DEFERRED_VM` | `v007_eval_20260823.log` |

## 2. D5B 边界验证（空库 / 服务故障 / Top-K）

| 项 | 结论 | 归档日志 |
|---|---|---|
| W1 空库 | `PASS`：空 FTS5 + 空 Vector + 融合返回可解释空结果，退出码 0 | `d5b_w1_empty_20260823.log` |
| W2 服务故障 | `PASS`：停服务 code=3 → `provider_unavailable`，FTS5 命中保留，恢复自愈 | `d5b_w2_service_fault_20260823.log` |
| W3 Top-K 边界 | `PASS`：top_n=1/超命中数/超大/空库均正确 | `d5b_w3_topk_20260823.log` |

## 3. 证据归档 SHA-256

| 文件 | SHA-256 |
|---|---|
| `v002_error_mapping_20260823.log` | `96ada15ace392229b211b44d6ba34d761d834f2af84414f2418ec520e6e62525` |
| `v003_deadline_cancel_20260823.log` | `cf1175a166621e9ef8ba6655d6e1cd8b650d98ef0ba9bc4d03d3b28b62abfc3c` |
| `v004_generation_rebuild_20260823.log` | `99707a68cda4ca9988b6b5b14b355a0806fe1ae99f724e8f18e90ac834dec0f5` |
| `v005_atomic_switch_20260823.log` | `a12243c17de66eafd6bd0710a1ed7b8fae21eabd3b1b665d38f9421973aeb78d` |
| `v006_e2e_fts5_vector_rrf_20260823.log` | `95590dc4145ce7f8e1edce2e9da7feea81a164ee01727f85b2348ae761e0aa06` |
| `d5b_w1_empty_20260823.log` | `19fd31f7d19414ee7cf2771f861a6a6b51ded123a48d5d1df900242d58ba1110` |
| `d5b_w2_service_fault_20260823.log` | `b7848f7d9efbb627dec1f74480f452cdb3f0b0c0fc75d44a53c63c72d0266c5b` |
| `d5b_w3_topk_20260823.log` | `cb5b5e18bfde354d3451e42633ba1a2bb81a45f9f7bba8c7f920437bbf5dbbcd` |
| `v007_eval_20260823.log` | `11ba6aa29768052d994c0d11e358db858e42cb9a4ac95d8cded89c1419d88591` |

## 4. 候选文件 SHA-256（完整见 index.yaml）

| 文件 | SHA-256 |
|---|---|
| `tests/vector-engine/d2_vector_error_mapping.cpp` | `7bb77f6f776ad562b7a148099952ee9fb9f333bee2eca566b615ed805cba12bb` |
| `tests/vector-engine/d3_vector_deadline_cancel.cpp` | `764834b8c7abbb6c16f48af79c10c58812aa2634ae1928f051a491a9a47cc5dd` |
| `tests/vector-engine/d4_vector_generation_rebuild.cpp` | `f77d9cf31b1191d3b74e6aa63de9e2a5da4d944359a48dd1fd514c0decf2158d` |
| `tests/vector-engine/d5_vector_atomic_switch.cpp` | `dd1371460d4c9776d74017a16d365970fed81b0d1ec1a501a75ed6ec065e8044` |
| `tests/vector-engine/vector_bridge_cli.cpp` | `079bf7cbe90b31da930215ca4558d07f04214077664d1052bbd3c6795b9b368d` |
| `memory-service/retrieval/fts5.py` | `600267325b678c334953b568ee84437b323818890718320ea72b2d81d5682e70` |
| `memory-service/retrieval/fusion.py` | `a8b3837109b54e5b4177214f8806601b261f3b31465b304c5f0371b981c185a9` |
| `memory-service/retrieval/real_vector_provider.py` | `bfc5a9113b675f89c789b00c3962e549250734b4d9e9d109a9ab4a5b0275b381` |
| `memory-service/retrieval/vector_sdk_errors.py` | `18103e61f5ec0ce823d6d5dff5017c788191173613629834caf8bea6ad48ce1c` |
| `memory-service/retrieval/evaluation.py` | `9943ad6376e30cd0146ed93ebc3a6783c1d7adcf8ff5bea1e079ee54cc51a907` |
| `scripts/v006_e2e_demo.py` | `3e21678632bf45835813114ea351ef427be041cbf1a6f93e29651debe7d89e83` |
| `scripts/v007_eval.py` | `dc59486cdc4bd1fb808e21f98c963d407c6223c5dfd1c6d91ed201ef67ff1342` |

## 5. 状态边界（如实，不虚标）

- `V007` 正式量化评测（Recall@K 达标等）依赖 E 轨 Gold Label/封存集，`datasets/` 当前尚未封存；本报告只证明评测脚本与配置版本绑定就绪。
- `TD-004` 已 `Resolved`：V005 已实证「无原子切换 API」，「routing-switch 等价方案」经 D 轨（周子腾，2026-08-23）冻结为关闭路径；`supports_atomic_generation_switch` 保持 `false/UNTESTED`，激活仅走 `routing_switch`/`maintenance_window`，禁止 `atomic_switch`。
- 本报告不替代一名独立、非作者 Reviewer 的 `APPROVED`，也不自动构成 D5B Gate 通过。
