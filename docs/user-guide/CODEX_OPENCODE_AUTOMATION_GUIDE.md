# Codex + OpenCode 自动化开发工具说明

> 文档状态：项目开发工具说明  
> 适用仓库：`Kylin-Agent-Competition/kylinOS-agent-memory`  
> 当前 Supervisor Skill：`opencode-batch-supervisor v1.2`  
> 目标：在不替代现有 OpenCode Task/Batch 工作流的前提下，用 Codex 作为外层 Supervisor，完成环境归一化、任务调度、失败诊断、长任务恢复与人工交接。

---

## 1. 工具定位

本工具不是新的代码生成框架，也不替代仓库已有的 OpenCode 工作流。

其职责是把 Codex 放在现有工作流外层，作为“自动化监督器（Supervisor）”：读取项目源、识别当前开发目标、复用或生成 Task/Batch、启动已有 OpenCode 工作流、观察真实日志、对非 0 结果做分类和最小诊断，并持续监督到 Batch 成功或遇到必须人工处理的真实阻塞。

现有 OpenCode 工作流仍然是实现权威：

```text
Task JSON
  ↓
Batch JSON
  ↓
Planner
  ↓
Implementer
  ↓
L0 / L1
  ↓
Reviewer
  ↓
Fixer（需要时）
  ↓
Evidence Reviewer
  ↓
Atomic Commit
```

Codex Supervisor 位于该链路之外：

```text
Human
  ↓
Codex / opencode-batch-supervisor
  ↓
现有 OpenCode Task/Batch 工作流
  ↓
代码、测试、Review、Evidence、Commit
  ↓
Codex 汇总最终状态
  ↓
Human Handoff
```

核心原则：**人工主导边界，Agent 自动执行，Reviewer 独立审查，证据真实闭环。**

---

## 2. 适用场景

适合：

- 日常 A/B/C/D/E 轨开发；
- 已有 Task/Batch 的自动执行；
- 根据当前仓库事实生成新的原子 Task/Batch；
- PR Review 后的修复 Batch；
- L0/L1 自动验证；
- Planner / Implementer / Reviewer / Fixer / Evidence Reviewer 的连续调度；
- Batch 非 0 后的日志诊断；
- Codex Desktop 长任务中断后的状态恢复；
- 文档、测试、业务代码等 WSL 内可完成任务。

不适合由本 Skill 自动完成：

- 直接在 `main` 开发；
- 自动创建、切换、rebase 或 reset 分支；
- push；
- 创建或修改 PR；
- APPROVE / merge；
- L2/L3 麒麟真实宿主验证；
- release；
- 需要 sudo、交互凭据或高权限操作的任务；
- 擅自安装/升级依赖；
- 修改 `.local-agent-workflow` 工作流引擎本身。

这些动作默认保留给人工，除非后续单独扩展专用 Skill。

---

## 3. 推荐运行环境

当前项目推荐环境：

```text
Windows 11
  └─ WSL2
      └─ Ubuntu 22.04
          └─ kylinOS-agent-memory
              ├─ .venv
              ├─ .local-agent-workflow
              ├─ .opencode
              └─ .agent-runs
```

Codex 应打开 WSL 中的真实仓库，而不是 Windows 镜像目录：

```text
/home/<user>/projects/kylinOS-agent-memory
```

首次接入时建议检查：

```bash
pwd
uname -a
cat /etc/os-release
git rev-parse --show-toplevel
git branch --show-current
command -v python3
command -v opencode
command -v code
echo "$HOME"
```

正确结果应满足：

- 当前目录在 `/home/...` 下；
- 系统为 Linux / WSL2；
- Git root 为当前项目；
- 当前分支不是 `main`；
- VS Code CLI 可从 WSL 调用；
- OpenCode 可被发现；
- 项目 `.venv` 存在时应优先使用项目 `.venv`。

---

## 4. Skill 安装位置

Supervisor Skill 为用户级工具，不要求提交到业务仓库。

默认路径：

```text
$HOME/.codex/skills/opencode-batch-supervisor/SKILL.md
```

检查：

```bash
test -f "$HOME/.codex/skills/opencode-batch-supervisor/SKILL.md" \
  && echo SKILL_OK \
  || echo SKILL_MISSING
```

升级 Skill 时建议先备份：

```bash
cp \
  "$HOME/.codex/skills/opencode-batch-supervisor/SKILL.md" \
  "$HOME/.codex/skills/opencode-batch-supervisor/SKILL.md.bak"
```

然后使用新版 `SKILL.md` 覆盖即可。

---

## 5. v1.2 关键能力

### 5.1 项目 `.venv` 自动归一化

Codex Desktop 启动的是非交互 shell，可能不会继承用户在 VS Code Terminal 中已经激活的 `.venv`。

v1.2 在所有 Python / pytest / JSON validation / Batch 命令前自动执行环境归一化：

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  export VIRTUAL_ENV="$REPO_ROOT/.venv"
  export PATH="$VIRTUAL_ENV/bin:$PATH"
fi
```

这样可以避免：

```text
项目 .venv 中已经安装 SQLAlchemy
        ↓
Codex 却调用 /usr/bin/python3
        ↓
误报 ModuleNotFoundError
        ↓
错误分类为 DEPENDENCY_MISSING
```

对于这种情况，正确分类是 `ENVIRONMENT_MISMATCH`，而不是直接重装依赖。

### 5.2 OpenCode / NVM 动态发现

OpenCode 可能由 NVM 管理，非交互 shell 中默认 PATH 不一定包含其安装目录。

Skill 不写死 Node 版本，而是动态发现：

```bash
if ! command -v opencode >/dev/null 2>&1; then
  OPENCODE_BIN="$(bash -ic 'type -P opencode || command -v opencode' 2>/dev/null | tail -n 1 || true)"
  if [ -n "$OPENCODE_BIN" ] && [ -x "$OPENCODE_BIN" ]; then
    export PATH="$(dirname "$OPENCODE_BIN"):$PATH"
  fi
fi
```

因此 Node/NVM 升级后通常不需要修改 Prompt。

### 5.3 Detached Batch 长任务执行

v1.1 曾发现一个桌面宿主问题：Codex 当前聊天 turn 可能结束，但 WSL 中的 `run_batch.sh` 子进程仍然继续运行。

如果长 Batch 直接作为一个前台 shell 调用，可能出现：

```text
Codex turn 结束
  ↓
Batch 后台继续
  ↓
OpenCode 最终成功 COMMITTED
  ↓
但 Codex 没回来读取 FINAL_BATCH_STATE
  ↓
没有 Human Handoff 报告
```

v1.2 将长 Batch 改为 detached、可恢复执行。

每个 Batch attempt 会持久化：

```text
.agent-runs/codex-supervisor/<batch-id>/
├── run-<N>.sh
├── pid-<N>.txt
└── status-<N>.env

.agent-runs/
└── <batch-id>-attempt-<N>.log
```

这些是本地 Supervisor 状态，不应提交到仓库。

### 5.4 Reattach / Recovery

每次启动或继续某个 Batch 前，Supervisor 必须先检查已有状态。

基本规则：

```text
STATE=RUNNING + PID alive
→ reattach
→ 禁止重复启动 Batch

STATE=FINISHED
→ 读取 FINAL_BATCH_STATE / BATCH_EXIT_CODE
→ 禁止自动重跑已经结束的 attempt

PID dead + STATE=RUNNING
→ 判定为 orphan/stale state
→ 先检查日志，不得盲目复制启动
```

Codex UI 一轮回复结束**不等于** Batch 结束。

### 5.5 短轮询监控

v1.2 不再让 Codex 用单个长时间 shell 一直阻塞。

监控采用约 20～30 秒的短 probe：

```bash
sleep 20
cat "$STATUS_FILE" 2>/dev/null || true
tail -n 80 "$ATTEMPT_LOG" 2>/dev/null || true
```

重点报告阶段变化：

```text
plan
implementation
review
fix
evidence-review
```

而不是反复刷相同日志。

如果宿主 turn 结束，允许输出：

```text
SUPERVISOR_PROGRESS: BATCH_RUNNING_BACKGROUND
```

它既不是成功，也不是失败。

---

## 6. 标准开发流程

### 6.1 人工准备分支

Supervisor 默认不会替你创建或切换开发分支。

人工先完成：

```bash
git fetch origin --prune
git switch main
git pull --ff-only origin main
git switch -c <task-branch>
```

然后确认：

```bash
git branch --show-current
git status --short --untracked-files=all
```

禁止直接在 `main` 上启动 Supervisor 开发。

### 6.2 Codex 选择项目

在 ChatGPT Desktop 中选择 Codex，并打开 WSL 项目目录：

```text
/home/<user>/projects/kylinOS-agent-memory
```

首次使用时先做环境检查，不要直接开工。

### 6.3 启动 Supervisor

典型 Prompt：

```text
$opencode-batch-supervisor 开工：完成 <当前任务>。

自行读取当前仓库中的 AGENTS.md、项目源、分工、计划、冻结契约、ADR、技术债、当前源码、测试和已有 Task/Batch。

先判断哪些内容已完成，哪些仍需开发；复用已有 Task/Batch，只有仓库事实证明旧 Task/Batch 已失效时才创建新的原子 Task/Batch。

使用现有 OpenCode 工作流持续开发。Batch 非 0 时读取真实日志并按 Skill 规则做最小诊断和修复。

持续到：
FINAL_BATCH_STATE: BATCH_COMPLETE
BATCH_EXIT_CODE=0

达到后停止。

不要 push，不创建或修改 PR，不执行 L2/L3，不 merge，不 release。
```

对于 Review 修复，应明确：

```text
PR Review 是新的外部输入。
历史已完成 Batch 不重写；新建独立 review-remediation Batch。
```

### 6.4 VS Code 观察

如果 `code` 可用，Supervisor 会执行：

```bash
code .
```

VS Code 只作为人类观察窗口，不通过 GUI 自动化操纵 VS Code。

推荐观察固定日志：

```text
.agent-runs/codex-live-console.log
```

可在终端手动查看：

```bash
tail -f .agent-runs/codex-live-console.log
```

---

## 7. 成功判定

任何 Batch 只有同时满足以下两个条件才算成功：

```text
FINAL_BATCH_STATE: BATCH_COMPLETE
BATCH_EXIT_CODE=0
```

不能因为：

- 测试看起来通过；
- Implementer 声称完成；
- Reviewer 已 APPROVE；
- detached 进程消失；
- Codex 停止输出；

就推断 Batch 成功。

成功后只允许做最终本地检查：

```bash
git status --short --untracked-files=all
git log --oneline -10
git diff --check main...HEAD
```

随后必须停在人工交接前。

最终格式：

```text
OpenCode Batch Supervisor 完成

目标: <task>
Branch: <branch>
Batch: <batch-id>
FINAL_BATCH_STATE: BATCH_COMPLETE
BATCH_EXIT_CODE: 0

Tasks:
- <task-id>: COMMITTED

Environment: <python/opencode summary>
L0: PASS
L1: PASS
Runtime/L2/L3: PENDING / NOT_APPLICABLE

Final commits:
- <sha> <message>

Remaining:
- <debt/limitation or NONE>

Human next action:
<人工下一步>

SUPERVISOR_STATUS: BATCH_READY_FOR_HUMAN_HANDOFF
```

---

## 8. 失败分类与处理原则

Supervisor 依据真实日志分类，而不是根据表象猜测。

当前主要类别：

| 分类 | 含义 | 典型处理 |
|---|---|---|
| `VALIDATION_FAILURE` | Task/Batch JSON 或 validate-only 失败 | 修正被证据证明错误的输入 |
| `PLAN_STOPPED` | Planner 停止 | 检查依赖、范围、路径、需求与仓库事实 |
| `IMPLEMENTATION_STOPPED` | Implementer 未完成 | 检查实现日志，不绕过 Implementer 手写代码 |
| `REVIEW_STOPPED` | Reviewer 阻断 | 保留 Reviewer 要求，由现有 workflow/Fixer 修复 |
| `FIX_STOPPED` | Fixer 未完成 | 检查允许修改范围和失败命令 |
| `EVIDENCE_STOPPED` | Evidence 不足 | 不伪造；真实宿主证据缺失时人工接管 |
| `AGENT_TIMEOUT` | Agent 超时 | 先判断代码失败还是 finalization/protocol stall |
| `TEST_FAILURE` | 合法测试失败 | 视为真实实现缺陷，不删测试、不降断言 |
| `SCOPE_FAILURE` | diff 超范围 | 只有 Task scope 客观错误时才改 Task |
| `ENVIRONMENT_MISMATCH` | 使用了错误现有环境 | 切回项目 `.venv` / 正确 OpenCode PATH 后复用原 Batch |
| `DEPENDENCY_BLOCKED` | 归一化后依赖仍真实缺失 | 人工处理，不静默安装 |
| `WORKFLOW_ENGINE_FAILURE` | orchestrator / harness 本身故障 | 保留日志并人工接管 |
| `UNKNOWN_WORKFLOW_FAILURE` | 暂不能可靠分类 | 继续收集证据，不猜测 |

### Task/Batch 何时允许重建

只有证据证明以下事实之一，才允许生成新的 Task/Batch：

- 旧 Task 的仓库假设已经过时；
- 前置依赖状态发生改变；
- 文件/路径写错；
- 任务不是原子的；
- Batch 顺序错误；
- 验收命令本身已失效；
- Task schema 与当前 workflow 不兼容；
- allowed scope 客观定义错误；
- 历史 Task/Batch 已明确 superseded。

以下情况**不能**作为重建理由：

- 实现失败；
- 合法测试失败；
- Reviewer 请求修改；
- Fixer 需要再尝试；
- Agent 超时但 Task 本身正确。

---

## 9. 证据纪律

本项目的自动化目标不是“跑到绿色”，而是形成可审计的真实证据链。

### 9.1 L0/L1

必须记录真实命令、退出码和输出。

不能：

- 删除失败测试；
- 改小断言；
- 无条件 skip；
- 只跑更容易通过的子集；
- 把静态检查冒充运行验证。

### 9.2 L2/L3

只有真实银河麒麟宿主执行的证据才能声明相应 Host / Runtime 结论。

WSL2 结果不能写成：

```text
HOST_VERIFIED
```

当前 Skill 默认不自动执行 L2/L3。

### 9.3 PR 可复验证据

`.agent-runs/` 是本地执行证据，不天然等于 Reviewer 可访问证据。

如果 PR 正式声明某次 Gate 已通过，而 Reviewer 需要复核，应根据任务要求把必要证据发布为：

- repository evidence；或
- GitHub Actions artifact。

原始证据不能人工重写后冒充测试日志。

建议使用：

```text
raw log
+ evidence index
+ command
+ tested snapshot
+ passed/failed/skipped
+ exit code
+ duration
+ SHA256
```

并将一次验证运行命名为固定事件，例如：

```text
PR144-V2-L1-R1
```

避免使用“当前 duration”这类会随着后续重跑失效的动态证据表述。

---

## 10. 人工边界

Supervisor 设计目标不是完全取消人工，而是把人工集中到真正需要判断或权限的边界。

默认人工负责：

```text
分支创建 / 同步
        ↓
Codex + OpenCode 自动开发
        ↓
BATCH_COMPLETE + exit 0
        ↓
人工检查最终 diff / commit
        ↓
push
        ↓
PR / 外部 Review
        ↓
需要时再次启动 review-remediation Batch
        ↓
L2/L3 麒麟宿主验证
        ↓
merge / release
```

遇到以下情况 Supervisor 必须停止：

- 当前分支是 `main`；
- 需要创建/同步/rebase 分支；
- 环境归一化后仍真实缺依赖；
- 需求存在无法自行消除的歧义；
- 需要破坏性 Git 操作；
- workflow engine 本身损坏；
- 需要凭据、sudo 或交互授权；
- 缺少 L2/L3 麒麟真实证据；
- 同一失败反复出现且没有新证据。

停止状态：

```text
SUPERVISOR_STATUS: HUMAN_HANDOFF_REQUIRED
```

---

## 11. 常见问题排查

### 11.1 Codex 无法进入正确 WSL

先检查 Windows PowerShell：

```powershell
wsl -l -v
wsl --status
```

如果真实项目在 `Ubuntu-22.04`，但默认发行版为另一个旧 `Ubuntu`，可将正确发行版设为默认：

```powershell
wsl --set-default Ubuntu-22.04
```

然后重新启动 Codex。

### 11.2 `opencode` 找不到

不要立即重装。

先检查：

```bash
command -v opencode || true
bash -ic 'command -v opencode' 2>/dev/null || true
```

如果交互式 shell 能找到，属于 PATH 继承问题，由 Skill 的 NVM 动态发现处理。

### 11.3 明明安装了依赖，Batch 却报 ModuleNotFoundError

先确认解释器：

```bash
command -v python3
python3 -c 'import sys; print(sys.executable)'
```

再检查项目 `.venv`：

```bash
.venv/bin/python -m pip show <package>
```

若依赖在 `.venv` 中存在，但 Batch 用的是 `/usr/bin/python3`，应分类为：

```text
ENVIRONMENT_MISMATCH
```

不要重新安装依赖，也不要重建 Task/Batch。

### 11.4 Codex 看起来停止，但 Batch 还在跑

检查持久化状态：

```bash
find .agent-runs/codex-supervisor -type f -name 'status-*.env' -print
```

检查进程：

```bash
pgrep -af 'run_batch|opencode|orchestrator' || true
```

查看真实日志：

```bash
tail -f .agent-runs/codex-live-console.log
```

Codex 当前聊天 turn 结束不代表 Batch 失败。下一次调用 Supervisor 时应先 reattach，而不是重新启动。

### 11.5 `FINAL_BATCH_STATE` 是 COMPLETE，但没看到 Codex 最终报告

先读取 detached attempt 的 `status-*.env` 和 attempt log。

如果已经满足：

```text
FINAL_BATCH_STATE: BATCH_COMPLETE
BATCH_EXIT_CODE=0
```

则下一次 Supervisor 调用只应恢复并输出 Human Handoff，不能重新执行 Batch。

---

## 12. 模型使用建议

Codex 只是外层 Supervisor，主要实现工作仍由 OpenCode 多 Agent 工作流承担，因此没有必要长期使用最高推理档位。

当前实践建议：

| 场景 | 建议 |
|---|---|
| 简单环境检查 / Git 检查 | 轻量推理即可 |
| 日常 Supervisor 开发 | 中等推理档位 |
| 跨轨契约冲突 / 多次失败 / 复杂 Review | 临时提高推理能力 |
| 问题解决后 | 回到日常中等档位 |

原则是：**以能够稳定完成失败分类和工程判断的最低档位为默认。**

模型名称、可选档位和产品 UI 可能变化，因此本文不把某个具体模型名作为工作流契约。

---

## 13. 本地文件与 Git 管理

建议保持以下内容不提交：

```text
.agent-runs/
.codex-supervisor-backup-*/
```

Supervisor Skill 默认位于：

```text
$HOME/.codex/skills/
```

同样不属于仓库文件。

如果需要在本地试验 Codex 辅助文件，而暂时不想污染仓库，可使用：

```text
.git/info/exclude
```

而不是为了单人本地配置修改团队 `.gitignore`。

但已经被项目正式采纳的共享开发文档，应正常进入 Git 管理。

---

## 14. 版本演进

### v1.0

完成最初的 Codex 外层 Supervisor：

- 读取项目源；
- 复用 Task/Batch；
- 执行现有 OpenCode workflow；
- 非 0 日志诊断；
- 成功后 Human Handoff；
- 保留 push / PR / L2/L3 / merge / release 人工边界。

### v1.1

解决非交互环境继承问题：

- 自动使用仓库 `.venv`；
- 动态发现 NVM/OpenCode；
- 新增 `ENVIRONMENT_MISMATCH`；
- 防止把“已有依赖但解释器错误”误报成依赖缺失；
- 禁止为通过 Gate 静默安装项目依赖。

### v1.2

解决 Desktop Codex 长任务生命周期问题：

- 长 Batch detached 执行；
- 持久化 runner / PID / status / attempt log；
- 启动前 recovery check；
- 运行中短轮询；
- Codex turn 结束后可 reattach；
- 防止重复启动正在运行或已经完成的 Batch；
- 不再根据“Codex 没有最终回复”判断 Batch 失败。

---

## 15. 后续可扩展方向

当前 v1.2 重点解决 WSL 内 L0/L1 自动开发。

后续可以独立扩展：

### Kylin Runtime Supervisor

通过 SSH 而不是 GUI 自动化连接真实麒麟测试机，负责：

```text
校验目标 OS / snapshot / SHA
        ↓
部署当前代码
        ↓
执行 runtime_commands
        ↓
systemd / journal / UDS / SDK 检查
        ↓
采集 stdout / stderr / exit code
        ↓
生成 L2 evidence
        ↓
人工复核
```

该能力应与现有 `opencode-batch-supervisor` 解耦，避免把 WSL 开发与真实宿主证据边界混为一体。

### PR / Review 自动化

理论上可以扩展自动 push、PR 更新、Review 拉取，但需要额外权限、安全规则和 SHA gate。

在没有专门设计前，当前 Skill 保持人工 push/PR/merge 边界。

---

## 16. 一句话操作规则

日常使用只需要记住：

```text
人工准备正确分支
→ Codex 选择 WSL 仓库
→ $opencode-batch-supervisor 开工
→ Supervisor 自动归一化环境
→ OpenCode 按原 Task/Batch 工作流开发
→ 非 0 自动诊断
→ detached 长任务可恢复
→ BATCH_COMPLETE + exit 0
→ 人工检查、push、PR、L2/L3、merge
```

**任何时候都以仓库事实、真实退出码、Reviewer 结论和可复验证据为准，不以 Agent 自述成功替代证据。**
