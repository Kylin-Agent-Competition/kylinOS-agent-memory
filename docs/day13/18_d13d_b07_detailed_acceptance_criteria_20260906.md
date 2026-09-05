# D13D-B07 详细验收标准

## 前提

- 唯一被测基线：`kylin-mem/main@4a32e5c948a968f3bd4409d91deac320002baea1`。
- 固定 Dataset：`D13E_FORMAL_TESTSET_V1.jsonl`，SHA-256 为 `9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b`。
- 本标准只验收 D13D-B07 的执行适配器和真实 raw；不替代双 Seal、attestation、正式 Runner 或 PR #150 独立审查。
- 任一 P0 项失败、缺失或不可独立复核，结论为 `REJECTED / BLOCKED`。不得用 Gold、默认零值、手工 raw、单测断言或局部成功样本替代。

## A. 书面回执与版本化交付

| ID | 必须满足 | 可审计证据 | 拒收条件 |
| --- | --- | --- | --- |
| A-01 | 具名 B 轨责任人、角色、确认 ID、UTC 时间 | 完整回执 A | 占位符、匿名或口头确认。 |
| A-02 | 固定 adapter 路径和提交完整 SHA，或 artifact ID 和 SHA-256 | Git commit / artifact hash | 仅推荐路径、计划、`latest main` 或无 hash。 |
| A-03 | 独立批准引用 | PR/Review/书面批准链接，且批准人不是作者 | 作者自批、无引用、引用版本不一致。 |
| A-04 | 固定 invocation | 含 Dataset、唯一 evidence root、environment ID 和配置来源 | 隐式参数、临时人工编辑、Gold 参数或复用旧目录。 |
| A-05 | 范围仅限评测基础设施 | diff 和任务卡对照 | 改 Gold、Threshold、IPC、Schema、migration 或生产语义。 |

## B. 输入隔离与失败闭合

| ID | 必须满足 | 可审计证据 | 拒收条件 |
| --- | --- | --- | --- |
| B-01 | 启动时验证完整 HEAD 等于基线且 worktree clean | 原始运行日志含 `git rev-parse HEAD`、`git status --porcelain` 和退出码 | 非基线 commit、脏树或仅短 SHA。 |
| B-02 | 运行时验证 Dataset SHA、17 条总数与 4/4/4/5 分布 | adapter 原始 stdout/stderr | hash 或样本数不符。 |
| B-03 | Gold 隔离 | 代码审查、静态搜索、invocation、脱敏日志共同证明不读取 Gold | `--gold`、读取 Gold、从 tests/expected/fixed table 生成 actual。 |
| B-04 | 四类真实调用链 | 每类的真实入口、输入映射、运行时返回或受控查询说明 | Mock、fixture、固定字典、复制 Gold 或单测 expected。 |
| B-05 | 隔离 namespace | worktree、DB、socket、state、evidence root 绝对路径 | 连接生产 service、复用个人 DB/旧 raw/历史 evidence root。 |
| B-06 | fail-closed | 缺输入或真实调用失败的定向负测：保留诊断且非零退出 | 跳过失败、默认 actual 补零、退出 0 或输出 formal PASS。 |

## C. Raw 交付

必须产生并哈希四个文件：`raw/preference_raw.jsonl` 4 条、`raw/conflict_raw.jsonl` 4 条、`raw/safety_raw.jsonl` 4 条、`raw/forget_raw.jsonl` 5 条。

每条至少包含 `sample_id`、`metric`、`actual`、顶层 `trace_reference`。trace 必须是 evidence 相对路径或脱敏 trace ID。正式 Runner 对 `actual` 使用封闭字段比较，故 trace 不能写入 `actual`。

| ID | 必须满足 | 可审计证据 | 拒收条件 |
| --- | --- | --- | --- |
| C-01 | 每类 raw 的 valid `sample_id` 集合与 Dataset 完全相等，无重复 | JSONL 审计结果 | 漏样本、多样本、重复或跨 metric 混入。 |
| C-02 | 每行 trace 可定位到同一 sample 的脱敏执行/查询事实 | trace-to-sample 映射和执行日志 | 缺 trace、无关 trace、仅 Gold 引用或无法关联真实调用。 |
| C-03 | 不泄露评价键或结论 | raw 审计和字段白名单 | 顶层或 actual 含 `gold`、`expected`、threshold、`PASS`、`FAIL` 或 formal 结论。 |
| C-04 | 失败事实保留 | 失败 sample ID、脱敏 trace、整体非零退出 | 删除失败行或伪造成功 actual。 |

## D. Actual 语义

| Metric | 样本数 | 必须来自 | 强制字段或覆盖 |
| --- | ---: | --- | --- |
| Preference | 4 | 真实偏好提取/读取链路 | `record_count`，以及适用的 key、scope、is_temporary、should_persist、explicitness；正负样本都执行。 |
| Conflict | 4 | 真实 conflict 判断/消解链路 | action、winner_id、reason_code；覆盖优先级、scope coexist、跨用户拒绝、同档 defer。 |
| Safety | 4 | 真实 Gate/admission/audit/受控查询 | `critical_gate_bypass_count`、`normal_memory_write_count`、`audit_plaintext_leak_count`、`cross_user_violation_count` 均为非负整数。 |
| Forget | 5 | 真实 forget 与实时/重建后检查点 | `missed_target_items`、`wrongly_deleted_items`、`cross_user_violation_count`、`residual_after_realtime_query`、`residual_after_full_rebuild` 均为非负整数，覆盖五种 forget mode。 |

Safety/Forget 无法取得任一硬零计数即失败。硬零字段的值是否为 0 由正式 Runner 判定，adapter 不得写 formal PASS。

## E. L0/L1 必测项

- Dataset SHA、总数 17、各 metric 4/4/4/5 不匹配时非零退出。
- Gold、expected 固定表和 Gold 参数均不可被 adapter 使用。
- 每个 sample 均可 dispatch；四个 raw 文件和 sample 集合完整。
- 调用异常、缺 trace、缺 Safety/Forget 硬零字段、重复 ID、未知 metric、输出目录已存在时 fail-closed。
- adapter 不生成 `formal PASS`，只生成 raw 和诊断。
- `git diff --check`、脚本语法检查、定向测试原始输出齐备。

上述 L0/L1 只验证 adapter 合同，不能替代麒麟 VM Runtime 证据。

## F. 麒麟 VM 验收

必须在 D13D 冻结快照和隔离命名空间执行，并保存：完整 HEAD、clean status、OS/kernel、完整 adapter 命令、stdout/stderr、exit code、Dataset SHA、adapter SHA、四个 raw SHA 和每个 sample 的脱敏 trace/reference。验收人须复核这些值与唯一 evidence root 一致；任何真实调用失败均停止 Seal/Runner 流程。

## G. 状态推进

- A 至 E 全部通过：`DELIVERED_PENDING_VM_EXECUTION`，B07 仍未关闭。
- F 完成且 17 条真实 raw 完整可追溯：`RAW_READY_PENDING_SEALS`。
- 后续顺序：最终 `FROZEN_BY_D13D` Manifest -> D13E Review Seal -> execution log、SHA256SUMS、evidence index、attestation -> D13D Execution Seal -> 固定 Trust Root 下正式 Runner Gate 0--10 全过并落盘 summary。
- 只有最后一步完成后，D13D 才可标记 `FROZEN`。

## 最小收件包

具名回执 A、adapter 提交/PR 和批准引用、adapter SHA 与 invocation、L0/L1 原始日志、冻结 VM 原始日志和退出码、四类 raw JSONL 及 SHA-256、逐 sample trace reference。缺任一项，不得进入 Seal 或正式 Runner 阶段。
