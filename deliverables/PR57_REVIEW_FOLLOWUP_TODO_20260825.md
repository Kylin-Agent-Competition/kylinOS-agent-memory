# PR#57 复审待办清单（第三轮收口）

- **来源**：PR#57 最新一轮复审（Reviewer `lovezy0730-create`，2026-08-25T00:19:33Z，结论 **REWORK / DO NOT MERGE**）
- **审查对象 HEAD**：`e7528bc7d6406f2adc14ec50b81d9b089a50b885`（分支 `feat/d4-phase0-ipc-alignment`）
- **审查原文**：<https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/57#pullrequestreview-5013758568>
- **整理日期**：2026-08-25
- **收口目标**：审查结论明确「若下一轮没有新增回归，应优先向 **PASS_WITH_DEBT** 收口，不建议继续扩大返工范围」。因此本清单只列**必须关闭的最小集合** + 可登记 TD，不再扩大范围。
- **前置说明**：第二轮 REWORK 中的多数意见（ALIGN-005 socket ownership、必填字段校验、错误码语义分类、envelope data 契约、证据脱敏）作者已在 `740bb62` 及后续提交修复，并完成麒麟宿主 L2 验证。**本轮仍被要求关闭的是下述「必须关闭的最小集合」**，多数为返工未完全覆盖的遗留项。

---

## 一、待办总览

| # | 严重度 | 类型 | 关联审查条目 | 待办摘要 | 状态 |
|---|:---:|---|------|----------|:---:|
| B-1 | **BLOCKER** | 合并冲突 | 最小集合 #1 | 同步最新 `main`（`87dac64`，PR#56），解决 `evidence/index.yaml` 合并冲突 | ⬜ |
| H-1 | **HIGH** | 测试脚本 Bug | 最小集合 #2 | 修复 `run_l2_verify.py::l2_a1` 对正式 `memory.sock` 的无条件 `rm -f`，并重跑 L2-A1 | ⬜ |
| H-2 | **HIGH** | 契约 Bug | 最小集合 #3 | 修复非法 typed `request_id/trace_id` 导致错误 envelope 自身违反 FRZ-IPC-006 | ⬜ |
| H-3 | **HIGH/Security** | 安全确认 | 最小集合 #4 | 完成 servicekey 历史泄露的安全属性确认与处置结论 | ⬜ |
| M-1 | MEDIUM/Governance | 文档口径 | 最小集合 #5 | 统一 ALIGN-005 socket ownership 文档口径（Checklist / ADR-008 / 实现三处） | ⬜ |
| TD-1 | MEDIUM | 技术债 | 四-M1 | `/tmp` fallback 非严格 per-user（`/tmp/kylin-memory/embedding.sock` 跨用户固定路径） | 登记 |
| TD-2 | — | 技术债 | 四-M2 | L2-C1 用 `sudo mv` 系统 SDK `.so` 模拟缺失，异常中断有残留风险 | 登记 |
| TD-3 | LOW | 技术债 | 五-Evidence | evidence metadata 精化（Reviewer 提及项） | 登记 |
| L-1 | LOW | 文档卫生 | 六-1 | PR body 过时表述需更新 | ⬜ |
| L-2 | LOW | 文档卫生 | 六-2 | Checklist 中 `599 passed` 与 `602 passed` 统一 | ⬜ |
| L-3 | LOW | 文档卫生 | 六-3 | Checklist `[ ]` 与仓库实际完成状态同步 | ⬜ |
| P-1 | — | 流程核签 | 七-ADR-008 | 形成最终可合并 HEAD 后，提交 Reviewer E 签署 ADR-008（SIGN_AFTER_FINAL_HEAD） | ⬜ |
| P-2 | — | 流程 | 作者 comment | 能力矩阵 `IPC-001`/`EMB-T03` 回写（01 文档，另行更新） | ⬜ |
| P-3 | — | 流程 | 审查结论 | 全部关闭后请求下一轮复审；无新增回归则向 PASS_WITH_DEBT 收口 | ⬜ |

---

## 二、详细待办项

### B-1 【BLOCKER】同步最新 main，解决 `evidence/index.yaml` 冲突

- **现状核实**：本分支 merge-base 为 `8bf4c9b`；`kylin-agent/main` 已前进到 `87dac64`（PR#56 `Feat/e d6 multisource quality security gate`），该 commit 对 `evidence/index.yaml` 增加约 40 行；本分支在相同文件末尾追加约 86 行（`PHASE0-ALIGN005-001` / `PR57-L2-001` / `PR57-L2-IPC001-001` / `PR57-L2-EMBT03-001`）。Git 合并会发生**同一文件末尾追加冲突**。
- **动作**：
  1. `git fetch kylin-agent && git rebase kylin-agent/main`（或 merge），手工合并 `evidence/index.yaml`，保留 main 的 PR#56 登记 + 本分支 PR#57 登记；
  2. 冲突解决后重新跑 `git diff --check` 确认无 trailing whitespace；
  3. 本地/CI 复验 index.yaml 结构合法（YAML 可解析、entries 无重复 id）。
- **验收**：`evidence/index.yaml` 同时含 main 的 E 轨 d6 登记与本分支 PR#57 的 4 条登记，无冲突残留，YAML 合法。

### H-1 【HIGH】修复 L2-A1 runner 对正式 `memory.sock` 的无条件 unlink，并重跑 L2-A1

- **现状核实**：`evidence/l2-kylin-vm/run_l2_verify.py::l2_a1`（约 268/287 行）在测试前后直接执行 `rm -f {MEM_SOCK}`（`MEM_SOCK=/run/user/1000/kylin-memory/memory.sock`）。虽然测试用受控 `active_listener.py`，但 runner 对**正式 Memory Service 入口 socket 做无条件 `rm -f`** 不安全：若该路径存在正式监听（现状证据显示 `python pid=3107` 曾占用 `memory.sock`），误删会破坏正式服务。
- **动作**：
  1. 将 L2-A1 的 `rm -f {MEM_SOCK}` 改为**受控/隔离路径**（如 `{REPO}/l2a1-mem.sock` 或 `$XDG_RUNTIME_DIR/kylin-memory/l2a1-test.sock`），禁止触碰正式 `memory.sock`；仅清理本次测试自己创建的 listener；
  2. 断言逻辑不变（active listener 拒绝 unlink + listener 仍存活 + socket 未被抢占）；
  3. 以修复后 runner 在麒麟 VM **重跑 L2-A1**（审查结论为 MUST_RERUN），回收 raw 证据并绑定新 HEAD。
- **验收**：L2-A1 重跑 PASS，runner 不再对正式 `memory.sock` 执行任何 `rm -f`；证据绑定新 HEAD。

### H-2 【HIGH】修复非法 typed `request_id/trace_id` 导致错误 envelope 违反 FRZ-IPC-006

- **现状核实**：`embedding_service.py::_envelope_error` 用 `req.get("request_id", "")` / `req.get("trace_id", "")` 透传原始值；`protocol.py::build_error_envelope` 用 `request_id or ""` 兜底。当请求的 `request_id`/`trace_id` 是**非空非字符串类型**（如 dict/int）时，`or ""` 不触发（truthy），导致**错误 envelope 自身的 `request_id`/`trace_id` 仍是非字符串类型**，违反 FRZ-IPC-006 §6.2（envelope 字段类型契约）。`parse_envelope` 校验通过前即抛错，错误路径绕过校验。
- **动作**：
  1. 错误 envelope 构造时对 `request_id`/`trace_id` 做**类型收敛**：仅接受 `str`，非 str（或空串）一律回退为空串 `""`（在 `_envelope_error` 或 `build_error_envelope` 统一处理）；
  2. 补充 typed-ID 用例：`request_id`/`trace_id` 为 dict / int / bool / 空串时，错误响应 `request_id`/`trace_id` 必须为字符串类型；
  3. 同时补充到 L2-B2 宿主验证（审查建议补 typed-ID case）。
- **验收**：新增 L0/L1 测试通过；宿主 L2-B2 补充 typed-ID 用例验证通过；错误 envelope 中 `request_id`/`trace_id` 恒为 `str`。

### H-3 【HIGH/Security】完成 servicekey 历史泄露的安全属性确认与处置结论

- **现状核实**：`collect_phase0_evidence.py` 已实现 `redact()`（`servicekey/secret/token/key=...` → `REDACTED`），当前工作树文件无明文 `servicekey`。但需确认**历史提交**是否曾将明文 `servicekey`（`/etc/.kyinfo` 的 `[servicekey] key=...`）写入仓库（git 历史可被检索），并给出正式处置结论。
- **动作**：
  1. 全历史审计：`git log -S servicekey` / `git log -p -- evidence/phase0` 等确认是否曾有明文 `servicekey` 入库；
  2. 若存在，给出处置结论：评估泄露影响（该 key 是否仍有效）、是否需要轮换、是否改写历史（建议评估成本后再定，不要轻易 `filter-branch`）、并在 PR 说明 / 安全审查中如实记录；
  3. 若无明文，书面确认「历史无明文 servicekey 泄露」作为处置结论落档。
- **验收**：PR 内给出明确的「安全属性确认 + 处置结论」，Reviewer 认可。

### M-1 【MEDIUM/Governance】统一 ALIGN-005 socket ownership 文档口径

- **现状核实（三处不一致）**：
  1. `deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` Phase 0.5（约 48 行）写「**裁定唯一 socket 路径 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`，3 套路径收敛**」；
  2. 生产实现：`embedding/server.py::_default_socket_path` 默认 **`embedding.sock`（独立子服务 socket）**，`memory.sock` 归正式 Memory Service / Gateway；
  3. `docs/adr/008-embedding-subservice-method-domain.md` 范围限定写「本 ADR **仅处理 method routing**……**不得被解释为批准 ALIGN-005 的当前 socket 方案**……另行裁决」。
  三者口径冲突（唯一 socket vs 独立 socket vs 另行裁决）。
- **动作**：
  1. 修订 `D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` Phase 0.5，改为与实现一致的描述：**Memory Service / Gateway owns `memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；Echo 属 Gate 0 / 验证实现细节**；不要求所有独立进程绑定同一个 UDS；
  2. 评估补一个**最小 socket ownership ADR**（或在既有 ADR 澄清）明确 ownership 归属；
  3. **在口径统一前，不写 `ALIGN-005 CLOSED`**。
- **验收**：Checklist / ADR / 实现三方口径一致；文档明确 socket ownership 归属；Reviewer 认可后按流程更新 ALIGN-005 状态。

---

## 三、可登记 Technical Debt（不阻断合并）

| 编号 | 来源 | 描述 | 建议处置 | 责任人 | 计划 |
|---|---|------|---------|:---:|:---:|
| TD-1 | 审查四-M1 | `_default_socket_path` 无 `XDG_RUNTIME_DIR` 时回退 `/tmp/kylin-memory/embedding.sock`（**固定跨用户路径**，非严格 per-user） | 改 `/tmp/kylin-memory-$UID/embedding.sock` 或 production 缺失 XDG 时 fail-close | D(IPC) | 后续 Phase |
| TD-2 | 审查四-M2 | L2-C1 用 `sudo mv` 系统 SDK `.so` 模拟缺失，runner 被 kill / SSH 断连 / Python crash / VM 退出时可能残留真实宿主 SDK 被移动 | disposable VM snapshot / isolated library path / loader failure injection / 临时隔离环境 | D(IPC) | Test Infra 优化 |
| TD-3 | 审查五-Evidence | evidence metadata 精化（Reviewer 提及项，细化字段/一致性） | 按证据治理规范精化 | D(IPC) | 后续 |

---

## 四、Evidence 复核建议（审查「五、Evidence 状态」）

审查明确**不要求机械重跑所有 L2**，仅对受限项处置：

| 项 | 审查结论 | 处置 |
|---|---|------|
| L2-A1 | **MUST_RERUN** | runner 修复后重跑（见 H-1） |
| L2-A2 | VALID | 维持，不重跑 |
| L2-A3 | VALID（`0e07950` 已有独立宿主重采证） | 维持 |
| L2-B1 | VALID | 维持 |
| L2-B2 | VALID_WITH_LIMITATION | 补 typed-ID case（见 H-2） |
| L2-B3 | VALID | 维持 |
| L2-C1 | VALID_WITH_LIMITATION | 维持（Test Infra 风险记 TD-2） |
| L2-C2 | VALID | 维持 |
| L2-D1 | VALID | 维持 |

---

## 五、流程 / 核签待办

- **P-1**：形成最终可合并 HEAD（B-1、H-1、H-2、H-3、M-1 全部关闭后），再提交 **Reviewer E（谢嘉然）签署 ADR-008**（审查结论：`SIGN_AFTER_FINAL_HEAD`，非现签）。
- **P-2**：能力矩阵 `IPC-001`（UDS）/ `EMB-T03`（异常输入）回写为 `HOST_VERIFIED`（`01_sdk_capability_boundary.md`，另行更新；`evidence/index.yaml` 已登记，文档需同步）。
- **P-3**：提交完整测试与证据后，请求 Reviewer 发起下一轮复审；**若无新增回归，目标 PASS_WITH_DEBT 收口，不继续扩大返工范围**。

---

## 六、诚实声明与限制

- 本清单基于 GitHub PR#57 最新一轮复审（`lovezy0730-create`，2026-08-25，commit `e7528bc`）整理；代码现状经本地核对（`protocol.py`、`server.py`、`embedding_service.py`、`run_l2_verify.py`、`D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md`、`ADR-008`、`evidence/index.yaml` 与 main 差异）。
- 第二轮意见中的 ALIGN-005 socket ownership / 必填校验 / 错误码语义 / envelope data / 证据脱敏已由 `740bb62` 及后续提交修复，**不重复列为待办**；仅保留本轮仍要求关闭的最小集合。
- 所有 L2 宿主项需在麒麟 VirtualBox V11 虚拟机执行，WSL L0/L1 不构成宿主证据；未完成 L2 前，文档/代码注释不得写「已支持」「成品通过」。
