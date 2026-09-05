# D13D 正式环境冻结：剩余阻塞项请求单

- 日期：2026-09-05
- 关联：PR #150、`docs/day13/09_d13d_environment_freeze_task_card_20260905.md`、B 轨回执 `PR150_B轨_B06解除回执_20260905.md`
- 被测代码基线：`kylin-mem/main@7242935bee5f230cee0535d5e28dbe1e60a302f6`
- 当前结论：D13B -> D13D Evaluation Contract（B06）已由 B 轨解除；D13D 正式冻结与正式 VM 评测仍为 `NO-GO`。

## 已解除项

| ID | 事项 | 状态 | 依据 |
| --- | --- | --- | --- |
| B06 | D13B 正式评测入口、bundle 输入校验、报告、失败语义与 evidence 可消费性 | B 轨已解除 | B 轨回执确认 CLI、`d9-retrieval-eval-config/v1`、报告 `d13b-retrieval-eval-report/v3` 与 fail-closed 语义已就绪。 |

B06 的解除仅表示不再等待 B 轨补充评测器实现；真实 D13E 输入与 D13D 冻结环境就绪后，仍须由 B 轨在该环境执行正式 CLI。

## 仍存阻塞项

| ID | 阻塞项 | 责任方 | 需要的交付/回执 | 验收与关闭条件 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| B01 | D13E 封存 Candidate/Dataset 与 manifest 未交付 | D13E | 封存集文件、manifest、`dataset_version`、条目数、完整 64 位小写 SHA-256、访问/脱敏说明。 | D13D 在受控位置复算 SHA-256，与 manifest 一致；D13B bundle 中 `dataset_version` 与 `dataset_sha256` 实值绑定。 | P0 |
| B02 | 正式 PASS/FAIL 阈值未冻结 | D13E / 指标批准人 | 书面阈值配置、配置版本和 SHA-256、来源、批准人、批准日期；至少涵盖 Recall 与端到端延迟口径。 | 阈值文件的 hash、来源和批准记录写入环境清单；D13B 不在此前输出正式 PASS/FAIL。 | P0 |
| D13D-01 | VM 身份、快照和资源登记 | D13D | 已记录 VM `Kylin-desktop-neo D12-TDR`、UUID、8 CPU/8 GB、Kylin V11 2603、kernel 和快照 `d13d-pre-7242935-20260905-0858`。 | 已完成本轮准备登记；后续正式部署仍使用该回滚点。 | PREPARED |
| D13D-02 | 正式 user-service 尚未切换到被测基线 | D13D | 当前 `kylin-memory.service` 仍保持旧工作树；候选 `7242935...` 已在隔离 worktree/DB/socket 上启动并核验。 | D13E 输入封存后，按已记录快照与部署流程完成正式 service 切换或经批准的等价部署。 | P0 |
| D13D-03 | 正式评测证据包尚不完整 | D13D | 已建立唯一目录、环境清单、原始 L2 预检日志和 `SHA256SUMS`；没有 D13B raw results/report。 | D13E 输入和阈值解除后补入正式命令、原始结果、报告并更新校验清单与索引。 | P0 |
| D13D-04 | 当前基线与 B 轨回执基线差异 | D13D + B 轨 | 已比较 D13B CLI、`formal_eval.py` 与正式测试入口。 | CLOSED：三个文件在 `053754d...` 与 `7242935...` 的 blob ID 完全相同，结论见 D13D 环境清单。 | CLOSED |
| D13D-05 | 正式 bundle 尚无法填充实值 provenance | D13E + D13D + B 轨 | 对 B06 定义的 bundle 填入实际 dataset/Gold 版本与 hash、`implementation_commit=7242935...`、冻结 environment ID、evidence 路径和统计参数。 | D13B CLI fail-closed 校验通过；不使用占位符；任一字段不一致即该轮无正式指标。 | P0 |

## 请 D13E 回复的最小内容

请按以下字段提供，避免只给口头结论或短 SHA：

```text
dataset_version:
dataset_manifest_path_or_artifact_id:
dataset_sha256:
dataset_record_count:
gold_label_version:
gold_path_or_artifact_id:
gold_sha256:
gold_policy_for_empty_negative_boundary_cases:
official_threshold_config_version:
official_threshold_config_sha256:
threshold_approval_source_and_approver:
data_access_and_redaction_constraints:
```

封存材料不得直接包含在公开 PR 正文或普通日志中；交接路径应受控，D13D 只在环境清单中记录版本、路径标识、条目数和校验和。

## 请 B 轨回复的最小内容

请在 `7242935bee5f230cee0535d5e28dbe1e60a302f6` 上确认：

```text
d13b_contract_verified_on_commit:
formal_eval_module_hash_or_diff_result:
formal_eval_cli_hash_or_diff_result:
test_entrypoint_and_expected_command:
bundle_output_report_filename_contract:
known_blockers_or_incompatibilities:
```

如 D13B 合同在该基线上与回执基线不一致，须在 D13D 部署前说明差异、影响和建议处理方式。

## D13D 后续执行顺序

1. 收到并核验 B01、B02 资料，关闭数据与阈值阻塞。
2. 完成 D13D-04 基线复核；出现差异则停止部署并协调 B 轨。
3. 从记录的干净快照部署 `7242935...`，关闭 D13D-01 和 D13D-02。
4. 建立唯一证据目录并完成 D13D-03。
5. 用实值输入生成 bundle，完成 D13D-05 后才允许 B 轨运行正式 CLI。
6. 所有 P0 项关闭、校验和通过并登记 `evidence/index.yaml` 后，才可将 D13D 标为 `FROZEN`。

## 非目标与状态边界

- 本请求单不要求合并 `kylin-mem/test/d13e-formal-eval@6f55dfefeb248a11a0c9b54ce392762d49c4e065` 作为被测代码；D13E 只交接经批准的输入工件。
- 本请求单不授权修改检索实现、Gold、阈值、IPC、Schema、SQLite 或生产部署策略。
- 在所有 P0 项关闭前，任何 L0/L1、历史 L2 或 CLI 冒烟结果均为 `UNVERIFIED`，不得写为正式 PASS/FAIL 或正式冻结成功。
