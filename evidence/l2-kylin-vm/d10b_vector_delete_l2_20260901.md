# D10-B 麒麟 L2 验证证据（Vector 精确删除协议，2026-09-01）

> 对应 PR：#82（`feature/d10-b-vector-forget-rebuild`）
> 重跑绑定最终 HEAD：`4675e60de5e80bed1caf83092b5d862040825d4b`

## 一、验证环境

- VM：`Kylin-V11-2603-D10B-c15866d-Test`（链接克隆，基础快照 `20-btrack-test-deps-20260821`；Kylin V11 2603，kernel 6.6.0-63 x86_64）。
- 引擎：`kylin-ai-vector-engine 1.2.0.1-0k0.11`，UDS `/tmp/kylin-ai-vector-engine-1000.sock`。
- 客户端 SDK：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`（应用 ABI patch `kysdk-vector-engine-client-1.2.0.0-0k0.7.patch`，SDK 源码 commit `2213447ef765e709e93f94d4177f4417478fe8ea`）。
- 被测二进制：`vector_bridge_cli`（sha256 `c9909ee596959e14b184e41c730982b53fc539d14c748da7106d5b65e8a59b33`，编译 `-DKYLIN_VECTOR_LEGACY_0K0_7`；KySec 临时信任，测后已撤销）。
- 登录：SSH `yanmouren778@127.0.0.1:2222`（NAT 端口转发）。

## 二、执行与结果

- 命令：`bash tests/vector-engine/run_d10b_vector_delete_l2.sh --binary <vector_bridge_cli>`
- 运行器元数据：
  - 已测提交：`4675e60de5e80bed1caf83092b5d862040825d4b`
  - 桥接源码哈希：`5f0e1310023b1fabc50df5d7a591e4c6f427892a87977706daea565a148d54d9`
  - 运行器哈希：`cf820947c33db6bd6358bbc2c03e084c6475cdf9d4b4347e9e8b70add93e4147`
- **15/15 通过**：创建集合、写入删除测试数据、同用户精确删除、删除后仅保留同用户未选记录、删除不影响其他用户、跨用户 ID 不删他人记录、版本不匹配不删除、重复删除可重放、空选择器/未知字段/未配对版本/超长选择器失败关闭、临时集合清理完成。
- `RUNNER_RC=0`。

## 三、证据文件

- 原始日志：`evidence/l2-kylin-vm/d10b-l2-run-4675e60.log`（SHA-256 `9681EA1A298CB4A5CE5911B5665D9AFC1300F440A645A1A033715E114B77B369`）。
- 环境信息：`evidence/l2-kylin-vm/d10b-l2-environment-4675e60.txt`。

## 四、零差异证明（相对此前 c15866d 运行）

- 桥接源码哈希与运行器哈希在 `c15866d` 与 `4675e60` 两次运行中一致（`5f0e1310...` / `cf820947...`），证明 L2 被测主题（`vector_bridge_cli.cpp`、`run_d10b_vector_delete_l2.sh`、`real_vector_provider.py`）在最终 HEAD 上零差异；`4675e60` 相对 `c15866d` 的变更均为 Python 侧（SqliteVectorProvider 正式适配、残留率评测、迁移链对齐）与文档。
- 本轮在最终 HEAD 上重跑并绑定 `tested_commit=4675e60`，满足 T-4/E-5（source_log 指向仓库内可审计路径）。

## 五、说明

- 测试集合使用 `d10b_` 隔离前缀并在结束时清理；不触碰生产 Collection、SQLite 真源或其他轨道证据。
