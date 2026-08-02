# D2-B Vector Engine 真实数据面与用户隔离证据

- 日期：2026-07-31
- 分支：`codex/d2-vector-smoke-formal`
- 结论：`PASS`
- 范围：D2 及之前；不包含 D3 契约冻结或正式 Provider

## 1. 环境

- 虚拟机：`Kylin-V11-D2-OldClient-20260727`
- 架构：x86_64
- 客户端：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 服务端：`kylin-ai-vector-engine 1.2.0.1-0k0.11`
- 公开 SDK 基线：
  `2213447ef765e709e93f94d4177f4417478fe8ea`
- 正式 ABI 兼容补丁 SHA-256：
  `73e5ffb79d06496f99d8e5cd76472843dd7ebedf1f9e34ae18face906218eda1`
- 正式探针 SHA-256：
  `92981863716c85f09e4546652ed12d3e7bdc7af534e8a6a8206fdb81ad9bc473`

发行版客户端二进制与同标签公开头文件存在对象布局和
`Database` vtable 差异。正式 runner 在临时干净 SDK clone 上应用
可审计补丁，并以六项 `static_assert(sizeof(...))` 阻止不匹配构建。
补丁不修改系统库。

## 2. 隔离边界

- 测试 DB：
  `/home/yanmouren778/d2-b-vector-smoke-587bee8/runtime/d2-vector-smoke.db`
- Collection：`d2_vector_user_filter_20260731`
- 默认 DB：
  `/home/yanmouren778/.local/share/kylin-ai-vector-engine/default.db`
- 默认 DB 测试前后 SHA-256：
  `54a1ecb52a7dfd7f05c0fea5cc3ffdc6f0a12fb607c9f7fc921c0ecc97a4f768`
- prepare/verify 后 D2 DB SHA-256：
  `22abc2f963b9de74d6310eb0f8ebf018124e834775d4350c2338df1bcb50714a`

测试期间临时用户单元的进程参数明确指向测试 DB；默认 DB
不在该进程参数中。

## 3. 测试数据与用户隔离

| ID | user_id | 用途 |
|---:|---|---|
| 101 | `user-alpha` | 目标用户最近允许结果 |
| 102 | `user-alpha` | 组合过滤与 upsert |
| 201 | `user-beta` | 与查询向量完全相同的跨用户诱饵 |
| 202 | `user-beta` | 删除验证 |

通过项：

1. 创建 Collection 与 FLAT/COSINE 索引。
2. 真实插入 4 行双用户数据。
3. `user_id == "user-alpha"` 只返回 `{101,102}`。
4. `user_id == "user-alpha" && category >= 20` 只返回 `{102}`。
5. 向量搜索在 id 201 更相似时仍将其硬过滤，首项为 id 101。
6. upsert id 102 后仍保持 `user_id=user-alpha`。
7. 删除 id 202 后终态为 `{101,102,201}`。
8. 服务重启后集合、CRUD 终态、用户过滤和向量过滤全部保持。
9. cleanup 删除测试 Collection。

## 4. 重启证据

- prepare 实例 ID：
  `86bae740480246b4b5955144591cf99e`
- verify 实例 ID：
  `03f5cf75866b4351bc452c57114a0635`
- runner 已验证两个实例 ID 不同。

## 5. 原始日志

| 文件 | SHA-256 | PASS | FAIL |
|---|---|---:|---:|
| `d2-vector-smoke-prepare-20260731.log` | `c0baa76512e58a91c2e1b3987cc93fd1048746f728ebcfcebb0b51b219542418` | 28 | 0 |
| `d2-vector-smoke-verify-20260731.log` | `af58e9c7d97190bde289b035424bc6aa904f72c0ac4882ec105d219cb58b7776` | 26 | 0 |
| `d2-vector-smoke-cleanup-20260731.log` | `2a2e3d8f2500888a7841308c6673577fe5622030b4b1b47498ee94dbc9dc323c` | 21 | 0 |

## 6. 非功能性执行记录

首次两次 verify 的 SSH 会话分别因 `tee` 管道持有和其外层进程组
回收延迟而超时；两次都停在 runner 预检阶段，未执行探针。
移除 `tee`，改为直接写日志并设置 `timeout -k` 后，正式 verify
在数秒内完整通过。最终证据只采用上述完整日志。

## 7. 恢复状态

- 正式探针临时 KySec 信任已撤销，状态为 `unknown`。
- 临时 `d2-vector-engine.service` 已停止并自动卸载。
- 陈旧测试 Socket 已在确认无进程和监听者后移除。
- 默认 `kylin-ai-vector-engine.service` 已恢复为 `active/running`。
- 默认引擎进程重新加载默认 DB。
- 克隆机内最终可用内存约 1.9 GiB，交换空间可用约 6.3 GiB。

## 8. D2 边界

本证据只证明当前指定版本组合中的真实 CRUD、过滤、搜索、删除、
用户隔离和重启持久化。它不冻结 `RetrievalCandidate`、Provider、
IPC、错误码、RRF 参数或生产 Collection Schema；这些仍属于 D3
及后续工作。
