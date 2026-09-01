# D11B 麒麟 VM 检索验证证据（2026-09-01）

> 被测提交：`38318562111bca482bb0a716fbdf73b29ce9e792`（`fix: 补齐D11B检索过滤诊断`）。
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
