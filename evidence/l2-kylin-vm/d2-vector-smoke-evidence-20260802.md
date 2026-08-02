# D2-B Vector Engine 安全回归与恢复证据

- 日期：2026-08-02（Asia/Shanghai）
- 分支：`test/B-vector-engine-user-isolation`
- 被测提交：`278d2bc1041ec884b4285ad9f8195a9080e5cb53`
- 技术运行结论：`PASS`
- 证据等级：E4（真实麒麟宿主调用）
- 审查状态：`PENDING`；本报告不代表 Review 通过或具备合并资格
- 范围：D2 及之前；不包含 D3 Provider、IPC、RRF 契约或生产 Schema

## 1. 环境与身份绑定

- 虚拟机：`Kylin-V11-D2-OldClient-20260727`
- 架构：x86_64
- 客户端：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 服务端：`kylin-ai-vector-engine 1.2.0.1-0k0.11`
- 公开 SDK commit：
  `2213447ef765e709e93f94d4177f4417478fe8ea`
- 正式探针 SHA-256：
  `2c9f7c25edca1415e606b936222f4400092f9dae47a3488d89e0ec29d5332d77`
- 探针源码 SHA-256：
  `49c6771427082708d8f7b9b46c079167dc9a63b91bf32a2cb2c45421ebcbce16`
- runner SHA-256：
  `4d3baeba4d3fff0a5ee71e6728326f98140a98feab9802857a62d5c723dda093`
- ABI 补丁 SHA-256：
  `73e5ffb79d06496f99d8e5cd76472843dd7ebedf1f9e34ae18face906218eda1`
- ABI 断言 SHA-256：
  `8b8567cfbb9c60e93d58b26359023315e33150c8946e18243d75a7bcf26fa5d7`

prepare 在执行探针前原子创建 manifest。verify 与 cleanup 均严格复核上述
身份，以及 run ID、数据库规范路径与文件身份、Collection、app ID、服务单元
和 prepare InvocationID。manifest SHA-256 为
`c01a01d9ea31d59b763b1dfe5b8fa77f92a98f3cfcea9ea50a3f0b974805cf1e`。

## 2. 隔离边界

- run ID：`20260802b1`
- 固定测试根目录：
  `/home/yanmouren778/d2-b-vector-smoke-20260802b1`
- 测试数据库：
  `/home/yanmouren778/d2-b-vector-smoke-20260802b1/runtime/d2-vector-smoke.db`
- 数据库文件身份：`2052:2230954`
- Collection：`d2_vector_smoke_20260802b1`
- 用户服务：`d2-vector-engine.service`
- 默认数据库：
  `/home/yanmouren778/.local/share/kylin-ai-vector-engine/default.db`
- 默认数据库测试前后 SHA-256：
  `54a1ecb52a7dfd7f05c0fea5cc3ffdc6f0a12fb607c9f7fc921c0ecc97a4f768`

安全回归共 10 项 PASS，覆盖合法根目录、根目录外路径、符号链接、默认数据库
同文件身份、非法 run ID、非法 Collection，以及 manifest 缺失、精确匹配和
字段不匹配。正式服务进程参数明确指向测试数据库；默认服务停止后才启动测试
服务，两者不并行占用同一 socket。

## 3. 正向功能结果

| 阶段 | PASS | FAIL | 结论 |
|---|---:|---:|---|
| 安全回归 | 10 | 0 | 路径、文件身份、run ID、Collection、manifest 门禁通过 |
| 构建 | 17 | 0 | 固定 SDK commit 与 ABI 补丁构建通过 |
| prepare | 43 | 0 | Collection、CRUD、用户过滤、向量过滤、碰撞保护通过 |
| 碰撞后只读 verify | 11 | 0 | 拒绝同名 prepare 后原数据仍完整 |
| 重启后 verify | 32 | 0 | InvocationID 变化且持久化状态通过 |
| cleanup | 27 | 0 | 仅删除本次测试 Collection |

测试数据包括 `user-alpha` 的 `{101,102}` 与 `user-beta` 的 `{201,202}`。
运行时检查确认：

1. 查询结果中的 `user_id` 字段真实返回且全部为 `user-alpha`；
2. 用户过滤结果集合精确等于 `{101,102}`，不是仅检查数量或包含关系；
3. id 201 作为跨用户、向量更相似的诱饵，不能进入 alpha 结果；
4. alpha 搜索首项为 id 101；
5. upsert id 102 后仍保持 `user_id=user-alpha`；
6. 删除表达式同时限定 `user_id == "user-beta"` 与 `id in [202]`；
7. prepare 终态精确为 `{101,102,201}`；
8. 服务重启后集合、终态、用户过滤和向量过滤均保持；
9. SDK 原始 score 只按未验证语义记录，不宣称已归一化相似度。

## 4. 预期负向门禁

以下 FAIL 是测试目标，不是运行失败：

| 日志 | 预期结果 | 实际退出状态 | 是否执行探针 |
|---|---|---:|---|
| `d2-vector-collision-negative-20260802.log` | 同名 Collection 已存在时拒绝 prepare | 1 | 探针进入碰撞前置检查后拒绝，不 drop、不改数据 |
| `d2-vector-preverify-no-restart-20260802.log` | InvocationID 未变化时拒绝 verify | 1 | 否 |
| `d2-vector-manifest-mismatch-20260802.log` | app ID 与 manifest 不一致时拒绝 verify | 1 | 否 |

碰撞负向日志中有 2 个 FAIL 行：一个为具体前置检查，另一个为探针顶层汇总；
二者描述同一次预期拒绝。随后独立 verify 以 11 PASS / 0 FAIL 证明
`{101,102,201}` 及 upsert 后字段未被碰撞尝试改变。

所有受控命令均有 30 秒上限。成功阶段退出状态为 0，预期负向阶段退出状态为
1；没有 124、137 或 `timeout=true`，也没有发生超时后继续执行探针的情况。

## 5. 服务重启与恢复

- prepare InvocationID：`a468b4e645c543559be359e8dfc69a36`
- restart 后 InvocationID：`231827b1e4d7409b99517b4d4c37b958`
- 默认服务恢复前 PID：`35771`
- 默认服务恢复后 PID：`50261`
- 默认服务恢复前 InvocationID：`3a8c325c90aa4c1ca8ad350ed9a66b8b`
- 默认服务恢复后 InvocationID：`6cbc7faf5cd244f59f5826e8b4ba03ff`

退出恢复陷阱完成并验证：

1. 测试服务停止，用户单元文件删除，reload 后状态为 `not-found/inactive`；
2. 确认无监听者后删除陈旧测试 socket；
3. 默认服务恢复为 `active/running`，默认引擎重新指向默认数据库；
4. 默认数据库 SHA-256 前后完全相同；
5. 临时 KySec 信任从 `verified` 撤销为 `unknown`；
6. 临时 SSH key tag 计数从 1 变为 0，其他 key 行保留，权限仍为 600；
7. 使用已撤销私钥再次登录返回 255 与 `Permission denied`；
8. 两条临时 NAT 转发均已删除；
9. 目标 VM 最终保存为可恢复的 `saved` 状态，目标运行进程数为 0。

SSH key 撤销的 VM 原始日志保留在正式测试根目录，SHA-256 为
`3d9a0a1410206c03330215374b181e507e41c1fd3e629ded6fdf0c0042c246f2`。
仓库中的 `d2-vector-ssh-key-revocation-host-capture-20260802.log` 是宿主捕获的
规范化转录，明确记录原始日志路径、哈希、撤销前后计数和失败登录复核；它不
冒充远端原始文件。

## 6. Review 问题映射

| 问题 | 本次证据 |
|---|---|
| C01 | 同名 Collection 负向拒绝 + 独立只读 verify，证明不 drop 且数据保留 |
| C02 | 10 项安全回归覆盖默认 DB 同文件身份、符号链接和根目录外路径等门禁 |
| C03 | runner 与探针均绑定 `d2_vector_smoke_<run_id>`，非法值在执行前拒绝 |
| C04 | `278d2bc` 的 v1 manifest 绑定静态身份；尚未记录 `created_by_prepare` 成功状态，不能据此宣称该项完全关闭 |
| C05 | 原始日志绑定被测 commit、源码、runner、ABI 与二进制哈希；manifest 哈希由独立捕获日志记录 |
| C06 | 独立基线与恢复日志记录默认 DB 哈希、服务 PID/InvocationID、socket、KySec 和临时 key |
| S01/S04 | 读取返回的 `user_id`，结果集合精确为 `{101,102}` 且全部属于 alpha |
| S02 | 删除表达式同时限定用户与 id |
| S03 | 原始 score 明确标为语义未验证 |
| S05 | prepare/verify/cleanup 生命周期及清理均由正式日志证明 |

## 7. 原始证据校验和

| 文件 | SHA-256 |
|---|---|
| `d2-vector-build-20260802.log` | `0a7766281ac33fd808b38466be65b757b03bd063c41013bef1615b80e056f8b4` |
| `d2-vector-safety-test-20260802.log` | `76123a7ba79a63d80b3cca2e9bd82516aa095118f9b307415c3aef0e573e3203` |
| `d2-vector-service-switch-20260802.log` | `8067f36fb208b2d24f70f95f27264eb94051044c283006be1d7530366fd8d7c9` |
| `d2-vector-prepare-20260802.log` | `8f2ca464124c23d1f957b556634a3395af475da6184d268adf41d20cd04c3f6f` |
| `d2-vector-collision-negative-20260802.log` | `c965d664981a0429eb9af061419b2595c81e7823de7ec18c2474e728fabfbc08` |
| `d2-vector-collision-preserved-20260802.log` | `392f23f1ddaed6ea2a0b9821bfd1b16c06b4e72e6523cadfa9b3867766ba2114` |
| `d2-vector-preverify-no-restart-20260802.log` | `c06667e676d07dcd07241fd9da9644060eabae8750ad537b06ad5bbd08c4f694` |
| `d2-vector-manifest-mismatch-20260802.log` | `e3c0d5d9faf7f5d1c1289ed1a0139637585b46315a151ef0bacc97aeb882415a` |
| `d2-vector-restart-20260802.log` | `94b2e79199271e1a54fc57e3772ee351724d870180e1d69fe7e5c8616435bf72` |
| `d2-vector-verify-20260802.log` | `c673fe574903bcc083eb60060c92b86885993a838b3205fff342fa680c298351` |
| `d2-vector-cleanup-20260802.log` | `1f948553ac002c684937b22e50637b42b9e59f534152b7c3973bd4b10ba87cfd` |
| `d2-vector-recovery-baseline-20260802.log` | `3cb6e29a63cb97f8de1e815fa30e41fa0c364d1cb0e445d1f21b7e24723100b8` |
| `d2-vector-recovery-after-20260802.log` | `cf84ab457557af74fe38a65b80a74d6c74e7eaea006142352da1648827b6c307` |
| `d2-vector-kysec-before-20260802.log` | `53ba5e3cda363ae5dd6a1a91f34cc1771a1e29032aae39ba8d258df77b19be97` |
| `d2-vector-kysec-after-trust-20260802.log` | `198d2ee388c1f8962d43cc43471dd82edd98d9a43201a2fe67b8b56144f41f29` |
| `d2-vector-kysec-revocation-20260802.log` | `3fba17f7ce62c8d952c5958f77682d392759546c6208ce3687315db6146902ee` |
| `d2-vector-ssh-key-revocation-host-capture-20260802.log` | `5567c3512ed7619a3ce1e82ff3fd9e5b0fe4694ff70ef86fc57b8e9147555be9` |
| `d2-vector-service-journal-20260802.log` | `845e46d35e256afd5ca06ffff72e1401b91784dd2d7d206f3973b8a8846e7cf6` |
| `d2-vector-manifest-20260802.log` | `260551c4c7d02469129931fcbc134acf490f2c9e48d47d8b3163a572f7d1e30a` |
| `d2-vector-smoke-20260802.manifest` | `c01a01d9ea31d59b763b1dfe5b8fa77f92a98f3cfcea9ea50a3f0b974805cf1e` |

## 8. D2 边界与限制

本证据仅证明指定麒麟 V11 x86_64、指定旧版客户端与服务端组合中的真实
Collection、CRUD、用户过滤、向量过滤、删除、重启持久化、安全门禁和恢复。
并发、性能、原生 Hybrid/RRF、Provider、IPC、错误码、RRF 参数与生产
Collection Schema 均未在本次扩展或冻结。

本报告严格绑定 `278d2bc1041ec884b4285ad9f8195a9080e5cb53`。其后的
Manifest 所有权状态、数据库快照字段或安全回归修改必须先形成新的被测 Commit，
再重新执行完整 L2 流程；不得复用本报告证明未提交代码。
