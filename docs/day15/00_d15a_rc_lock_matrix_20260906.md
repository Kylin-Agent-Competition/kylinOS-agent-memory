# D15A A 轨发布候选锁定矩阵与状态基线（as-of 2026-09-06）

> **性质声明**：本文件为 A 轨（D15A）发布候选的**锁点程序 / 交付物身份 / 状态机 /
> 版本一致性检查程序**的文档基线，并以 as-of 快照方式如实记录 2026-09-06 的仓库事实。
> 本文件**不执行、不宣称任何正式锁**；A15-1/A15-2/A15-3 三项锁点当前均只能为
> `WAITING_PREREQ`。任何正式锁前**必须**按 §4 刷新规则重跑 `git rev-parse HEAD`、
> `git status --porcelain` 与 `git diff --name-only`（指定基线）做三分类复核，
> 快照过期时不得直接引用本节事实。本矩阵线自身状态独立标记为
> `DOCUMENTATION_PREPARATION / READY_FOR_REVIEW`，**不得**与其他三行混标。

---

## 1. 目的与范围

### 1.1 目的

为 D15A A 轨发布候选（Release Candidate）建立可审计的锁定矩阵：

- **锁点程序**：定义 A15-1 / A15-2 / A15-3 三个正式锁点的内容、前置条件与验收口径；
- **交付物身份**：明确 A 轨正式交付物身份（发布包内 `kylin_embedding*.so`），
  并排除 wheel / Kaiming 等非本轨交付物；
- **状态机**：约束允许使用的状态词与禁止出现的越级结论；
- **版本一致性检查程序**：定义正式锁时对最终包 `VERSION` / `manifest.package_version`
  / `EXPECT_*` / `source_commit` 的 fail-closed 检查等式；
- **仓库事实基线**：如实记录当前仓库、契约与 evidence 状态（as-of 2026-09-06）。

### 1.2 范围边界

- 本 Task（PR #164 对应的 D15A 锁定矩阵与确定性守卫）涉及**三个实际文件**：
  - `docs/day15/00_d15a_rc_lock_matrix_20260906.md`（本文件）；
  - `docs/day15/test_d15a_rc_lock_matrix.py`（配套确定性守卫测试）；
  - `.github/workflows/baseline-check.yml`（既有 CI workflow，见下）。
- 三文件中的 code 变更仅限上述守卫测试与本矩阵文档（module=docs）；`.github/workflows/
  baseline-check.yml` **不改动其结构**——仅把 `docs/day15/test_d15a_rc_lock_matrix.py`
  守卫接入既有 `d14a-packaging-provenance` job 的 pytest 命令（在 `docs/day14/
  test_d14a_release_provenance.py` 之后追加一行），在此 job 上**不新增 job / 不新增
  runner，保持 `fetch-depth: 0`**；既有 D15A / D14A CI integration 语义保持不变。
- **不**新增 wheel / pyproject / setup / 任何发布构建体系；
- 本 Task 不整体排除 `.github/**`；除 `baseline-check.yml` 单文件的有限接入
  声明外，**不**修改 / 不新增任何其他 `.github/workflows/*` 的 job / runner / 语义。
- **不**修改 `packaging/**`、`cpp-bridge/**`、`memory-service/**`、`migrations/**`、
  `config/**`、`scripts/**`、`tests/**`、`evidence/**`、`evidence/index.yaml`；
- **不**额外修改 `docs/day14/**`：`docs/day14/00_d14a_release_package_contract.md`、
  `docs/day14/01_d14a_implementation_report_20260905.md` 或任何 D14A 冻结契约/报告
  需保持原样（如需改动身份字段须由 D 主审会签并升版，本 Task 不代做）；
- **不**执行 / 不宣称任何正式 `FINAL` 锁、不做 L2/L3、不访问银河麒麟虚拟机。

---

## 2. 交付物身份判定

### 2.1 正式交付物身份

- **正式交付物**：D14A 发布包 `dist/kylin-memory-a-d14a-0.1.0-d14a/`（包名
  `kylin-memory-a-d14a`，`package_version=0.1.0-d14a`，见
  `docs/day14/00_d14a_release_package_contract.md` §1）；
- **Bridge**：该发布包内 `runtime/bridge/` 下的 `kylin_embedding*.so`（CMake +
  pybind11 构建产物），为 A 轨锁点 A15-1 的锁定对象；
- **不包含任何 wheel / pyproject / setup.py / *.whl 构建体系**：全仓 `git ls-files`
  无 `pyproject.toml`、`setup.py`、`setup.cfg`、`*.whl`、`*.so` 跟踪文件；
  本仓库不存在 wheel 发布链路，本 Task 也不新增；**本 Task 不新增任何
  wheel 构建体系**。
- **正式交付物身份以发布包内 `kylin_embedding*.so` 为准**：该 so 为 CMake/pybind11
  构建产物并装入 `runtime/bridge/`；wheel 一律不作为本 A 轨交付物出现。

### 2.2 “so/wheel”外部施工台账措辞澄清

- “锁定 Bridge so/wheel、依赖清单和构建说明”为**外部 D15-A project / construction
  ledger（外部施工台账）**中的历史泛称（该台账不在本仓库的仓库树 / 全量 git 历史内），
  **不属于本仓库版本化的权威发布契约来源**；
- 本仓库**不追踪、不含任何此类 pseudo-repo 施工台账路径**；上文历史措辞仅引用其
  语义，不代表仓库内存在该外部台账对应的已追踪文件。
- 仓库权威发布契约以 `docs/day14/00_d14a_release_package_contract.md`
  （FROZEN、唯一真源）与 `packaging/release/**` 为准；
- **语义裁量**：正式交付物身份以 **§2.1 为准**——`kylin_embedding*.so`（pybind11
  模块）是正式交付物；外部台账“so/wheel”泛称**不新增** wheel、不构成 A15 交付物
  语义；wheel 与 `packaging/kaiming` **均不在 A15 交付范围**；本 Task 亦不因外部
  措辞新增 wheel 构建体系。

---

## 3. 锁定状态机与 A15 锁点状态表

### 3.1 状态机

A 轨发布候选锁定沿如下程序推进，**任何一步未完成前不得进入下一步**：

```text
预备评审（文档矩阵基线，即本文档）  →  正式锁点逐项判定（A15-1/2/3）
  →  全部锁点闭合后由 D 主审会签 →  进入后续发布 Gate（超出本 Task）
```

- 每个正式锁点仅可在其**前置条件全部闭合且 evidence 依 §4 刷新规则复核后**，
  由 D 主审依据真实证据判定；
- 本矩阵文档基线仅建立**程序与记录**，本身不具备任何正式锁授权；
- 任何前置缺失（如 D13D 未冻结、D14D 正式 G0–G9 未运行、D14A final package
  未冻结）一律保持 `WAITING_PREREQ`，禁止以文档表格代替真实锁。

### 3.2 A15 锁点状态表（as-of 2026-09-06）

| 锁点 | 锁定内容 | 当前状态 |
|---|---|---|
| A15-1 | Bridge `kylin_embedding*.so` / 依赖清单 / 构建说明 正式锁 | `WAITING_PREREQ` |
| A15-2 | SDK 防御测试与性能报告 正式锁 | `WAITING_PREREQ` |
| A15-3 | 最终包 `VERSION` / `manifest` / source identity 一致性锁 | `WAITING_PREREQ` |
| 本矩阵线 | D15A A 轨发布候选锁定矩阵与状态基线文档 | `DOCUMENTATION_PREPARATION / READY_FOR_REVIEW` |

- 上表前三行（A15-1/A15-2/A15-3）当前均只能为 **`WAITING_PREREQ`**；
- 第四行为**独立行**，仅表示本文档作为准备基线处于文档评审状态，**不得**与前三行
  混标、不得被解读为任何正式锁；
- **机器守卫语义（M-2）**：每个 A15-x 锁点在**表格中仅允许恰好一行**，且该唯一行的
  状态 cell 必须**精确等于 `WAITING_PREREQ`**；任何重复 / 歧义 / 混合 / 额外状态一律
  fail-closed，**不使用** `any(WAITING_PREREQ)` 接受重复或冲突行（实际强制由配套
  确定性测试承担，见 test 的第 2 条断言与 §7.2bis 结构化状态行覆盖）。

---

## 4. 仓库事实快照与刷新规则（as-of 2026-09-06）

### 4.1 Git 事实

- 当前分支：`release/D15A-lock-preparation`；
- `preparation_base_commit`（历史固定 SHA）：
  `3138e942770ec1f9863e86c03da4df9dd1ad8703`（`origin/main` 同点）——仅作为锁准备
  基线的历史记录，随 preparation HEAD 前移不更新；
- `current_head`（动态）：正式复核时以 `git rev-parse HEAD` 输出（40 位完整 SHA）
  为唯一真源，本文件**不在任何绑定窗口硬编码 40 位 SHA**；命令失败 / 非 clean
  tree 一律 fail-closed，**不得 Mock、不得默认 / 伪造 HEAD**；语义等价 D14A 契约
  §1.1 `current_pr_head`;
- `git status --porcelain` 为空（worktree clean）——在创建本文档与配套测试之前
  的工作区事实；
- `historical_tested_runtime_commit = e3d4b9d565e2c3c153973125b3c071225e1b9e4d`
  （历史固定记录：历史 runtime 包在真实 VM **实际执行**的提交；D14A 契约 §1.1
  现行值）；
- `current_tested_runtime_commit`：正式 evidence/contract 当前声明的**实际被测提交**；
  当前 as-of 为**未选择**（final tested_commit 仍 `PENDING_P0_I3_RESELECTION`，
  `evidence/index.yaml` 无 D13A/D14A 正式条目）。

### 4.2 事实快照

| 项 | 状态（as-of 2026-09-06） |
|---|---|
| final tested_commit | `PENDING_P0_I3_RESELECTION`（D13D 正式基线须在 P0-I3c 审查/合并后由 P0-I3d 重选；历史基线 `4a32e5c…` 为 `INVALIDATED_BY_PR_157`） |
| D13D | `BLOCKED` / 未 FROZEN（TD-061 Open，见 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`） |
| D14D_ENV_PREPARED | `READY(r3)`（r1/r2 SUPERSEDED 历史；fail-closed Gate 脚本 + 正/负向证据） |
| D14D_FORMAL_L3 | `BLOCKED / NOT_STARTED`（不是 L3 就绪；正式 G0–G9 未运行） |
| G0–G9 | 未正式运行（G8 性能为 `NOT_RUN`；D14D B5：package-only runner/阈值未批准） |
| D14A final package | `NOT_FROZEN`（`PACKAGE_IMPLEMENTATION_CANDIDATE`，未到 formal candidate） |
| D14A formal package hash | `NOT_FROZEN`（未重算；正式 hash 未回填） |
| D14A BLOCKER C | `HANDOFF_REQUIRED`（runtime/model 冻结身份无 D Reviewer 接受的可信外部输入，契约 §6bis） |
| runtime evidence 相对 main | `RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED`（快照时刻对历史已知被测提交 `e3d4b9d…`（`historical_tested_runtime_commit`）的 diff 观测到 `packaging/`、`memory-service/`、`migrations/` 等 runtime/生产前缀；须重新打包 → 重算 hash → 真实 VM 重测后回填） |
| D13A perf（`perf/day13a` 三轮 run_01~03 + summary） | `INVALIDATED`（`perf/day13a/INVALIDATED.md`；不作为正式性能基线） |
| D13A `formal_baseline_complete` | `formal_baseline_complete=false` |
| G8 package-only runner/阈值 | 未批准（D14D B5） |
| evidence/index.yaml | 尚无 D13A/D14A 正式条目（git grep 在 `evidence/index.yaml` 无命中） |
| package_version | `0.1.0-d14a` |

### 4.3 刷新规则（任何正式锁前必须执行）

任何正式锁判定前，必须重新执行以下只读事实，并以结果为唯一依据：

1. `git rev-parse HEAD` —— 取得执行时 HEAD（40 位完整 SHA）；
2. `git status --porcelain` —— 必须为空（dirty tree 一律不得进入正式锁判定）；
3. `git diff --name-only current_tested_runtime_commit..HEAD` —— 基线取正式
   evidence/contract 当前声明的**实际被测提交**，**不永久绑定历史基线 e3d4…**；
   对结果做三分类：

   - `EVIDENCE_CURRENT`：diff 为空；
   - `DOCS_EVIDENCE_ONLY`：diff 非空且不含 `packaging/`、`memory-service/`、
     `cpp-bridge/`、`migrations/`、`config/` 任一前缀（仅 docs/evidence 等变更）；
   - `RUNTIME_EVIDENCE_STALE`：diff 含上述任一 runtime/生产前缀——必须
     **重新打包 → 重算 hash → 重跑真实 VM** → 回填 `tested_runtime_commit` /
     `evidence_commit` 后才可更新 runtime evidence。

随后按结果**复核本节快照**；任一事实与 §4.2 不符时，本文件的状态表与结论
**一律作废**，不得引用。

- **当前事实（as-of）**：`current_tested_runtime_commit` **未选择**，不得以
  `historical_tested_runtime_commit`（e3d4b9d…）充当现行刷新基线；runtime evidence
  结论保持 `RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED`。三分类
  （`EVIDENCE_CURRENT` / `DOCS_EVIDENCE_ONLY` / `RUNTIME_EVIDENCE_STALE`）与
  fail-closed 处理原样保留。

---

## 5. 正式锁验收门禁与版本一致性检查程序

> 本节定义**正式锁时执行的程序**，引用 `docs/day14/00_d14a_release_package_contract.md`
> §1/§5.1/§7/§10 与 `packaging/release/build_release_package.sh` 现状。
> **本节不虚构任何已执行结果**——所有检查项当前均未达到“已通过”状态。

### 5.1 版本一致性等式（正式锁时 fail-closed）

- **最终包内** `VERSION` 文件内容 == `manifest.package_version` == `0.1.0-d14a`
  （契约 §1 / §10；`build_release_package.sh` 现状：`PACKAGE_VERSION="0.1.0-d14a"`，
  Phase 2.8 写入 `VERSION`）；
- **安装侧** `EXPECT_SOURCE_COMMIT` / `EXPECT_PACKAGE_VERSION`（`systemd_install.sh`）
  与正式包的 `manifest.source_commit` / `manifest.package_version` **精确一致**
  （fail-closed：缺失、格式非法、不匹配均拒绝，契约 §7）；
- `source_commit` 必须是**正式 build 时 `git rev-parse HEAD` 的 40 位完整 SHA**，
  且等于 `manifest.source_commit`（`build_release_package.sh` Phase 0
  `--source-commit` 必填且与 HEAD 一致，dirty-tree Gate fail-closed）；
- 不得超过任意字段互相伪造相等（契约 §1.1 四身份语义：`source_commit` /
  `tested_runtime_commit` / `evidence_commit` / `current_pr_head` 独立）；
  动态 `current_head` / `current_pr_head`（执行时 `git rev-parse HEAD`）与
  `source_commit` / `tested_runtime_commit` / `evidence_commit` 独立，不得互相
  伪造相等。

### 5.2 正式锁验收门禁（步骤序列）

1. **§4 刷新复核**：HEAD / clean / 三分类结果与正式锁目标一致；
2. **重新打包**（`build_release_package.sh`）：包结构完整
   （bin/runtime/config/systemd/VERSION/manifest/SHA256SUMS），build-time Builder Gate
   （契约 §5.1 A，当前脚本已实现）；
3. **重算 hash**：`manifest.json` 与 `SHA256SUMS` 双向断言（契约 §10）；
4. **真实 VM 重测（L2/L3）**：clean VM 上 package-only install → start → 真实 SDK
   smoke（独立 embedding server PID 实载校验）→ restart → 回退；dependency audit
   （ldd/readelf/path_scan）按契约 §5.2 B 以 REQUIRED Gate 执行；
5. **回填身份**：回填 `tested_runtime_commit` / `evidence_commit` 并登记
   `evidence/index.yaml`（契约 §12）；
6. **D 主审会签**：全部证据与契约一致后，由 D 主审对 A15-1/2/3 逐项判定。

### 5.3 明确未执行

以下项**当前均未执行**，任何文档或测试不得宣称其已完成：

- 正式重打包（正式 D14A final package 未生成）；
- 正式 hash 重算与回填；
- 真实麒麟 VM 上的正式 L2/L3 复测；
- `evidence/index.yaml` 的 D13A/D14A 正式条目登记。

---

## 6. 已知限制与 blockers

| # | 限制 / blocker | 影响 |
|---|---|---|
| B1 | D13D 未 FROZEN（TD-061 Open，`PENDING_P0_I3_RESELECTION`） | A15-1/2/3 前置缺失，保持 `WAITING_PREREQ` |
| B2 | D14D 正式 G0–G9 未运行；`D14D_FORMAL_L3=BLOCKED / NOT_STARTED` | 无正式 L3 证据可引用 |
| B3 | D14A final package `NOT_FROZEN`、formal package hash `NOT_FROZEN` | A15-3 前置缺失 |
| B4 | D14A BLOCKER C = `HANDOFF_REQUIRED`（runtime/model 冻结身份） | 不得宣称 runtime/model identity 闭环 |
| B5 | runtime evidence 相对 main 为 `RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED` | 必须重打包 → 重算 hash → 真实 VM 重测后才可更新 |
| B6 | D13A perf 三轮 `INVALIDATED`，`formal_baseline_complete=false`；G8 package-only runner/阈值未批准（D14D B5） | A15-2 性能报告无有效基线可引用 |
| B7 | evidence/index.yaml 无 D13A/D14A 正式条目 | 正式证据索引未就绪 |
| B8 | 本 Task 不新增任何 wheel 构建体系、不生成发布包 | A15 正式锁需后续 Gate 独立执行 |

以上 blockers 属**本 Task 不解除**的既定事实；本矩阵仅登记，不越级宣称已解决。

---

## 7. 状态词纪律与责任/Reviewer

### 7.1 允许使用的受控状态词

`WAITING_PREREQ`、`BLOCKED`、`RUNTIME_UNVERIFIED`、`RUNTIME_EVIDENCE_STALE`、
`NOT_FROZEN`、`NOT_STARTED`、`PENDING_P0_I3_RESELECTION`、`DOCUMENTATION_PREPARATION`、
`READY_FOR_REVIEW`、`HANDOFF_REQUIRED`、`INVALIDATED`、`PENDING`、`NOT_RUN`、
`PACKAGE_IMPLEMENTATION_CANDIDATE`。

### 7.2 禁止的越级结论（全文不得出现）

以下**语义**在本文件全文中一律不得以任何中英文等价表述出现，属必须遵守的**文档
纪律**（中文 / 自然语言同义越级同样受约束，不只是受控英文 sentinel）；其中机器
守卫（确定性测试）只覆盖受控英文 sentinel、结构化状态行与已定义 provenance/state
token（覆盖边界见 7.2bis），语义级越级与语义归因由独立 Reviewer 人工审查：

- **正式终锁类**：以“最终锁定 / final 锁定”语义表述的状态结论（final 前缀加
  lock 后缀的英文组合即属此类）；
- **终态锁定类**：以英文“锁定”（lock 词族）独立词义结尾的终态结论
  （受控词 `BLOCKED` 除外——`BLOCKED` 中的局部拼写不构成越级结论）；
- **“L3 就绪”类**：L3 层级与“就绪/ready”语义组合表达的状态结论；
- **“宿主已核验”类**：宿主（host）层级与“已核验/verified”语义组合表达的结论；
- **“Runtime 已核验”类**：运行期（runtime）与“已核验/verified”语义组合表达的
  结论（受控词 `RUNTIME_UNVERIFIED` 不受影响）；
- **完成/就绪结论类**：『D14A 已完成』、『生产就绪』、『发布就绪』以及对应的
  英文等价表述；
- **D13A 形式基线完成结论**：`formal_baseline_complete` 不得声明为 `true`
  （当前事实为 `false`）。

> 上述 §7.2 所列越级词族的英文原词组合（final 锁定、lock 词族终态、
> L3 加就绪、host 加已核验、runtime 加已核验、D14A 完成、生产就绪、发布就绪等）
> 在本文件全文中**均以中文语义描述代替，不书写其英文原词组合**；配套测试以
> 机器可读方式断言其缺席（fail-closed）。任何新提交若引入上述越级结论，测试
> 立即变红。

### 7.2bis 机器守卫覆盖边界

配套确定性守卫测试（`docs/day15/test_d15a_rc_lock_matrix.py`，纯 stdlib 静态断言）
**仅**声明覆盖：

1. **受控英文 sentinel 缺席**：§7.2 所列越级词族对应的受控英文 sentinel 词边界
   token（final 前缀加 lock 后缀组合、独立 lock 词族终态、L3 加 ready、host 加
   verified、runtime 加 verified 组合，以及 D14A 完成 / 生产就绪 / 发布就绪的
   英文固定短语）一律缺席；
2. **结构化状态行**：A15-1/A15-2/A15-3 表格行与 `WAITING_PREREQ` 的行级绑定、
   本矩阵线独立状态行；
3. **已定义 provenance/state token 在场**：受控状态词、`preparation_base_commit`、
   `historical_tested_runtime_commit` / `current_tested_runtime_commit`、三分类
   （`EVIDENCE_CURRENT` / `DOCS_EVIDENCE_ONLY` / `RUNTIME_EVIDENCE_STALE`）、
   `current_head` 与关键仓库事实。

**不覆盖**中文 / 自然语言同义越级、语义归因、evidence 真实性——由独立 Reviewer
（D 主审，涉性能 / 安全由 E 补审）人工审查；本守卫**不引入** NLP / LLM / 机器
学习检测（纯 stdlib 静态断言，无模型、无语义推理、无网络、无 Runtime 依赖）。

### 7.3 责任与 Reviewer

- **责任方**：本文档与配套测试由 A 轨（D15A）维护；正式锁判定须由 **D 主审**
  依据真实 evidence 会签，作者不得自审；
- **Reviewer**：本矩阵线与配套测试的 Review 由 **D 主审**执行；凡涉及
  性能指标（A15-2）或安全结论的判定，须 **E 补审**共同确认；
- 任何越级结论、伪造 evidence、以 Mock 冒充 Runtime Test 的行为，一律
  fail-closed 拒绝并上升为阻断项。

---

*本文档为 D15A A 轨发布候选锁定矩阵与状态基线（as-of 2026-09-06）。
正式锁前必须按 §4 刷新规则重跑复核，任何变更均须 D 主审会签。*
