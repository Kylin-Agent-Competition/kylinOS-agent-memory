# 16 轨道 B — D5B 检索垂直链路宿主验证报告（V002–V007）

> 结论：`B-D3-V002`–`V006` 及 D5B 边界验证（空库/服务故障/Top-K）取得麒麟 VM 宿主证据；
> `V007` 评测脚本/配置版本绑定为 `PARTIAL / L1 / LOCAL_UNCOMMITTED`（Windows-local 脚本烟测），其正式量化评测仍 `DEFERRED_VM`（依赖 E 轨 Gold Label/封存集）。
> `TD-004` 已 `Resolved`：V005 已实证 SDK 无原子切换 API，routing-switch 等价方案经 D 轨（周子腾，2026-08-23）冻结为关闭路径。

- 日期：2026-08-23
- 系统：Kylin V11 x86_64，内核 `6.6.0-63-generic`
- 项目基线：`origin/main@8bf4c9b`，本分支 head `a7fa30c`（EIR 重跑 tested_commit）
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
| V006 | FTS5 + Vector + rrf-v1 端到端 | `PASS_VM`：FTS5 BM25 + 真实 Vector + 应用层 RRF 在 VM 跑通 | `v006_e2e_fts5_vector_rrf_a7fa30c_20260825.log` |
| V007 | Recall@K/MRR/nDCG/P95 | `PARTIAL / L1_LOCAL`（Windows-local 脚本烟测）：评测脚本输出三通道指标；正式量化评测仍 `DEFERRED_VM` | `v007_eval_20260823.log` |

## 2. D5B 边界验证（空库 / 服务故障 / Top-K）

| 项 | 结论 | 归档日志 |
|---|---|---|
| W1 空库 | `PASS`：空 FTS5 + 空 Vector + 融合返回可解释空结果，退出码 0 | `d5b_w1_empty_a7fa30c_20260825.log` |
| W2 服务故障 | `PASS`：停服务 code=3 → `provider_unavailable`，FTS5 命中保留，恢复自愈 | `d5b_w2_service_fault_a7fa30c_20260825.log` |
| W3 Top-K 边界 | `PASS`：top_n=1/超命中数/超大/空库均正确 | `d5b_w3_topk_a7fa30c_20260825.log` |

## 3. 证据归档 SHA-256

| 文件 | SHA-256 |
|---|---|
| `v002_error_mapping_20260823.log` | `96ada15ace392229b211b44d6ba34d761d834f2af84414f2418ec520e6e62525` |
| `v003_deadline_cancel_20260823.log` | `cf1175a166621e9ef8ba6655d6e1cd8b650d98ef0ba9bc4d03d3b28b62abfc3c` |
| `v004_generation_rebuild_20260823.log` | `99707a68cda4ca9988b6b5b14b355a0806fe1ae99f724e8f18e90ac834dec0f5` |
| `v005_atomic_switch_20260823.log` | `a12243c17de66eafd6bd0710a1ed7b8fae21eabd3b1b665d38f9421973aeb78d` |
| `v006_e2e_fts5_vector_rrf_a7fa30c_20260825.log` | `9aec6b0e5dd75a935ed074d4175a1ed3998d39cd522f20a80126e73ed97ea17f` |
| `d5b_w1_empty_a7fa30c_20260825.log` | `8f8d5bf0cc92559dbb2621d677401f14cdb71dc44f8275c1bbb1c278492b9200` |
| `d5b_w2_service_fault_a7fa30c_20260825.log` | `adfedb0b653d17abed95d0d2f5c6ffee14b0b7c4e81b0a2262778b79d64699d3` |
| `d5b_w3_topk_a7fa30c_20260825.log` | `e4b571f779fa4dbde41b74e1ba3771de6cb3f3df2119c7fc490b3fe187b2499c` |
| `v007_eval_20260823.log` | `11ba6aa29768052d994c0d11e358db858e42cb9a4ac95d8cded89c1419d88591` |

## 4. 候选文件 SHA-256（完整见 index.yaml）

| 文件 | SHA-256 |
|---|---|
| `tests/vector-engine/d2_vector_error_mapping.cpp` | `7bb77f6f776ad562b7a148099952ee9fb9f333bee2eca566b615ed805cba12bb` |
| `tests/vector-engine/d3_vector_deadline_cancel.cpp` | `764834b8c7abbb6c16f48af79c10c58812aa2634ae1928f051a491a9a47cc5dd` |
| `tests/vector-engine/d4_vector_generation_rebuild.cpp` | `f77d9cf31b1191d3b74e6aa63de9e2a5da4d944359a48dd1fd514c0decf2158d` |
| `tests/vector-engine/d5_vector_atomic_switch.cpp` | `dd1371460d4c9776d74017a16d365970fed81b0d1ec1a501a75ed6ec065e8044` |
| `tests/vector-engine/vector_bridge_cli.cpp` | `079bf7cbe90b31da930215ca4558d07f04214077664d1052bbd3c6795b9b368d` |
| `memory-service/retrieval/fts5.py` | `7dcac1a0aefbe33c6e727845452ac13419d2b9369294aca5e2c6b2390f77eec3` |
| `memory-service/retrieval/fusion.py` | `d0cb113816db5b83b218a69d5024610546fd47cf608589fbd49eec8e3d588c6f` |
| `memory-service/retrieval/real_vector_provider.py` | `9ae2c116160835208f34209c7db5b6243589e595230abd9bcfc8b66c6aa32ae5` |
| `memory-service/retrieval/vector_sdk_errors.py` | `18103e61f5ec0ce823d6d5dff5017c788191173613629834caf8bea6ad48ce1c` |
| `memory-service/retrieval/evaluation.py` | `4ae5204cfba82969c283f35d71cd6695f43a0812d505b16164d1cc2ed4c89a51` |
| `scripts/v006_e2e_demo.py` | `d16043a0b011abc54936a9769b8df1430f1d2f0cc4abf6edf31ecf2a164a088a` |
| `scripts/v007_eval.py` | `c634ba0f5b11a899f0dc1197b1b7f045d57a23fa84ba0a2f53ea2dddac1cb69b` |

## 5. 状态边界（如实，不虚标）

- `V007` 正式量化评测（Recall@K 达标等）依赖 E 轨 Gold Label/封存集，`datasets/` 当前尚未封存；本报告将 V007 界定为 Windows/local 脚本烟测（PARTIAL / L1 / LOCAL_UNCOMMITTED），正式量化评测仍 `DEFERRED_VM`。
- `TD-004` 已 `Resolved`：V005 已实证「无原子切换 API」，「routing-switch 等价方案」经 D 轨（周子腾，2026-08-23）冻结为关闭路径；`supports_atomic_generation_switch` 保持 `false/UNTESTED`，激活仅走 `routing_switch`/`maintenance_window`，禁止 `atomic_switch`。
- 本报告不替代一名独立、非作者 Reviewer 的 `APPROVED`，也不自动构成 D5B Gate 通过。
