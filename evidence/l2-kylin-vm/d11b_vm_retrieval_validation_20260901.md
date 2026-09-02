# D11B 麒麟 VM 检索验证证据（2026-09-01）

> 被测提交：`e9dba4f38dbc310854b19647d84067e5fbe6a0bc`（REWORK #111 复审后的最终 HEAD）；首轮实测基线 `3831856` 见 §二/§三 历史记录。
>
> 本文只记录本轮真实执行结果。未具备 D/C 端到端入口或 `kylin-memory.service` 的项目保持 `UNVERIFIED`。

## 一、环境与被测工作树

- VM：`Kylin-V11-2603-D11B-ffd20b9-Test`（长期 B 轨基线快照 `20-btrack-test-deps-20260821` 的链接克隆，前台 GUI 运行）。
- 来宾：Kylin V11，Linux `6.6.0-63-generic`，Python `3.12.3`。
- Vector Runtime：`kylin-ai-vector-engine=1.2.0.1-0k0.11`，`libkysdk-vector-engine-client=1.2.0.0-0k0.7`，UDS `/tmp/kylin-ai-vector-engine-1000.sock` 可用。
- 代码：以 Git bundle 在来宾克隆，`git rev-parse HEAD` 为 `38318562111bca482bb0a716fbdf73b29ce9e792`，工作树无改动。
- Python 依赖：仅安装于 `~/d11b-pylibs`，pytest `9.1.1`；未改动系统 Python 包。

## 二、D11B 检索回归（L0/L1 在真实 VM）

| 命令 | 结果 | 覆盖结论 |
|---|---:|---|
| `PYTHONPATH=~/d11b-pylibs:<memory-service> python3 -m pytest tests/retrieval tests/test_migrations_d10b.py -q` | **312 passed in 16.06s** | 包含 D11B `filter_diagnostics`：拒绝原因仅聚合计数，且断言不含正文或候选标识；覆盖 RRF、过滤、SQLite Vector Provider 与 D10B migration 回归。 |
| `PYTHONPATH=~/d11b-pylibs python3 -m pytest test_d9_retrieval_gold_spec.py -q` | **68 passed in 0.45s** | D9 Gold/评测参数契约回归。 |

## 三、真实 Vector 删除运行器（L2）

1. 使用 VM 实际 `libkysdk-vector-engine-client.so.1` 构建 `vector_bridge_cli`；构建启用 `-DKYLIN_VECTOR_LEGACY_0K0_7=1` 与 ABI `static_assert`，生成二进制 SHA-256：`2ff6ed3c03e9b02897a6b37da445431c2d6e0b58475d5a3591448664b2a74578`。
2. 在可审计工作树执行：

   ```bash
   bash tests/vector-engine/run_d10b_vector_delete_l2.sh \
     --binary ~/.local/d11b-sdk/bin/vector_bridge_cli
   ```

3. 运行器元数据绑定 `tested_commit=38318562111bca482bb0a716fbdf73b29ce9e792`，桥接源码 SHA-256 `5f0e1310023b1fabc50df5d7a591e4c6f427892a87977706daea565a148d54d9`，运行器 SHA-256 `cf820947c33db6bd6358bbc2c03e084c6475cdf9d4b4347e9e8b70add93e4147`。
4. **15/15 通过，退出码 0**：创建集合、写入、同用户精确删除、删除后查询、跨用户隔离、版本不匹配、删除重放、空/未知/未配对/超长选择器失败关闭；临时 `d10b_` Collection 已清理。

该 L2 证明最终提交在真实 Engine 上保持 D10B 物理删除隔离协议。D11B 的 Python 过滤诊断不改变 bridge/运行器源码；D11B 自身诊断行为由上节 VM pytest 覆盖。不得将本项表述为 D/C 服务端到端联调或重启恢复验证。

## 四、未验证项与跨轨阻塞

- `systemctl --user is-enabled kylin-memory.service` 返回 `not-found`，`is-active` 为 `inactive`，unit 不存在。
- 因此本轮不能执行 D11B 的服务重启、OS 重启、正式 Memory Service health/index state，或 C 端输入到检索结果的端到端验收。
- 这些项目依赖 D 轨部署/systemd 与 C 轨演示输入，均保持 `UNVERIFIED`；B 轨不代为安装 unit、补接服务或实现客户端。

## 五、结论

- D11B 过滤诊断及既有 B 轨检索/迁移回归已在同一麒麟 VM、同一提交下通过。
- 最终提交上的真实 Vector 精确删除 L2 已通过并完成资源清理。
- 服务/OS 重启与 D/C 端到端项未达成；本证据不宣称 D11B 全功能联调完成。

## 六、返工说明（REWORK #111，2026-09-01）

- MEDIUM-01 方案 A：公共 `RetrievalOutcome.filter_diagnostics` 将 `cross_user` 泛化为 `security_filtered`；精确 `cross_user` 计数仅保留在可信内部 telemetry/debug 边界（`_retrieve_graceful_with_internal_diagnostics`），不进入普通检索 consumer。
- 该改动为 Python 层诊断输出改造，不触及 Vector bridge/运行器源码；上文 VM 实测仍绑定 `tested_commit=3831856`。
- 新行为的宿主回归：`tests/retrieval + tests/test_migrations_d10b.py + tests/test_config_d4d.py` → **324 passed**（含新增 internal-only 边界测试）；D9 Gold 契约 **68 passed**；`git diff --check` 通过。
- 最终 HEAD `e9dba4f` 已在同一麒麟 VM 完成复测（见 §七），MEDIUM-01 证据绑定闭环。


## 七、REWORK 复审 VM 复测（2026-09-02，最终 HEAD e9dba4f）

> 目的：按 D 轨复审 MEDIUM-01（证据绑定）要求，在最终 HEAD `e9dba4f` 于同一麒麟 VM 重跑 L0/L1 检索回归与真实 Vector 删除运行器，回填证据绑定。

- 被测提交：`e9dba4f38dbc310854b19647d84067e5fbe6a0bc`（REWORK #111 最终 HEAD）；以受控 Git bundle（SHA-256 `ec0d1086…`）部署，`git rev-parse HEAD` 校验一致，部署工作树由 `git archive e9dba4f` 重建。
- VM 同前（`Kylin-V11-2603-D11B-ffd20b9-Test`，GUI 前台）；来宾 Kylin V11 / 6.6.0-63 / Python 3.12.3；Vector Engine 1.2.0.1 与 UDS 可用；`vector_bridge_cli` SHA-256 仍为 `2ff6ed3c…`。

| 命令 | 结果 | 覆盖 |
|---|---:|---|
| `PYTHONPATH=~/d11b-pylibs:<memory-service> python3 -m pytest tests/retrieval tests/test_migrations_d10b.py tests/test_config_d4d.py -q` | **324 passed in 8.54s** | MEDIUM-01 泛化后检索回归 + D10B migration + D4D 配置（含新增 internal-only 边界测试） |
| `python3 -m pytest tests/retrieval/test_v006_fusion.py -q` | **52 passed in 0.35s** | fusion 定向：filter_diagnostics 脱敏与 internal-only 边界 |
| `PYTHONPATH=~/d11b-pylibs python3 -m pytest test_d9_retrieval_gold_spec.py -q` | **68 passed in 0.12s** | D9 Gold/评测参数契约 |

- Vector 删除运行器（从 git 仓库 `kylinOS-agent-memory-d11b-git` 执行以保证元数据绑定）：`bash tests/vector-engine/run_d10b_vector_delete_l2.sh --binary ~/.local/d11b-sdk/bin/vector_bridge_cli`
  - 元数据：`tested_commit=e9dba4f38dbc310854b19647d84067e5fbe6a0bc`、桥接源码 `5f0e1310…`、运行器 `cf820947…`（与首轮一致，源码零变化）。
  - **15/15 通过，退出码 0，临时 `d10b_` Collection 清理完成**。
- 日志：`evidence/l2-kylin-vm/d11b_l2_session_e9dba4f.log`（SHA-256 `c6a61f2c…`）、`evidence/l2-kylin-vm/d11b_vector_delete_l2_e9dba4f.log`（SHA-256 `378867b3…`）。
- 本复测将 D11B 检索回归 / D9 Gold / Vector 删除协议的证据绑定到最终 HEAD `e9dba4f`；服务/OS 重启与 D/C 端到端仍保持 `UNVERIFIED`。
