# PR #144 证据索引（EVIDENCE_INDEX）

> 本索引登记 PR #144 复审所需的**仓库内不可变原始证据**。固定验证事件 `PR144-V2-L1-R1` 的数据来源为 v2 批次 controller 真实 L1 原始日志，字节原样复制，禁止编辑、截断或改写给后续复跑事件。

## 固定验证事件

| 字段 | 值 |
|---|---|
| Evidence ID | `PR144-V2-L1-R1` |
| Level | L1（组件集成测试，WSL2 环境） |
| 环境 | WSL2 |
| Source Batch | `day12-e-pr144-review-remediation-v2`（controller 批次 state=`BATCH_COMPLETE`，head_sha=`9cfaccd09a665e5b09917b5e8180f8d7966cc1e0`） |
| 完整测试命令 | `python -m pytest -o pythonpath=memory-service memory-service/tests/test_domain_models_d4e.py memory-service/tests/test_knowledge_domain_mapping_d8e.py memory-service/tests/test_candidate_governance_d5e.py memory-service/tests/test_lifecycle_policy_d8e.py memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py memory-service/tests/test_source_admission_d6e.py memory-service/tests/test_multisource_security_adversarial_d6e.py memory-service/tests/test_forget_persistence_d10d.py -q` |
| Tested code snapshot | A = `cc4acf6ec67de50ca6fbb60bb7044cff46f7d4a5`（PR #144 合并前 main-base 代码 snapshot） |
| Python 环境 | 项目 `.venv`（`python -m pytest --version` → `pytest 9.1.0`，L0 记录于 2026-09-04） |
| passed / failed / skipped | 355 / 0 / 0 |
| EXIT_CODE | 0 |
| RESULT | PASS |
| Duration | 21.94s（pytest 输出；与既有历史 duration 10.15s / 8.68s 的语义一致，均为 pytest 输出值） |
| START_TIME | `2026-09-04T21:36:47+08:00`（原始日志字段，非 wall-clock 计算） |
| END_TIME | `2026-09-04T21:37:10+08:00`（原始日志字段，非 wall-clock 计算） |

## 证据文件

| 项 | 值 |
|---|---|
| 原始来源路径（仅本地 provenance） | `.agent-runs/batches/day12-e-pr144-review-remediation-v2/tasks/day12-e-pr144-review-remediation-v2/l1-r1-01.log` |
| 仓库证据路径 | `docs/day12/evidence/pr144/l1-v2-r1.log` |
| SHA256（仓库副本 与 原始来源 一致） | `0b6f937be5a3788f73f8927983455472e4f387f160cd9c6941a7fc81979d89cc` |
| 复制方式 | `cp` 字节原样复制，未做任何编辑；`git diff --no-index` 零差异核验 |

## 证据语义说明

- **固定事件不可改写**：`PR144-V2-L1-R1` 绑定上述原始日志字段与 SHA256，任何后续复跑都必须使用新事件编号（如 `PR144-V2-L1-R2`），不得改写 R1 数据。
- **docs-only 后续提交不改变被测试代码 snapshot**：本批（C=`9cfaccd…`）与后续 docs-only 提交只修改 `docs/` 文档，不触碰 `memory-service/`、`tests/` 或任何运行时代码；被测试代码 snapshot A（`cc4acf6…`）保持不变，因此 R1 对被测试代码 snapshot 的引用对本任务及后续 docs-only 提交仍然有效。
- **证据层级**：L0/L1（WSL2 单测/静态）通过**不构成** Runtime 证据；本任务 `runtime_required=false`，运行验证状态 `RUNTIME_NOT_REQUIRED`，不含 `HOST_VERIFIED`，不含 L2/L3。