# D13D Draft：阻塞项与开工条件

- Draft 分支：`docs/d13d-environment-freeze`
- 被测代码基线：`kylin-mem/main@7242935bee5f230cee0535d5e28dbe1e60a302f6`
- 状态：`PREPARED`。本记录不是环境冻结成功证据，也不发布正式量化结论。
- 关联任务卡：`docs/day13/09_d13d_environment_freeze_task_card_20260905.md`

## 阻塞项

| ID | 阻塞项 | 责任方 | 解除条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| D13D-B01 | D13E 封存测试集未交付 | D13E | 提供正式测试集版本、完整 SHA-256、条目数和受控访问说明。 | BLOCKED |
| D13D-B02 | D13E Gold 与官方阈值未交付 | D13E | 提供 Gold 判定键版本、完整 SHA-256、空 Gold/负例/边界策略及 OFFICIAL 阈值来源。 | BLOCKED |
| D13D-B03 | 正式 VM 快照与资源尚未为本轮登记 | D13D | 记录 VM 名称/UUID、银河麒麟版本、kernel、CPU/RAM/磁盘、快照名与时间；从该快照创建隔离工作树。 | BLOCKED |
| D13D-B04 | 基线尚未部署并在 VM 核验 | D13D | VM 内 `HEAD` 等于 `7242935bee5f230cee0535d5e28dbe1e60a302f6`，工作树干净，服务单元/依赖/路径已采集。 | BLOCKED |
| D13D-B05 | 本轮证据目录与校验清单尚未生成 | D13D | 创建唯一 `evidence/l2-kylin-vm/d13d_<UTC_RUN_ID>/`，写入环境清单、命令输出和 `SHA256SUMS`。 | BLOCKED |
| D13D-B06 | D13B -> D13D 正式 Evaluation Contract | B 轨 | B 轨已提供正式 CLI、输入/输出合同和 fail-closed 语义；真实输入绑定随 D13E/B01、B02 与 D13D 环境冻结执行。 | B 轨已解除 |

## 开工条件

允许开始 VM 部署与只读环境采集，必须同时满足：

1. 使用上述完整 `tested_commit` 创建隔离 VM 工作树；不得使用当前开发树或 D13E 分支替代。
2. 已保存部署前 VM 状态和回滚点，且不覆盖系统 SDK、系统库、模型目录或既有快照。
3. 所有命令、输出和退出码写入唯一的 D13D 证据目录；日志不记录封存样本正文、用户原文或任何凭据。

允许开始正式 D13B 评测，必须额外满足：

1. D13D-B01 至 D13D-B06 全部关闭，并在 `environment_freeze.json` 写入 `freeze_status=FROZEN`。
2. 评测报告中的 `tested_commit`、数据集/Gold/配置哈希与环境清单逐项一致。
3. `SHA256SUMS` 验证通过，且 `evidence/index.yaml` 可按 1.1 契约登记。

## 不可绕过的边界

- 不合并 `kylin-mem/test/d13e-formal-eval@6f55dfefeb248a11a0c9b54ce392762d49c4e065` 作为被测代码；该分支含封存数据之外的未合并跨层变更。
- 不因阻塞项存在而修改 Gold、阈值、评测样本或生产检索实现。
- 不以 WSL/L0/L1、旧 commit 或历史 VM 日志替代本次基线的 L2 证据。

## Draft 退出条件

本 Draft PR 仅在任务卡、阻塞项和开工门禁被确认后可合并。合并本 PR 不等同 D13D `FROZEN`；实际冻结证据必须在后续同分支或关联 PR 中按任务卡生成和审核。
