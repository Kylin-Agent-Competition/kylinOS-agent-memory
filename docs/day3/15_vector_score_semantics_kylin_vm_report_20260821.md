# 15 轨道 B — Vector raw score 麒麟 VM 验证报告

> 结论：`B-D3-V001 PASS_VM`。此结论只适用于下列固定 SDK、运行库、服务和候选代码组合。

- 日期：2026-08-21
- 系统：Kylin V11 x86_64，内核 `6.6.0-63-generic`
- 项目基线：`origin/main@2b8bed7b2cae33bb5a00e1291fb6ac00ec304358`
- SDK 源码：`2213447ef765e709e93f94d4177f4417478fe8ea`
- 运行库包：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 运行库：`libkysdk-vector-engine-client.so.0.0.1`
- 运行库 SHA-256：`58c2bf38b392e8bf3d5ef454e1198a459203e62d67751cd06253b510e28b4cf5`
- 服务数据库：由 `kylin-ai-vector-engine.service` 管理的用户数据库

## 1. 被测候选绑定

测试在上述 `main` 基线上加载本分支候选文件。未提交候选以 SHA-256 绑定，避免把基线
commit 错写成候选实现 commit：

| 文件 | SHA-256 |
|---|---|
| `scripts/run_d1_vector_baseline.sh` | `ed4c13259edbff5ed5f25aae7ad7585b342d0ccff4d1bfe891ff06f6c167daed` |
| `tests/vector-engine/d1_vector_baseline.cpp` | `fc263166b0872b2e6936dac18c45709879409d642b1cdb93b782ac8ae999366f` |
| `tests/vector-engine/run_d1_vector_baseline_legacy_vm_test.sh` | `f16856df6e3278e75d057c457f7d8588588886b79a9e4e8e12583573e3372554` |

## 2. 受控 score 实验

查询向量为单位向量 `[1, 0, 0, 0]`，固定三条候选：identical、orthogonal、opposite。
真实 Vector Engine 连续执行 5 次，结果如下：

| 候选 | raw score | 排序 |
|---|---:|---:|
| identical | `1` | 1 |
| orthogonal | `0` | 2 |
| opposite | `-1` | 3 |

五轮结果均为有限数且在 `1e-6` 容差内稳定，满足严格关系
`identical > orthogonal > opposite`。当前固定组合的 raw score 可解释为余弦相似度：

- 方向：越高越接近；
- 实测范围：`[-1, 1]`；
- 典型点：identical=`1`、orthogonal=`0`、opposite=`-1`。

该结论允许同一固定组合内校验 Vector 排序和分数异常；不允许据此跨 SDK/服务版本、
模型或检索通道直接比较 raw score。混合检索仍按 `rrf-v1` 使用名次融合。

## 3. 完整工作流

| 步骤 | 结果 |
|---|---|
| prepare：建集合、插入、过滤查询、向量检索、upsert、delete、score 语义 | `PASS` |
| 重启 `kylin-ai-vector-engine.service` | `PASS` |
| 服务实例变化 | `b14c1675421f41c6a6629cec19072d0a` → `678e13d585514d43b6bd7f27ce9eb68d` |
| verify：重启后集合、记录与向量检索仍成立 | `PASS` |
| cleanup：删除测试集合 | `PASS` |
| 遗留 D2 安全回归 | `45/45 PASS` |
| Bash 语法与非遗留 SDK 源码兼容检查 | `PASS` |

## 4. 兼容性处理与异常

安装运行库的 ABI 与取得的 SDK 头文件不一致。测试执行器仅在运行库版本精确等于
`1.2.0.0-0k0.7` 且 SDK commit 精确匹配时，在临时 SDK 副本上以 `--fuzz=0`
应用仓库既有兼容补丁；原 SDK 工作区保持 clean。ABI 探针确认运行库使用默认
`ConnectParam()`、带 `shard_num` 的 `CollectionSchema` 和带 `index_id`
的 `IndexDesc` 构造签名。

VM 中系统级 `git` 与 `nlohmann-json` 头文件不可用，测试使用本轮证据目录内从缓存包
解出的只读副本。`/mnt/shared` 和 SFTP 不可用只影响证据传输方式，不影响 SDK 数据面
或服务重启验证。最终证据通过 SSH 文本通道归档。

## 5. 证据

- VM 证据目录：`/home/yanmouren778/test-rounds/B-V001-V007-2b8bed7-20260821/evidence`
- 宿主归档：`辅助生成文件/文本整理/B_V001_V007_20260821/v001-main-2b8bed7-final2/v001-evidence.tar.gz`
- 归档 SHA-256：`3dc7ab1f512e1f3f131f3b1192b17ab6ef79c2d6714185dd3de643bfdc8ca45d`
- 清单：`v001-evidence.sha256`，38 项在 VM 与宿主两端校验均为 `PASS`

## 6. 后续边界

本报告只关闭 `B-D3-V001 / TD-003`。`B-D3-V002`–`V007` 依赖 D4 Provider、调度、
generation、FTS5/RRF 和评测实现；在这些接口合并到默认分支前继续保持
`DEFERRED_VM`，不得以未合并 PR 作为实现或验证基线。
