# PR#57 复审收口修复计划（2026-08-25）

- **关联待办清单**：`deliverables/PR57_REVIEW_FOLLOWUP_TODO_20260825.md`
- **审查对象 HEAD**：`e7528bc7d6406f2adc14ec50b81d9b089a50b885`（分支 `feat/d4-phase0-ipc-alignment`）
- **目标**：关闭必须关闭的最小集合（B-1 / H-1 / H-2 / H-3 / M-1）+ 文档卫生（L-1~3），其余（TD-1~3）仅登记，最终形成可合并 HEAD 后走 P-1/P-2/P-3 流程向 **PASS_WITH_DEBT** 收口。
- **整理日期**：2026-08-25

---

## 0. 当前基线与事实核对（已核验）

- 分支 `feat/d4-phase0-ipc-alignment`，HEAD `e7528bc`，工作树干净（仅 `PR57_REVIEW_FOLLOWUP_TODO_20260825.md` 未跟踪）。
- `main` 已前进（需 fetch `kylin-agent/main` 到 `87dac64` / PR#56）。
- 相关文件已定位：

| 条目 | 文件 | 位置 |
|---|---|---|
| H-1 | `evidence/l2-kylin-vm/run_l2_verify.py` | `l2_a1` 第 265–287 行 |
| H-2 | `memory-service/embedding/embedding_service.py` | `_envelope_error` 第 494–506 行 |
| H-2 | `memory-service/embedding/protocol.py` | `build_error_envelope` 第 207–228 行 |
| H-3 | `evidence/phase0/collect_phase0_evidence.py` | `redact` 第 38–40 行 |
| M-1 | `deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md` | Phase 0.5 第 48 行 |
| M-1 | `docs/adr/008-embedding-subservice-method-domain.md` | 范围限定第 95 行 |
| M-1 | `memory-service/embedding/server.py` | `_default_socket_path` 第 43 行起 |
| B-1 | `evidence/index.yaml` | 624 行，PR#57 登记在末尾 |

---

## 1. 阶段 0 — 同步最新 main 并解决 B-1（先做，作为后续所有修复与证据的基底）

### B-1 【BLOCKER】同步 main + 解决 `evidence/index.yaml` 冲突

- 动作：
  1. `git fetch kylin-agent` 确认 `87dac64` 可用；
  2. `git rebase kylin-agent/main`（或 merge，倾向 rebase 保持线性历史）；
  3. 冲突仅在 `evidence/index.yaml` 末尾追加段：手工合并——保留 main 的 PR#56 E 轨 d6 登记（约 40 行）+ 本分支 PR#57 的 4 条登记（`PHASE0-ALIGN005-001` / `PR57-L2-001` / `PR57-L2-IPC001-001` / `PR57-L2-EMBT03-001`）；
  4. 冲突解决后 `git diff --check` 确认无 trailing whitespace；
  5. 校验 YAML 合法 + entries 无重复 id。
- **验收**：`index.yaml` 同时含 main 与 PR#57 全部登记，无冲突残留。
- **注意**：本步骤是后续 H-1/H-2 证据绑定新 HEAD 的前置，**必须先完成**。


---

## 2. 阶段 1 — 代码级修复（H-1、H-2）

### H-1 【HIGH】修复 L2-A1 runner 对正式 `memory.sock` 的无条件 unlink

- 现状：`run_l2_verify.py:268` 测试前 `rm -f {MEM_SOCK}`、`:287` 测试后 `rm -f {MEM_SOCK}`，均为正式 `memory.sock`（`/run/user/1000/kylin-memory/memory.sock`）。
- 动作：
  1. 引入受控路径常量 `A1_SOCK = f"{REPO}/l2a1-mem.sock"`（或 `$XDG_RUNTIME_DIR/kylin-memory/l2a1-test.sock`），**禁止使用 `MEM_SOCK`**；
  2. `l2_a1` 内两处 `rm -f {MEM_SOCK}` 全部改为 `rm -f {A1_SOCK}`；`active_listener.py` 与 `embedding.server --socket` 均改用 `A1_SOCK`；
  3. 断言逻辑不变（active 拒绝 unlink + listener 存活 + socket 未被抢占）；
  4. 在麒麟 VM 以修复后 runner **重跑 L2-A1**，回收 raw 证据，`index.yaml` 中 `tested_commit`/`evidence_commit` 绑定新 HEAD（MUST_RERUN）。
- **验收**：L2-A1 PASS，runner 源码中**不再出现对正式 `MEM_SOCK` 的 `rm -f`**；证据绑定新 HEAD。

### H-2 【HIGH】修复非法 typed `request_id/trace_id` 导致错误 envelope 违反 FRZ-IPC-006 §6.2

- 现状：`_envelope_error`（`embedding_service.py:504-505`）透传 `req.get("request_id","")`；`build_error_envelope`（`protocol.py:221-222`）用 `request_id or ""`，对 dict/int 等 truthy 非 str 值不收敛。
- 动作：
  1. 在 `build_error_envelope`（**单一实现，收敛点**）内对 `request_id`/`trace_id` 做类型收敛：`rid = request_id if isinstance(request_id, str) else ""`，trace_id 同理（保持函数签名 `str` 兼容，不破坏调用方）；
  2. 在 `test_protocol.py` / `test_embedding_service.py` 新增 typed-ID 用例：`request_id`/`trace_id` 分别传 dict / int / bool / 空串时，错误 envelope 的 `request_id`/`trace_id` **恒为 `str`**（含空串）；
  3. 在 `run_l2_verify.py::l2_b2` 补充宿主 typed-ID 用例（审查建议 VALID_WITH_LIMITATION 补 typed-ID case）。
- **验收**：新增 L0/L1 测试通过；宿主 L2-B2 typed-ID 用例 PASS；错误 envelope 中两字段恒为 `str`。

---

## 3. 阶段 2 — 安全与文档（H-3、M-1）

### H-3 【HIGH/Security】servicekey 历史泄露安全属性确认与处置结论

- 现状：`collect_phase0_evidence.py` 已有 `redact()`，当前工作树无明文。
- 动作（审计型，不修改代码）：
  1. 全历史审计：`git log --all -S servicekey`、`git log -p -- evidence/phase0`、`git log --all -S '/etc/.kyinfo'` 等；
  2. 结论分支：
     - 无明文 → 在 PR 说明中书面落档「历史无明文 servicekey 泄露」；
     - 有明文 → 评估 key 有效性、是否需轮换、是否改写历史（不轻易 `filter-branch`），如实记录处置。
- **验收**：PR 内给出「安全属性确认 + 处置结论」，Reviewer 认可。

### M-1 【MEDIUM/Governance】统一 ALIGN-005 socket ownership 三方口径

- 现状（三处冲突）：
  1. Checklist Phase 0.5（`D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md:48`）写「唯一 socket 路径 + 3 套收敛」；
  2. 实现 `server.py::_default_socket_path` → `embedding.sock`（独立子服务 socket），`memory.sock` 归 Memory Service/Gateway；
  3. ADR-008 范围限定（:95）「不得解释为批准 ALIGN-005 当前 socket 方案，另行裁决」。
- 动作：
  1. 修订 Checklist Phase 0.5，改为与实现一致：**Memory Service/Gateway owns `memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；Echo 属 Gate 0 验证细节；不要求所有进程绑同一 UDS**；
  2. 在既有 ADR-008 或新增最小 socket ownership 说明中明确 ownership 归属；
  3. **口径统一前不写 `ALIGN-005 CLOSED`**。
- **验收**：Checklist / ADR / 实现三方一致，明确 ownership 归属，Reviewer 认可后再更新 ALIGN-005 状态。

---

## 4. 阶段 3 — 文档卫生（L-1 ~ L-3，低成本，随阶段合并入 commit）

- **L-1**：更新 PR body 过时表述。
- **L-2**：Checklist 中 `599 passed` / `602 passed` 统一为最终实际通过数。
- **L-3**：Checklist `[ ]` 勾选状态与仓库实际完成状态同步。

---

## 5. 阶段 4 — 流程与核签（P-1 ~ P-3，收口）

- **P-2**：`01_sdk_capability_boundary.md` 能力矩阵 `IPC-001`（UDS）/ `EMB-T03`（异常输入）回写 `HOST_VERIFIED`（`index.yaml` 已登记，同步文档）。
- **P-1**：形成最终可合并 HEAD（B-1/H-1/H-2/H-3/M-1 全部关闭后）→ 提交 **Reviewer E（谢嘉然）签署 ADR-008**（SIGN_AFTER_FINAL_HEAD）。
- **P-3**：提交完整测试与证据 → 请求下一轮复审；无新增回归则 **PASS_WITH_DEBT 收口**。

---

## 6. 不阻断项（仅登记，不处理）

| 编号 | 描述 | 处置 |
|---|---|---|
| TD-1 | `/tmp` fallback 非严格 per-user（`/tmp/kylin-memory/embedding.sock` 固定跨用户路径） | 后续 Phase |
| TD-2 | L2-C1 `sudo mv` 系统 SDK `.so` 模拟缺失，异常中断残留风险 | Test Infra 优化 |
| TD-3 | evidence metadata 精化 | 后续 |

---

## 7. 建议执行顺序与验证节奏

| 步骤 | 动作 | 验证 |
|---|---|---|
| 1 | fetch + rebase main，解决 B-1 冲突 | `git diff --check`、YAML 解析、无重复 id |
| 2 | H-2 代码收敛 + L0/L1 typed 测试 | `pytest memory-service/tests` |
| 3 | H-1 runner 改造 | 静态检查无 `rm -f MEM_SOCK` |
| 4 | H-3 历史审计 | `git log -S servicekey` 结论落档 |
| 5 | M-1 文档统一 + L-1~3 | 三方口径 diff 复核 |
| 6 | 麒麟 VM 重跑 L2-A1 + L2-B2 typed-ID | runner PASS，证据绑定新 HEAD |
| 7 | P-2 矩阵回写 → P-1 提交 Reviewer E → P-3 复审 | PASS_WITH_DEBT 收口 |

---

## 8. 风险与注意事项

- 阶段 0（B-1）必须在任何证据重跑之前完成，否则证据 `tested_commit` 无法绑定最终 HEAD；
- H-2 收敛点选在 `build_error_envelope` 单一实现，避免 `_envelope_error` 与 `server.py` 两套逻辑漂移；
- H-3 若发现历史明文泄露，**优先评估轮换而非立即 `filter-branch`**，结论需在安全审查中如实记录；
- 所有 L2 宿主证据需在麒麟 VirtualBox V11 VM 执行，WSL L0/L1 不构成宿主证据；未完成 L2 前不得在文档/注释写「已支持」。
