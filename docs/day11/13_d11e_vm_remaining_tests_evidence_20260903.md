# D11E 麒麟 VM 剩余测试证据（广回归 + IPC 负向补测，2026-09-03）

## 概览

- VM/提交/环境同 `09/11/12`：`Kylin-V11-2603-D11E-0820036-Test`，被测提交 `f4d9a00`（运行时=`main@b70827c`），validation profile 服务运行中。
- 本文件对应工作清单项 5/6 的「剩余补跑」：广回归（memory-service + evaluation）与 IPC 负向补充。

## 一、广回归（VM）

- 命令：`PYTHONPATH=~/d11e-pylibs:memory-service python3 -m pytest -q -p no:cacheprovider memory-service/tests evaluation --ignore=memory-service/tests/test_embedding_service_real.py`
- 结果：**1744 passed, 39 skipped, 1 error**（337.81s）。原始输出：`docs/day11/14_d11e_vm_broad_regression_20260903.log`。
- 唯一 error：`memory-service/tests/test_server_lifecycle.py::test_stop_rejects_new_business_request` → `RuntimeError: cannot join thread before it is started`（D 轨服务生命周期测试的线程 join 竞态，非 E 业务、非本批引入；本批不修改 D 轨测试）。
- 39 skipped：A 轨真实 SDK/embedding 相关等环境依赖用例（A bridge/SDK 未在本 VM 构建，属预期跳过）。

## 二、IPC 负向补测（validation profile，合成数据）

| 用例 | 输入 | 结果 |
|---|---|---|
| 跨用户遗忘（RC-06） | user_rc06_other 对 user_rc01 的 preference id=1 发起 forget.preview | ok：resolved=[]，affected_count=0（零影响，guardrail 生效） |
| 幂等重放（RC 幂等） | 同一 forget.execute 用同一 idempotency_key 重放 | 第二次 ok：completed，executed_count=0（不重复删除） |
| 硬删不升级（MEDIUM-04 语义） | execute payload 传 delete_mode=hard（预览为 soft） | ok：completed，delete_mode 仍为 soft，executed_count=0（未越权升级硬删） |

## 三、观察与结论口径

- 跨用户遗忘零影响、执行幂等重放、硬删不升级 fail-safe 均在真实服务+SQLite 上验证通过。
- 仍 `UNVERIFIED`：`memory.retrieve`/MemoryContext 主链排除（main chain pending）、真实硬删除无明文残留（需 B 轨 Vector/FTS5 删除链路）、C 轨 QML 主演示与 A 轨真实 SDK 同 Commit 端到端。
- 广回归的 1 error（D 轨 lifecycle 线程竞态）与 39 skipped（A SDK 未构建）不作为 D11E 通过/失败结论，如实记录待 D/A 轨处置。
- 本批未修改任何生产代码、冻结契约或其他轨道交付物。
