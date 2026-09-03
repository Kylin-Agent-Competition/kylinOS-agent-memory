# TD-013 关闭候选审计报告（NonEmptyStr 空串/纯空白拒绝与原值保留）

- **任务**：day12-e-03-td013-closure-audit-v5（D12E TD-013 关闭候选事实审计回写）
- **日期**：2026-09-03
- **分支**：`fix/e-d12-business-schema-drift-remediation`
- **当前 HEAD**：`7434429`（`fix: 收紧E轨非空字符串业务约束`，工作区干净）
- **审计对象**：TD-013「Domain NonEmptyStr 未拒绝纯空白字符串」（`memory-service/domain/common.py`）
- **审计性质**：关闭候选审计（Closure Candidate），**非 Resolved 宣告**。本报告只陈述仓库中已落地并已提交的代码事实与测试定义，不预写本 Task 尚未执行的 L0/L1 结果，不虚构 Runtime 证据或 Reviewer 签署。

---

## 0、四层状态分离说明

本报告按以下四层分别陈述，各层互不替代：

| 层 | 状态标记 | 含义 |
|----|----------|------|
| 代码事实层 | `CODE_VERIFIED` | 实现已落地并已提交（commit `7434429`），引用文件与行号可核对 |
| 测试定义层 | `TEST_DEFINED` | 测试用例已定义并已提交（同 commit），覆盖正向/负向与逐字保留断言；**只陈述定义存在，不写运行数值** |
| Controller Gate 层 | `GATE_PENDING` | 本 Task 的 L0/L1 验收命令由 Controller 在 Implementer 返回后独立执行，结果另行记录 |
| Reviewer 关闭层 | `REVIEW_PENDING` | D 主审（周子腾）尚未签署，状态为 Closure Candidate / In Progress pending D Reviewer，**不得标记 Resolved** |

---

## 1、代码事实层（CODE_VERIFIED）

实现文件：`memory-service/domain/common.py`（commit `7434429`，当前 HEAD）。

| TD-013 关闭条件输入 | 实现事实 | 引用 |
|---------------------|----------|------|
| 空串（`""`） | `NonEmptyStr = Annotated[str, Field(min_length=1), AfterValidator(_ensure_non_blank)]`：`min_length=1` 在 Pydantic 层拒绝空串；`_ensure_non_blank` 对 `""` 执行 `strip()` 后为空，抛 `ValueError` | `common.py` 第 51 行、第 38–45 行 |
| 纯空白（空格/Tab/换行/CR/混合/全角空格） | `_ensure_non_blank`：`if not value.strip(): raise ValueError("string must not be empty or whitespace only")`。`str.strip()` 口径覆盖空格、`\t`、`\n`、`\r`、混合空白与全角空格 `\u3000` | `common.py` 第 43–44 行 |
| 正常字符串原值保留（不 strip） | `_ensure_non_blank` 仅做空白判定，命中有效字符后 `return value` 原样返回，不做 `strip()`；docstring 明确「含有效字符的原值原样保留，不做 strip」 | `common.py` 第 38–45 行、第 17–18 行 |
| NonEmptyIdList 元素级继承 | `NonEmptyIdList = Annotated[List[NonEmptyStr], Field(min_length=1)]`：至少 1 个元素，且每个元素复用 `NonEmptyStr` 约束（空串/纯空白元素拒绝，含有效字符元素原值保留） | `common.py` 第 57 行 |

语义基线：`docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md`（commit `7b92490` 创建，158 行）为 E 轨业务语义层统一权威基线（Canonical Business Schema v1，`FROZEN`，限 E 轨职责范围）。NonEmptyStr 作为 E Domain 公共约束类型，承载该冻结语义层下业务字段「有效非空文本」的构造边界；本审计不声称该冻结文档单独冻结了 NonEmptyStr 的字符串校验细节，仅将其作为业务语义权威层引用。

**结论**：TD-013 的代码能力（空串拒绝、纯空白拒绝、原值保留、NonEmptyIdList 元素继承）已在当前分支落地并提交，标记 `CODE_VERIFIED`。

---

## 2、测试定义层（TEST_DEFINED）

测试文件：`memory-service/tests/test_domain_models_d4e.py`（commit `7434429`，第 661–745 行，共 6 组用例）。以下只陈述测试**定义**及其参数化输入与断言意图，不包含任何运行结果数值。

| 测试函数 | 行号 | 参数化输入 / 覆盖 | 断言意图 |
|----------|------|-------------------|----------|
| `test_non_empty_str_rejects_empty_and_whitespace_only` | 664–680 | `""`、`" "`、`"\t"`、`"\n"`、`"\r"`、`" \t\n\r "`、`"\u3000"`（全角空格）、`" \u3000\t "` | 空串与纯空白一律 `ValidationError`（负向） |
| `test_non_empty_str_preserves_original_value` | 683–695 | `"pref_d4e_01"`、`"  padded  "`、`"\tleading-tab"`、`"trailing-newline\n"`、`" 中 文 空 格 内 部 "` | 含有效字符的输入通过，且返回值与输入**逐字相等**（不 strip） |
| `test_non_empty_id_list_rejects_whitespace_only_element` | 698–703 | `["pref_d4e_01", "  "]`、`["\t"]` | NonEmptyIdList 纯空白元素拒绝（元素级继承） |
| `test_non_empty_id_list_preserves_padded_element` | 706–709 | `["  pref_d4e_01  "]` | 含有效字符的元素原值保留 |
| `test_domain_rejects_whitespace_only_non_empty_str_field` | 712–727 | Preference/Knowledge/Conflict/ForgetPlan 四模型 id 字段（`preference_id`/`knowledge_id`/`conflict_id`/`forget_plan_id`）传 `" "`、`"\t"`、`"\n"`、`" \t\n "` | 四模型 NonEmptyStr 字段传纯空白 → `ValidationError` |
| `test_domain_preserves_padded_non_empty_str_field` | 730–745 | 四模型字段（`preference_key`/`content_summary`/`conflict_summary`/`target_selector`）传 `"  padded-value  "` | 构造成功且字段值逐字保留 |

测试纪律（文件头第 21–24 行）：不使用 Mock、skip、xfail 或弱化断言；测试数据仅使用合成用户 ID、合成事件 ID 与脱敏内容。

**结论**：TD-013 的正向/负向测试定义与「原值逐字保留」断言已存在并已提交，标记 `TEST_DEFINED`。本 Task 不新增、不修改任何测试。

---

## 3、Controller Gate 层（GATE_PENDING）

本 Task 的验收命令由 Controller 在 Implementer 返回后**独立执行**，结果按 `.local-agent-workflow/rules/runtime-validation.md` 证据规则另行记录并归档。本报告**不声称执行结果、不预写 PASS 数值**。

| Gate | 命令 | 说明 |
|------|------|------|
| L0 | `python3 -m pytest --version` | pytest 可达性冒烟 |
| L1 | `python3 -m pytest -o pythonpath=memory-service memory-service/tests/test_domain_models_d4e.py -q` | 覆盖 TD-013 六组用例（验证已提交测试定义可执行） |
| L2/L3 | 无（`runtime_required=false`，`runtime_commands=[]`） | 不适用；NonEmptyStr 为纯 Pydantic 约束，无银河麒麟系统能力依赖，本 Task 不产生也不虚构任何 Runtime 证据（`RUNTIME_NOT_REQUIRED`） |

---

## 4、Reviewer 关闭层（REVIEW_PENDING）

- **当前状态**：Closure Candidate / In Progress **pending D Reviewer**（周子腾，D 主审）。
- **未完成事项**：
  1. 本 Task 的 L0/L1 验收 Gate 尚未由 Controller 执行（结果未产生）；
  2. D 主审尚未对关闭候选进行正式确认；
  3. 登记表状态推进到 `Resolved` 需要 D Reviewer 确认验收标准达成（`代码合并 ≠ 技术债关闭`，见登记表管理规则第 3 条）。
- **明确声明**：本报告**不标记 Resolved**，不虚构 Reviewer 签署，不把 WSL 测试描述为 `HOST_VERIFIED`。

---

## 5、明确未完成 / 未验证事项

1. 本 Task 的 L0/L1 命令尚未执行（由 Controller 在 Implementer 返回后独立执行并记录结果）。
2. D Reviewer（周子腾）对 TD-013 关闭候选的正式确认尚未取得。
3. 本报告不包含任何 Runtime 证据（`RUNTIME_NOT_REQUIRED`），也不包含任何虚构的测试运行数值或日志。

---

## 6、结论

TD-013 的**代码能力与测试定义**已在当前分支落地并提交（commit `7434429`，HEAD 一致，工作区干净），技术条件已具备关闭候选审计；业务流程上剩余 Controller Gate 执行与 D Reviewer 正式确认。登记表状态由 `Open` 推进为 `In Progress`（Closure Candidate pending D Reviewer），**不得直接标记 Resolved**。