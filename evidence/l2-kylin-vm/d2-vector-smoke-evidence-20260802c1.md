# D2-B Vector Engine 最终修复提交 L2 证据

- 日期：2026-08-02（Asia/Shanghai）
- 分支：`test/B-vector-engine-user-isolation`
- 被测提交：`b4b268e7c309308c97b1723a4554ebb68733650f`
- 技术运行结论：`PASS`
- 证据等级：E4（真实银河麒麟宿主调用）
- 审查状态：`PENDING`
- 合并资格：`false`
- 范围：D2 及之前；不包含 D3 Provider、IPC、RRF 契约或生产 Schema

本报告记录 PR #15 第二轮 Review 后最终修复提交的独立 L2 复跑。技术
Runtime PASS 不代表 Review 已通过，也不代表具备合并资格。

## 1. 环境与代码身份

- 虚拟机：`Kylin-V11-D2-OldClient-20260727`
- 架构：x86_64
- 客户端：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 服务端：`kylin-ai-vector-engine 1.2.0.1-0k0.11`
- 公开 SDK commit：
  `2213447ef765e709e93f94d4177f4417478fe8ea`
- 探针源码 SHA-256：
  `49c6771427082708d8f7b9b46c079167dc9a63b91bf32a2cb2c45421ebcbce16`
- 正式探针二进制 SHA-256：
  `2c9f7c25edca1415e606b936222f4400092f9dae47a3488d89e0ec29d5332d77`
- runner SHA-256：
  `764860e3862c19720d98baf604874a443855b9c42bdf3860638845d180d00f6a`
- ABI 补丁 SHA-256：
  `73e5ffb79d06496f99d8e5cd76472843dd7ebedf1f9e34ae18face906218eda1`
- ABI 断言 SHA-256：
  `8b8567cfbb9c60e93d58b26359023315e33150c8946e18243d75a7bcf26fa5d7`

被测项目通过完整 Git bundle 在 VM 中建立 detached checkout。checkout 的
HEAD 与预期提交完全一致，且 `git status --porcelain` 为空。

## 2. 运行身份与 Manifest v2

- run ID：`20260802c1`
- 测试根目录：
  `/home/yanmouren778/d2-b-vector-smoke-20260802c1`
- 测试数据库：
  `/home/yanmouren778/d2-b-vector-smoke-20260802c1/runtime/d2-vector-smoke.db`
- 数据库 device/inode：`2052/2231156`
- 预留时数据库大小：8192 bytes
- 预留时数据库 SHA-256：
  `9a4aa7159950abbb79a7e304f971d9fb6dbe8e18c19478cceb8c57f96921ab92`
- prepare 后数据库大小：12288 bytes
- prepare 后数据库 SHA-256：
  `5627d23260f0e02b0ccaf4416a36f89c283de3bb592d7c3908bd0d421e30c648`
- Collection：`d2_vector_smoke_20260802c1`
- 测试服务：`d2-vector-engine.service`
- Manifest 最终 SHA-256：
  `e03167d99867fa89ca328d42212d664c318802d2f09dba1034ac5cd4b26ff05d`

prepare 在探针执行前原子创建 `format_version=2` 的预留 Manifest，初始
`created_by_prepare=false`。只有 prepare 探针完成且数据库快照重新取得后，
runner 才原子替换为 `created_by_prepare=true`，并写入 `prepared_at_utc`、
prepare 后数据库大小和 SHA-256。verify 与 cleanup 均校验同一 Manifest 的
提交、源码、runner、ABI、二进制、DB 路径及文件身份、Collection、app ID、
服务单元和 prepare InvocationID；任一字段不一致即拒绝执行。

## 3. 执行结果

| 阶段 | PASS | FAIL | 结论 |
|---|---:|---:|---|
| 安全回归 | 15 用例 | 0 | 默认 DB、符号链接、目录、相对路径、run ID、Collection、Manifest 和 DB 替换门禁通过 |
| 构建 | 17 | 0 | 固定 SDK commit 与旧版 ABI 兼容构建通过 |
| prepare | 52 | 0 | Manifest 预留/完成、Collection、CRUD、用户隔离和向量过滤通过 |
| 同名碰撞负向 | 4 | 2（预期） | prepare 拒绝同名 Collection，不执行 drop |
| 碰撞后只读 verify | 11 | 0 | `{101,102,201}` 及 upsert 字段保持不变 |
| 未重启 verify | 19 | 1（预期） | InvocationID 未变化时拒绝，未执行探针 |
| Manifest 不匹配 | 15 | 1（预期） | app ID 不一致时拒绝，未执行探针 |
| 服务重启 | 1 | 0 | InvocationID 确认变化 |
| 重启后 verify | 33 | 0 | Collection、CRUD 终态、用户过滤和向量过滤持久化 |
| cleanup | 28 | 0 | 仅删除本轮 Manifest 明确拥有的 Collection |
| 环境恢复 | 8 | 0 | 默认服务、数据库、Socket 和测试单元恢复检查通过 |

三个预期负向命令退出状态均为非零，且没有 124/137 或 `timeout=true`。
未重启 verify 和 Manifest 不匹配日志均不存在 `step=probe_execute`。

## 4. 数据面与用户隔离

测试数据包含 `user-alpha` 的 `{101,102}` 和 `user-beta` 的 `{201,202}`。
id 201 与查询向量完全相同，但属于另一用户。prepare 与重启后 verify 均确认：

1. Query 结果精确为 `{101,102}`，返回的 `user_id` 全部为 `user-alpha`；
2. Vector Search 结果精确为 `{101,102}`，id 101 排名第一；
3. 跨用户同向量诱饵 id 201 不进入 alpha 结果；
4. upsert id 102 后仍保持 `user_id=user-alpha`；
5. delete 同时限定 `user_id == "user-beta"` 与 `id in [202]`；
6. prepare 终态精确为 `{101,102,201}`，重启后保持不变；
7. SDK 原始 score 仅作为未验证语义的通道诊断值，不跨通道比较。

## 5. 服务重启与环境恢复

- prepare InvocationID：`7793981615914e2995d252d0c70408d1`
- 重启后 InvocationID：`50c605e541fe4c29897747261b06c6d3`
- 默认服务恢复前 PID：`50261`
- 默认服务恢复后 PID：`64498`
- 默认服务恢复前 InvocationID：
  `6cbc7faf5cd244f59f5826e8b4ba03ff`
- 默认服务恢复后 InvocationID：
  `0d3ba870c03e4659b1b90c054f40d323`
- 默认数据库前后 SHA-256：
  `54a1ecb52a7dfd7f05c0fea5cc3ffdc6f0a12fb607c9f7fc921c0ecc97a4f768`

退出恢复陷阱确认测试服务为 `not-found/inactive`、测试 unit 文件不存在、
默认服务为 `active/running`，默认引擎进程参数重新指向默认数据库，默认
Socket 恢复监听。

KySec 状态按 `unknown → verified → unknown` 完成授权与撤销。临时 Windows
SSH 公钥标签计数从 0 登记为 1，结束时从 1 撤销为 0，其他维护公钥保留，
`authorized_keys` 权限保持 600。宿主侧两条临时 NAT 转发均已删除，VM
最终保存为 `saved` 状态。

## 6. Review 问题映射

| 问题 | 本轮证据 |
|---|---|
| C-01 | 同名 Collection prepare 负向拒绝，随后只读 verify 证明原数据未变 |
| C-02 | 安全回归覆盖默认 DB 同文件身份、符号链接、根目录外、相对路径和 DB 替换 |
| C-03 | runner 与探针均绑定 `d2_vector_smoke_<run_id>` |
| C-04 | Manifest v2 绑定三阶段身份，成功 prepare 后才取得所有权 |
| C-05 | 日志、Manifest、报告和索引绑定 `b4b268e` 及源码、runner、二进制和 Manifest 哈希 |
| C-06 | 独立基线、恢复、KySec、服务、SSH 公钥和宿主 VM/NAT 原始记录 |
| R2-01 | 技术状态、Review 状态和合并资格分离；本轮保持 `PENDING/false` |

## 7. 证据文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `d2-vector-build-20260802c1.log` | `95282dcca72e606cd58c63c8147369838451661e54d76e94a685ea401642967b` |
| `d2-vector-cleanup-20260802c1.log` | `bd9ca41e7ab0deeb827f70305b1eb7d7a5fc6d6f56e399b2d724fc55f4398cce` |
| `d2-vector-collision-negative-20260802c1.log` | `283cf7f1e85ac69839011dd687abc425a11b57aefd62342a7639638c2caca8f4` |
| `d2-vector-collision-preserved-20260802c1.log` | `4e983bc1b80f318d39cd89579664b994f7b3f801aab72b18de8edfb5f716ade8` |
| `d2-vector-host-final-state-20260802c1.log` | `37140018059162316bc5857558be9c500c2030c8c1b9af918ea1865504ff59ba` |
| `d2-vector-kysec-after-trust-20260802c1.log` | `2c2e8443a13061e6449552de89bb3eba3d294dfc4ed22f21ecdb936df29f1542` |
| `d2-vector-kysec-before-20260802c1.log` | `7ad72a84f1a2b0fbb7116fdc06424f3e660128196ce95ad0d0d4a5abeb94c66f` |
| `d2-vector-kysec-revocation-20260802c1.log` | `d300862fbc8fe5074be016072f9164b4a6d2427c231b15918df3518c4ddab8ad` |
| `d2-vector-manifest-20260802c1.log` | `5eba1280d7f276f32b5fee1520dc3dd4f88dcbc9ec86a25eaf35e74d84097044` |
| `d2-vector-manifest-mismatch-20260802c1.log` | `2bc33d1c6d8b5fd59136418a21f7973612b7e4fda4167ad1546febd9c4471bd6` |
| `d2-vector-prepare-20260802c1.log` | `2afd25f8307193d2cfde47a4fdb611b08242a7e3a377a0b41a2175bb3b29beec` |
| `d2-vector-preverify-no-restart-20260802c1.log` | `ad0dce4c1a06e731b4e4535cc63b055439a54b74dcd539ac887136d8e672f709` |
| `d2-vector-recovery-after-20260802c1.log` | `658a5278a531ef0a950d53103e7da1901e8faacf4f2ec4640db0a98f54831c78` |
| `d2-vector-recovery-baseline-20260802c1.log` | `b33a7d7518a4b30f3844e6374303ec32823d112da47d3811e36ab41c0145cc87` |
| `d2-vector-restart-20260802c1.log` | `456480801a239994be2b0bb5096d2d96e45883f64d483385b59494452024c6fa` |
| `d2-vector-safety-test-20260802c1.log` | `6605c48e6773ebef29684aae28466f5f86e1601611b303353695302b2329709f` |
| `d2-vector-service-journal-20260802c1.log` | `5b864ff6938bae51050e534b6f9f84fa4d02411646849a5b8369ff6a16c4f1a9` |
| `d2-vector-service-switch-20260802c1.log` | `d93f6882fe7deefce00d8506644a9a2ba373f7753291a1529b63ab0e46b357c6` |
| `d2-vector-smoke-20260802c1.manifest` | `e03167d99867fa89ca328d42212d664c318802d2f09dba1034ac5cd4b26ff05d` |
| `d2-vector-ssh-key-revocation-20260802c1.log` | `fd37b3bf07f028018ce2c5291d7b6f0c02adc5cb1e5c4b2a07695ed45c1177f3` |
| `d2-vector-verify-20260802c1.log` | `9b027adaa4c6ce6d02024af2e91c06cf4abcadba2cf75ac925f869c901727c1f` |

VM 输出的 `ss` 在四行末尾包含终端填充空格。仓库副本仅移除了这些行尾
空格，以通过 Git whitespace 检查；字段和值未改变。精确 VM 原件继续保留
在测试根目录和本地受控辅助目录中。

## 8. 限制与准入边界

本证据只证明 `b4b268e` 在指定 Kylin V11 x86_64、旧版客户端与服务端
组合中的真实运行结果。并发、性能、原生 Hybrid/RRF、D3 Provider/IPC、
统一错误码、RRF 参数和生产 Collection Schema 不在范围内。

独立 Reviewer 正式复审前，`review_status` 必须保持 `PENDING`，
`merge_qualified` 必须保持 `false`；本报告不得被解释为自行批准或允许合并。
