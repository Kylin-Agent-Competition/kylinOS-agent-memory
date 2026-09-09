# D14B B 轨替代路线收口报告（2026-09-09）

## 1. 路线裁定

本批按负责人授权，**放弃继续等待或在 D14D cleanVM 上执行的路线**，改以现有
`Kylin-V11-2603-BTrack-Base` 作为 B 轨替代验证环境，完成 D14B 的工程验收。

该决定不把 BTrack 冒充 D14D，也不把结果写成 D14D Formal L3；它只定义本 PR 的
B 轨替代交付边界：在同一 tested commit 上，用真实 Vector Engine、真实 SQLite/FTS5、
真实 RRF 编排和真实 service/OS restart 完成可复现的检索与索引全生命周期验证。

## 2. 替代环境身份与边界

- VM：`Kylin-V11-2603-BTrack-Base`
- guest：`yanmouren778-pc`，SSH `127.0.0.1:2222`
- tested commit：`ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- checkout：`/home/yanmouren778/d14b-ba3b50e-full-preparation`，工作树干净
- Vector Engine：真实 systemd 服务与真实 SDK bridge；测试集合均为临时集合并清理
- 原始替代日志与摘要：VM `~/d14b-substitute-20260909/`

限制：该 VM 不是 D14D cleanVM；未使用 D14D 身份、冻结 package bytes、正式 handoff
或 Formal evidence root。因此下文结论是 `BTRACK_SUBSTITUTE_PASS`，不是
`D14D_FORMAL_L3_VERIFIED`。

## 3. 验证结果

| 验证面 | 结果 | 证据摘要 |
| --- | --- | --- |
| Preparation harness | PASS | `tests/retrieval/test_d14b_harness.py`：62 passed |
| Retrieval 回归 | PASS | `memory-service/tests/retrieval`：365 passed in 26.86s |
| 生产 Repository/forget/rebuild/index-chain | PASS | 4 个生产生命周期测试文件：136 passed in 133.51s |
| Vector 精确删除 | PASS | D10B：15/15；同用户、跨用户、版本不匹配、重复删除和 fail-closed 均通过 |
| FTS5 删除与 rebuild | PASS | 删除目标后 rebuild、重开库均不再命中，控制记录保留 |
| Vector 删除后重建 | PASS | `(101,v1)` 删除后，重建前后均只命中 `(102,v2)`；另一用户 `(201,v1)` 保持命中 |
| FTS5 + Vector + RRF | PASS | V006 真实链路通过，三路结果完成融合并清理集合 |
| Vector service restart 持久化 | PASS | restart + `vector_db_load` 后查询集合与重启前一致 |
| Vector OS reboot 持久化 | PASS | guest reboot 后重新加载 DB，`(301,v1),(302,v2)` 与 reboot 前完全一致 |
| 性能采样 | 已记录 | 500 条语料、30 次/通道：FTS5 P50/P95 `5.630/10.027 ms`；Vector `107.234/148.725 ms`；RRF `2.547/5.473 ms` |

## 4. 替代验收结论

`D14B_BTRACK_SUBSTITUTE = COMPLETE`

本 PR 范围内 B 轨检索与索引生命周期已完成替代验收：持久化、重建、删除无残留、
跨用户隔离、服务重启、OS 重启、RRF 融合和性能采样均有当前 tested commit 的
BTrack 实测结果。没有未完成的 B 轨实现项需要等待 D14D 才能继续。

## 5. 明确未宣称事项

- 不宣称 D14D cleanVM 发布回归通过。
- 不宣称 D14D Formal L3、正式 package intake 或四路 Formal capture 已通过。
- 性能仅为替代环境 delta；未绑定 D13B 冻结数据集和性能阈值，不写性能达标。

## 6. 复现入口

```text
cd /home/yanmouren778/d14b-ba3b50e-full-preparation
PYTHONPATH=memory-service <runtime-python> -m pytest -q memory-service/tests/retrieval
bash tests/vector-engine/run_d10b_vector_delete_l2.sh --binary <vm-vector-bridge-cli>
```

其余替代驱动、重启前后摘要和性能 JSON 位于 VM `~/d14b-substitute-20260909/`，
不进入 D14D Formal evidence root。
