# Day6E 多源开发集 v1（D6_MULTISOURCE_DEVSET_V1）

- **版本**：v1
- **状态**：`DEVSET_V1`（开发集，**非 Gold、非回归集、非封存测试集**）
- **阶段定位**：Day6 / E 轨道 / 可为后续偏好、知识、检索与正式 Gold Label 评测提供可复用样本的错误归因基础
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **配套文件**：
  - `D6_MULTISOURCE_DEVSET_V1.jsonl`（96 条合成/脱敏样本）
  - `D6_MULTISOURCE_ERROR_TAXONOMY_V1.md`（统一错误分类表）
  - `test_d6_multisource_devset.py`（开发集验证测试）
- **任务性质声明**：本任务为纯数据集 + 文档 + 测试任务（`runtime_required=false`、`runtime_commands=[]`），不产生 Runtime 结论，不更新 `evidence/index.yaml`。

---

## 一、用途

本开发集为以下评测方向提供**可复用样本与错误归因基础**：

1. **偏好评测**（M1 偏好提取准确率样本层）；
2. **知识评测**（M2/M3 知识检索召回率与响应时间的查询语义关联样本层）；
3. **冲突评测**（M4 冲突处理正确率的候选输入）；
4. **多源准入评测**（Day6E Task1 `SourceAdmissionPolicy` 三值决策语义对齐）；
5. **安全对抗评测**（Day6E Task2 十类攻击族语义对齐）。

本开发集**不是**最终评测结果、不含任何分数或 PASS 结论；评测结果的取得依赖后续实现、真实环境与正式评测执行。

## 二、数据来源声明

- 全部样本为**合成/脱敏**内容，`input_case` 使用明确虚构占位标记词（`虚构`、`测试样本`、`攻击样本`、`PLACEHOLDER`、`fake`、`demo`、`REDACTED` 等）。
- **不含**任何真实用户数据、真实账户、手机号、身份证、私钥、API Key、Token 或密码。
- 用户 ID 使用合成格式 `user_demo_d6e_*` / `user_demo_d6e` / `user_demo_d6e_b`，均为虚构。
- 凭据占位格式对齐既有测试：`sk-demo-PLACEHOLDER-*`、`api_key=fake-PLACEHOLDER-*`、`password=PLACEHOLDER-*`、`token=PLACEHOLDER-*`。
- 手机号使用明显虚构格式（如 `19900000000`）；身份证号使用明显虚构格式（如 `000000000000000000`）。
- **禁止**出现 `sk-live-*`、`sk-prod-*`、`-----BEGIN RSA PRIVATE KEY-----` 等真实凭据模式。

## 三、非 Gold 声明

本开发集 **`DEVSET_V1` 定位**：

- **不是**最终 Gold Label 集；
- **不是**回归集；
- **不是**封存测试集；
- 尚未锁定 SHA-256 哈希；
- `annotation_status` 仅使用 `candidate` / `pending_review`，**不含** `reviewed` / `sealed`。

后续必须经过**人工双人复核、切分与封存**流程（见「九、后续流程」）后，方可升级为正式 Gold / 回归 / 封存子集。在此之前，不得把本开发集描述为最终 Gold、回归集或封存测试集。

## 四、字段规范

每条 JSONL 记录为一行为合法 JSON 对象，必须包含以下**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `sample_id` | string | 全局唯一、稳定、非空；格式 `d6-{tr\|bc\|mc}-{NNN}`（tr=tool_result，bc=behavior_candidate，mc=manual_config） | 样本唯一标识 |
| `source_family` | string enum | ∈ {`tool_result`, `behavior_candidate`, `manual_config`} | 数据源分类（**评测分类字段，非生产 `SourceType` 契约**） |
| `sample_category` | string enum | ∈ {`normal`, `boundary`, `error`, `security_attack`} | 样本类别 |
| `input_case` | string | 非空 | 人类可读的测试场景描述（合成/脱敏） |
| `expected_gate` | string enum | ∈ {`allow_extraction`, `audit_only`, `reject`} | 对齐 `SourceAdmissionDecision` |
| `expected_should_extract` | boolean | true/false | 是否应进入抽取 |
| `expected_memory_kind` | string enum | ∈ {`none`, `preference`, `success_knowledge`, `failure_experience`, `all`} | 对齐 `ExtractionKind`；`none`=不抽取，`all`=三种全开 |
| `expected_security_decision` | string enum | ∈ {`allow`, `deny`, `audit_only`, `conditional`} | 对齐 G0-E 案例安全动作语义 |
| `expected_error_codes` | array[string] | 可为空数组；每个元素必须能在 `D6_MULTISOURCE_ERROR_TAXONOMY_V1.md` 找到定义 | 错误归因（引用错误分类表） |
| `attack_tags` | array[string] | 可为空数组；非 `security_attack` 样本必须为空数组 `[]` | 攻击类型标签（见「五、枚举定义」） |
| `annotation_status` | string enum | ∈ {`candidate`, `pending_review`} | 标注状态；DEVSET_V1 不含 `reviewed`/`sealed` |
| `notes` | string | 可为空字符串 | 备注 |

**条件字段**：

| 字段 | 适用条件 | 类型 | 约束 |
|------|----------|------|------|
| `tool_execution_status` | `source_family=tool_result` 时必须存在 | string enum | ∈ {`success`, `failed`, `cancelled`, `timeout`, `partial`, `unchecked_payload`} |
| `mapping_status` | `source_family=behavior_candidate` 时必须存在 | string enum | ∈ {`PENDING_C_CONFIRMATION`} |

## 五、枚举定义

| 字段 | 合法值集合 |
|------|-----------|
| `source_family` | `tool_result`、`behavior_candidate`、`manual_config` |
| `sample_category` | `normal`、`boundary`、`error`、`security_attack` |
| `expected_gate` | `allow_extraction`、`audit_only`、`reject` |
| `expected_memory_kind` | `none`、`preference`、`success_knowledge`、`failure_experience`、`all` |
| `expected_security_decision` | `allow`、`deny`、`audit_only`、`conditional` |
| `annotation_status` | `candidate`、`pending_review` |
| `mapping_status` | `PENDING_C_CONFIRMATION` |
| `tool_execution_status` | `success`、`failed`、`cancelled`、`timeout`、`partial`、`unchecked_payload` |
| `attack_tags` | `prompt_injection`、`sensitive_leak`、`cross_user`、`tool_status_injection`、`identity_injection`、`provenance_injection`、`memory_status_injection`、`ignored_bypass`、`payload_bypass`、`temporary_to_persistent`、`schema_violation`、`config_conflict` |

`attack_tags` 语义对齐 Day6E Task2 十类攻击族（`ignored_bypass`、`schema_violation`、`config_conflict` 为本开发集扩展标签，用于标注对应攻击/边界语义，不代表已新增生产枚举）。

## 六、数据源分类与行为候选映射状态说明

- `source_family` 是**开发集评测分类字段**，**不是** `MemorySourceEvent.source_type` 生产契约。
- 生产契约 `SourceType` 当前七值：`chat` / `tool_result` / `manual_config` / `recollect` / `file` / `meeting` / `voice`（`memory-service/pipeline/schemas.py`），**不包含 `behavior`**。
- **behavior_candidate 到 `MemorySourceEvent.source_type` 的正式映射尚未由 C 轨冻结**。因此：
  - 所有 `behavior_candidate` 样本的 `mapping_status` **必须**为 `PENDING_C_CONFIRMATION`；
  - 本开发集**不新增** `behavior` `SourceType`、**不伪造**已冻结映射字段；
  - 任何开发集或本 README 中的 behavior 语义都**不代表**生产契约已冻结。

## 七、样本分布

| source_family | 本版条数 | sample_category 覆盖 | 附加覆盖 |
|---------------|----------|----------------------|----------|
| tool_result | 32 | normal / boundary / error / security_attack 各 ≥1 | `tool_execution_status` 覆盖 success / failed / cancelled / timeout / partial / unchecked_payload 各 ≥1 |
| behavior_candidate | 32 | normal / boundary / error / security_attack 各 ≥1 | 全部 `mapping_status=PENDING_C_CONFIRMATION` |
| manual_config | 32 | normal / boundary / error / security_attack 各 ≥1 | 覆盖长期偏好 / 临时设置 / 安全相关配置 / 敏感内容 / 冲突非法值 |
| **总计** | **96（≥90）** | — | — |

## 八、敏感占位约束

1. 所有敏感样本必须使用明显虚构/测试占位模式，标记词包括：`PLACEHOLDER`、`fake`、`demo`、`REDACTED`、`DUMMY`、`虚构`、`测试用`。
2. 凭据占位格式：`sk-demo-PLACEHOLDER-*`、`api_key=fake-PLACEHOLDER-*`、`password=PLACEHOLDER-*`、`token=PLACEHOLDER-*`。
3. 手机号使用 `19900000000` 等明显虚构格式；身份证号使用 `000000000000000000` 明显虚构格式。
4. **禁止**出现：`sk-live-*`、`sk-prod-*`、`-----BEGIN RSA PRIVATE KEY-----` 等真实凭据模式。
5. 用户 ID 使用合成格式 `user_demo_d6e*`。

## 九、后续流程

1. **人工双人复核**（对齐标注规范 §4.1）：标注人 A 初标 → 标注人 B 复核 → 争议提交 Reviewer（D/E）裁决；`annotation_status` 从 `candidate`/`pending_review` 升级为 `reviewed`。
2. **切分**（对齐 D3 规范 TD-07，比例待 B/E 确认）：开发集 / 回归集 / 封存集。
3. **封存**（对齐标注规范第七章与 D3 规范 TD-08）：对封存子集锁定 SHA-256 哈希，锁定后禁止修改。
4. 以上步骤完成后，由对应轨道另行建立正式 Gold / 回归 / 封存版本（独立任务），**本 `DEVSET_V1` 不自我宣称已完成上述步骤**。

## 十、与 D3 Gold Label 规范的关系

- 本开发集是 D3 `D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md` 定义的 Gold Label 判定规则在**样本层的实践载体**（候选），**不修改 D3 规范**。
- 本开发集的 `expected_*` 字段语义对齐 D3 规范的 Preference / Knowledge / Conflict Gold Label 判定规则、Day3 安全验收契约（SEC-*）与 Day6E Task1/Task2 的三值准入语义。
- 本开发集不是 D3 规范本身，也不替代 D3 规范的任何冻结流程。

## 十一、测试

`test_d6_multisource_devset.py` 自包含（仅标准库 + pytest，不导入 memory-service），校验：

- JSONL 逐行合法 JSON、必填字段完整、`sample_id` 全局唯一且格式合法；
- 总样本 ≥ 90，三类各 ≥ 30，每类四类别覆盖；
- 全部枚举合法（source_family / sample_category / expected_gate / expected_memory_kind / expected_security_decision / annotation_status / tool_execution_status / mapping_status）；
- `expected_error_codes` 中每个元素在 `D6_MULTISOURCE_ERROR_TAXONOMY_V1.md` 中均有定义；
- behavior 映射状态为 `PENDING_C_CONFIRMATION` 且未被冻结为共享 `SourceType`；
- Tool Result 状态覆盖六类；
- 非攻击样本 `attack_tags` 为空数组；
- 敏感样本使用占位标记、全文无真实凭据模式；
- 非法 JSON / 重复 sample_id / 缺字段 / 未知 error code / 数量不足时测试**真实失败**（硬断言、无 skip、无 xfail、无吞异常、无自动修正）。

## 十二、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-24 | 初稿：建立 `DEVSET_V1` 多源开发集（96 条，tool_result / behavior_candidate / manual_config 各 32 条），配套错误分类表与验证测试；行为候选映射全部 `PENDING_C_CONFIRMATION`，不新增共享 `SourceType`。 | E 轨道 |