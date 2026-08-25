# PR #58 Day7E —— 正式审查结果（含麒麟 VM L2/L3 独立验证）

- **审查对象**：PR #58（分支 `feat/e-d7-preference-business-semantics`，4 commits：`acd794c`/`f1f1286`/`3dae2e2`/`1ba5e6b`）
- **基线 Commit**：`87dac64`（`kylin/main` HEAD）
- **Diff 规模**：6 文件，+2974 行（全为新增）
- **审查日期**：2026-08-24
- **审查性质**：非作者 Reviewer 独立审查（代码审查 + 麒麟 VM L2/L3 独立验证）
- **对照文档（实际使用）**：
  - `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`（v1 / `CANDIDATE_FOR_FREEZE`）
  - `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`
  - `docs/baseline/v2-20260816/05_capability_boundary_reevaluation_20260816.md`（能力边界 v1.3）
  - 随附 skill 基线 01/02（v1.1）仅作能力分级与门禁规则引用
  - 注：四份基线 DOCX（01~04）均未入库，故以上述仓库内机器可读文档为执行口径

---

## 一、总体结论

| 维度 | 结论 |
|------|------|
| **E 轨业务策略代码（D7E-01/02/03）** | **PASS_WITH_DEBT**（L1 本地 100 passed；无假实现、无红线违反；2 Medium/Low 债务 + 1 文档缺口） |
| **C 轨 QML 偏好 UI（L2-C）** | **RUNTIME_UNVERIFIED**（未实现，无验证对象） |
| **D 轨版本持久化（L2-D）** | **RUNTIME_UNVERIFIED**（未实现，无验证对象） |
| **L3 干净镜像发布验证** | **RUNTIME_UNVERIFIED**（无发布候选，无法执行） |

> **综合判定**：PR #58 本身**可合并**（其交付物为 E 轨纯业务策略 + 验收规范候选文档，均如实标注未完成项，不虚标 C/D 轨已实现）。但验收规范 `day7-e-ui-version-acceptance-v1.md` **不得冻结为团队基线**，须待 C/D 轨实现并在麒麟 VM 完成 L2/L3 验证后方可生效。

---

## 二、E 轨业务策略代码审查结果

### 2.1 检查清单核对（摘要）

| 检查项 | 结果 |
|--------|------|
| 假实现 / 降级正确性 | ✅ 无 Mock、无固定返回值、无吞异常、无 TODO/FIXME；判定 fail-closed 首个命中即返回 |
| 架构红线（原文隔离 / 真源 / 异步写入） | ✅ 只读结构化字段，不读 `evidence` 正文；不写库、不改 `current_version`（`NOT_PERSISTENCE`） |
| 安全（跨用户隔离 / 密钥） | ✅ `plan_preference`/`plan_rollback` 均有 `rejected_cross_user` 防御；reason_code 不拼接密钥 |
| 复用契约 identity | ✅ 复用 `PreferenceCandidate`/`Preference`/`MemoryStatus`，无第二套平行 Schema |
| 门禁守护 | ✅ 新类型未加入 `service.__all__` |
| 测试与证据 | ✅ L1 100 passed；纯业务策略无需 L2；测试纪律明确"无 Mock/skip/xfail" |

### 2.2 问题清单

| # | 位置 | 严重度 | 类型 | 问题 | 处置建议 |
|---|---|---|---|---|---|
| 1 | `preference_version_policy.py:136`（`scope: str`） | Medium | Risk | `scope` 未做五值枚举校验，非法 scope 静默落到 CREATE 而非 REJECTED fail-closed | 改 `PreferenceScope` 枚举或加 validator，补非法 scope 负向测试 |
| 2 | `preference_version_policy.py:169`（`coexist_with_scopes: List[str] = []`） | Low | 建议 | 可变默认值（Pydantic 深拷贝当前安全，属反模式） | 改 `Field(default_factory=list)` |
| 3 | PR 描述 | Low | 建议 | 仓库内缺 Day7E 独立 PR 描述（`docs/day7/02_pr_description.md` 仍为 PR #36 旧内容） | 补 Day7E PR 描述 |

---

## 三、麒麟 VM L2/L3 独立验证结果

### 3.1 证据与完整性

| 证据文件 | SHA256（已复核一致） |
|----------|----------------------|
| `day7-l2l3-verification-report.md` | `cd5778df…f01350` ✅ |
| `day7-l2l3-vm-verification.log` | `2e86ee5e…b6cf7` ✅ |
| `day7-l2l3-vm-deployed.log` | `f571259d…24159c3` ✅ |
| `day7-l2l3-vm-db-schema.log` | `b82dd936…b6129fb` ✅ |
| `_verify.py` / `_verify2.py` / `_verify3.py` | 三者均与 `MANIFEST.sha256` 一致 ✅ |

- 验证方式：paramiko 连接 `127.0.0.1:2222`，凭证取自环境变量 `KYLIN_VM_PASSWORD`（无硬编码）✅
- 合规声明：零冒充，未以 L1 pytest / 截图 / Mock 冒充宿主验收 ✅

### 3.2 实测事实

| 核查项 | 实测结果 |
|--------|----------|
| VM OS | 银河麒麟桌面 V11 2603 Release x86_64 |
| VM 部署仓库 HEAD | `ed9949c`（`feat/d4d-ipc-db-outbox`，D4D 提交，**非 Day7E 分支**） |
| Day7E 策略代码 | `memory-service/service/` 仅 `candidate_governance.py`/`contracts.py`/`__init__.py`，**无 `preference_version_policy.py`/`preference_business_policy.py`** |
| `current_version` 指针 | `db/schema.py` `memory_entries` 表**无该列**；`repositories.py` 中 `current_version: int` 仅为乐观锁 `version` 的函数参数，非持久化指针字段 |
| `previous_version_id` 链 | schema 与落盘 DB 均**无** |
| 乐观锁 `version` | 存在（`memory_entries.version INTEGER NOT NULL`，D4d 乐观锁，default 1），但并发冲突检测/失败处理未实现 |
| 偏好版本语义落库 | D4d 仅通用 `memory_entries` 表，无偏好版本链持久化逻辑 |
| QML 生产文件 | 无（`memory-client/` 仅 README；VM 无 `*.qml` 偏好/记忆生产文件） |
| L3 发布候选 | 无（D/C 轨未实现，无法执行干净快照全链路） |

### 3.3 逐条结论

- **L2-D-01~08**：全部 `⬜ RUNTIME_UNVERIFIED`（D 轨版本持久化未实现）。
- **L2-C-01~07**：全部 `⬜ RUNTIME_UNVERIFIED`（C 轨 QML UI 未实现）。
- **L3-01~04**：全部 `⬜ RUNTIME_UNVERIFIED`（无发布候选）。

> 本验证**不产生任何 `HOST_VERIFIED`**，全部条目保持 `RUNTIME_UNVERIFIED`。

---

## 四、待人工裁决项

- 无文档冲突、无证据不足需裁决项。

---

## 五、后续行动项

| 责任轨道 | 行动 |
|----------|------|
| D | 实现 `current_version` 指针 + `previous_version_id` 版本链 + 五动作（CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK）落库 + 跨用户隔离 + 并发乐观锁冲突处理；完成后在麒麟 VM 补 L2-D 证据 |
| C | 实现 QML 偏好 UI（历史列表/修改/回滚/临时长期区分/多 scope/跨用户隔离）；完成后在麒麟 VM 补 L2-C 证据 |
| C/D | 完成 L3 干净快照全链路验证 |
| E | 收敛问题 #1（scope 枚举校验）、#2（可变默认值）；（可选）补 Day7E PR 描述 |

完成 L2/L3 并回写 `evidence/index.yaml` 与能力矩阵后，验收规范方可进入冻结流程。

---

## 六、Post-review Closure Addendum（审查后收敛补记）

> 本节为**追加的收敛补记**，属审查基准（2026-08-24，首次正式审查，L1 本地 100 passed）之后的后续事实记录。**不修改、不重写上文第一至五节原始审查正文（L1–L107）**，补记时点事实与原始审查时点并存、互不覆盖。

### 6.1 问题 #1 / #2 代码收敛

PR #58 正式审查问题 #1（Medium，scope fail-closed）与 #2（Low，default_factory / identity）已通过代码 + 测试收敛：

| 审查问题 | 收敛提交 | 收敛方式 | 新增测试 |
|---|---|---|---|
| #1 scope fail-closed | `b883516` | `PreferenceVersionIntent.scope` 复用 `PreferenceScope` 枚举（`preference_version_policy.py`），非法 / 空 scope 在构造阶段即被 Pydantic 拒绝 | `test_invalid_scope_rejected_at_construction`、`test_empty_scope_rejected_at_construction`、`test_intent_scope_reuses_preference_scope_enum` |
| #2 default_factory / identity Low | `b883516` | `PreferenceVersionPlan.coexist_with_scopes` 改为 `Field(default_factory=list)`，默认实例列表互相独立 | `test_coexist_with_scopes_default_independent_instances` |

> 注：`b883516` 为本任务输入提供的收敛提交标识；如需在 Git 历史中复核该 SHA，须由具备 git 读取权限的 Agent 另行确认。此处补记的通过判定依据为 Reviewer 独立复测结论（见 6.2）。

### 6.2 passed 数量时点区分

首次 100 passed 与后续 Reviewer 独立复测 104 passed **属于不同时间点**，二者均保留，且后续复测结果不覆盖首次审查时点事实：

| 时点 | 时间 | 内容 | 说明 |
|---|---|---|---|
| 首次正式审查 | 2026-08-24 | L1 本地 **100 passed** | 原始审查正文第五节之前记录的事实；此时问题 #1/#2 尚未收敛 |
| Reviewer 独立复测 | `b883516` 收敛 #1/#2 之后 | L1 本地 **104 passed**（新增 4 个 #1/#2 测试） | 收敛补记时点的事实，由 Reviewer 独立复测得出 |

- 若此后作者回归测试的 passed 数量再发生变化，**不得覆盖 Reviewer 独立复测 104 passed 这一已记录事实**，应作为新的独立时点另行记录。

### 6.3 本轮 identity Low 修复状态

- 本轮 `identity` 相关 Low（问题 #2，`default_factory` 可变默认值 / 实例 identity 独立性）已通过 `Field(default_factory=list)` 收敛，相关测试为 `test_coexist_with_scopes_default_independent_instances`。
- **该修复仍待非作者 Reviewer 复核确认**，尚未标记为最终关闭。
- 已登记 **TD-018**（Technical Debt / Low / In Progress，见 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`），待非作者 Reviewer 确认后关闭。

### 6.4 C/D/L2/L3 与 Acceptance Spec 状态（保持诚实）

本补记仅为文档层面的收敛治理，**未改变任何真实 Runtime 验证状态**：

- **C 轨 QML 偏好 UI**：`PENDING_INTEGRATION` / `RUNTIME_UNVERIFIED`（未实现，无验证对象）——保持不变。
- **D 轨版本持久化**：`PENDING_INTEGRATION` / `RUNTIME_UNVERIFIED`（未实现，无验证对象）——保持不变。
- **L2-C / L2-D / L3**：全部条目仍为 `RUNTIME_UNVERIFIED`（无发布候选 / 未实现）——保持不变。
- **Acceptance Spec**（`day7-e-ui-version-acceptance-v1.md`）：仍为 `PENDING_INTEGRATION`，**不冻结**。
- **本补记不将任何 `RUNTIME_UNVERIFIED` 改为 `HOST_VERIFIED` / `PASS`** 的表述。

本补记仅追加收敛事实与 TD-018 登记，不产生任何真实宿主验证证据，不代行 Reviewer 最终批准。
