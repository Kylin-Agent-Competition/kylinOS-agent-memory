# D13C L2 麒麟 VM 实测 — B 轨交付汇总（归档副本）

> **来源**：B 轨（高翌哲）于 2026-09-03 交付给 C 轨的 L2 实测结论。
> **原始文件**：`D13C_L2_B轨交付给C_20260903.md`
> **归档路径**：`docs/day13/09_d13c_l2_b_track_delivery_20260903.md`

## 核心结论（供 C 轨升级用）

B 轨在 `main@b70827c` 上完成了麒麟 VM 真实实测，结论分级如下：

### VERIFIED（6 项，可升级 C 轨会话评测 runtime_status）

| # | 需求项 | 结论 | 关键证据 |
|---|---|---|---|
| B-L2-01 | FTS5 通道可用 | **VERIFIED** | 真实 SQLite FTS5 返回非空，P50=0.10ms / P95=0.34ms |
| B-L2-02 | Vector 通道可用 | **VERIFIED** | VectorCliClient→bridge→真实引擎，搜索/过滤/隔离 PASS |
| B-L2-04 | 检索延迟可接受 | **VERIFIED** | P50=0.10ms / P95=0.34ms，远低于 <500/<2000ms 阈值 |
| B-L2-08 | 跨会话检索结果可区分 | **VERIFIED** | FTS5 与 Vector 双通道均验证 A/B 命中集隔离可区分 |
| B-L2-10 | Vector 精确删除 | **VERIFIED** | D10B 15/15，删除后残留 0、跨用户不影响、可重放、失败关闭 |
| B-L2-11 | FTS5 精确删除 | **VERIFIED** | 删除后查询不再返回目标，残留 0，他用户与错用户选择器不受影响 |

### PARTIAL/BLOCKED（6 项，需 D 轨 gateway 接线后复测）

| # | 需求项 | 结论 | 阻塞原因 |
|---|---|---|---|
| B-L2-03 | RRF 混合排序 | **PARTIAL/BLOCKED** | 两通道各自真实可用，`memory.retrieve` 返回 `recall_sources=rrf` 需 gateway 主链（main 未接线） |
| B-L2-05 | context.assemble 合法 MemoryContext | **BLOCKED** | gateway `memory.retrieve` 返回空上下文，无 context.assemble seam |
| B-L2-06 | Token 预算校验 | **BLOCKED** | 同 B-L2-05（gateway 层） |
| B-L2-07 | 空结果集不产生伪 Context | **BLOCKED** | 同 B-L2-05（gateway 层） |
| B-L2-09 | 跨会话无串台（5 轮） | **BLOCKED** | 检索层隔离零泄漏已验证；"5 轮会话切换"需 C 客户端/会话 harness |
| B-L2-12 | 遗漏删除检测 | **PARTIAL/BLOCKED** | 引擎删除语义已验证；`forget.execute` 的 `executed_count==affected_count` 属 gateway/D 轨事务 seam |

## 环境信息

| 项 | 值 |
|---|---|
| VM | `Kylin-V11-2603-D13CB-0820036-Test`（VirtualBox 链接克隆） |
| OS / 内核 | 银河麒麟桌面 V11 2603 x86_64 / Linux `6.6.0-63-generic` |
| 被测提交 | `main@b70827c5e9c9e014ae2c025eb01d0adfaabd4ef9` |
| Vector 引擎 | `kylin-ai-vector-engine 1.2.0.1-0k0.11`，UDS `/tmp/kylin-ai-vector-engine-1000.sock` |

## L0/L1 回归（麒麟 VM）

- `pytest memory-service/tests/retrieval`：**358 passed**
- `pytest evaluation/test_d9_retrieval_gold_spec.py evaluation/test_d9_retrieval_dataset.py evaluation/test_d6_multisource_devset.py`：**170 passed**
- 合并全量：**528 passed in 18.21s**

## 证据文件（SHA-256 校验）

| 文件 | SHA-256 |
|---|---|
| `t1_retrieval.log` | `6a85874a932635b0bce9598032e6e52721266934999da694d539b97e694f4acc` |
| `t2_eval.log` | `d8a1c224db2a982ed492a39f8689f2985926a7fdf023373eb37e8b079f00b93f` |
| `t3_full.log` | `ab90a1b6bc232f76e4fc1089633fda807a08dfb6512da64f3fc17e4bbd18d1e9` |
| `smoke_channel.log` | `4739e285cc9c742e1125e491a2052ba7c7045a852d1bb128950ee58441787101` |
| `d6b_real_vector_provider_l2.log` | `73daec440806a6d820f52c5be598dab4aa939af95711e200053a0a906fced481` |
| `d10b_delete_l2.log` | `7cf1e73c04f62c406029b48d246b53dd7e71f57781c49a029dde666f3c3483c3` |
| `fts5_delete_probe.log` | `fb3676725a530590e4937e4331b603b60ab5db73d3d53cf8487bf1ac02d9d01a` |
| `vector_bridge_cli`（二进制） | `48da0625cf36f153a83ff6cd15b116f31552ad0c35480666a75d3b61b326dfd8` |

## 边界声明

- 本汇总为 B 轨在 `main@b70827c` 上的真实 VM 实测交付，未代行 A/C/D/E 实现或审查。
- 未修改生产代码、冻结契约，未提交 Git。
- 端到端（gateway/context/会话 harness/forget seam）未达成项保持 `BLOCKED`/`UNVERIFIED`，不虚报为完成。
