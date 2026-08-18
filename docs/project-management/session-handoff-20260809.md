# 会话交接文档：Day4 PR #17 收尾 + Day5 就绪

生成时间：2026-08-09 ｜ 状态：Day4 PR #17 待 Reviewer 最终 APPROVE（CONDITIONALLY PASS_WITH_DEBT）；Day5 已完成并按架构 v1 对齐，麒麟 VM 验证全绿

---

## 一、项目基础信息

- **项目**：麒麟 OS AI Agent 记忆系统（Kylin-Agent-Competition/kylinOS-agent-memory，GitHub 公开仓库）。多源融合偏好与知识记忆系统：不重写聊天 UI/模型运行时/官方向量设施，新增 MemoryClient（UDS 连 Python Memory Service）+ 偏好/知识/版本/冲突/遗忘/混合检索/精准遗忘治理。
- **技术栈**：C++17（dlopen/dlsym SDK Bridge）+ pybind11 + Python 3.10/3.12 + asyncio + Pydantic v2 + SQLite/SQLAlchemy/Alembic/FTS5 + UDS 长度前缀 JSON + CMake + pytest/CTest + Qt5/QML（C 轨）。
- **运行环境**：开发在 Windows + WSL2（Ubuntu）；实测宿主为银河麒麟 V11 x86_64（VirtualBox VM，Runtime 1.3.0）。仓库 WSL 路径 `/home/fff/projects/kylinOS-agent-memory`；VM 挂载 `/mnt/shared`。
- **Agent**：Reasonix（Windows 侧），bash 工具宿主在 PowerShell / WSL bash 间不稳定切换——命令需按实际宿主选语法（报错提示 "Windows PowerShell" 时用 `;` 分隔、`Write-Host`、`Select-String`；能直接跑 `cd /home/... && ...` 时是 bash）。

## 二、当前进度与状态

### Day4 PR #17（feat/day4-bridge-provider-new @ 85b142a）—— 待 Reviewer 最终 APPROVE

- Review 结论：**CONDITIONALLY PASS_WITH_DEBT**（P0=0 / P1=0）。3 个最终 Gate：**Gate 1 ✅**（fixture 顺序验证全绿）、**Gate 2 ✅**（PR body 已直接 PATCH 更新，中文正常）、**Gate 3 ⏳**（Reviewer 批准 Day3 生命周期 Gate + 提交 APPROVE，外部动作，需提醒 Reviewer）。
- 第八轮 L2 证据：tested_commit=`939bc2d`、evidence_commit=`03fa9ae`、checksum=`4021b1cc`；CTest 6/6、pytest 38+13+1=52 无 Skip、Smoke 11、生命周期 4 路径、FAILURES=0。
- PR 数据：71 commits / 29 files（+3677/-8），Base main@a658b06，mergeable=true，Repository Baseline Check SUCCESS。
- 技术债 TD-A-005-01~08 已登记（docs/technical-debt/TECHNICAL_DEBT_REGISTER.md），按 PASS_WITH_DEBT 延期；**详细说明（产生原因/影响/延期依据/风险升级条件/验收标准/接受结论）已写入文档（提交 85b142a）**。

### Day5（feat/day5-minimal-vertical-chain @ 1df7413）—— 已完成，未推送

- 内容：`memory-service/embedding/`（embedding_service.py / protocol.py / server.py）+ 测试（test_embedding_service.py 11 项、test_protocol.py 12 项、test_embedding_service_real.py 8 项）。
- 已按总体架构 v1 对齐：IPC 协议为 4.4 envelope（protocol_version/request_id/trace_id/method/deadline_ms/payload），方法 memory.embed/embed_batch/ping/health；降级=明确空向量+degraded（非假样例）；Bridge 调用在线程池不阻塞聊天线程。
- **麒麟 VM 验证全绿（2026-08-08）**：真实 SDK 测试 8/8 无 Skip（768 维/中文/空串/batch/envelope 分发/health/降级）+ 本地 23/23 + 端到端 UDS（health bridge_loaded=true、embed dim=768）。
- **未推送、未回填 index.yaml**（等 Day4 合并 main 后走 Day5 PR，届时 tested_commit=1df7413）。

### main 状态

`origin/main = a658b06`（#21 UDS Echo + #24 E 轨 Gate0 评审已合并）。本地 main 指针曾落后（以 origin/main 为准）。

## 三、架构要求核心（写任务卡/PR 的依据）

详见项目记忆 [[architecture-v1-requirements]]，要点：
- **四项核心指标**：偏好准确率≥85%、知识检索召回≥85%、检索响应≤500ms、冲突正确率≥88%。
- **设计原则**：聊天优先（服务故障时聊天继续+降级）、原文隔离（UI 存原文，Memory Context 只进 model_request）、结构化真源（SQLite 为主 Vector 可重建）、异步写入（Post-Turn 不在 UI 线程做 Embedding）、证据优先、最小权限、一次完整交付。
- **Memory Service 分层**：IPC Gateway → Application Service → Domain → Repository → Provider → Worker → Evaluation → Observability；目录 `memory-service/app/{api,schemas,domain,services}/`（D5 阶段 A 轨用 `memory-service/embedding/` 最小结构，后续演进）。
- **IPC 契约（冻结）**：UDS + 4 字节大端长度前缀 + UTF-8 JSON envelope `{"protocol_version":"1.0","request_id","trace_id","method","deadline_ms","payload"}`；方法 memory.retrieve/observe_turn/observe_tool/preference.list|update/conflict.resolve/forget.preview|execute/health。**不得自行改协议**。
- **延迟预算**：IPC≤20ms、SQLite/FTS≤80ms、Embedding≤180ms、Vector≤120ms、融合≤80ms、总计≤500ms。
- **降级红线（TABLE 54）**：失败返回固定样例=假实现；正确降级=真实结果或空上下文。
- **SOP 18 步**：任务卡→上下文→契约→影响→安全→环境→方案 Gate→接口冻结→分支开发→候选检查→L0→L1→独立审查→L2→问题分类→证据 Gate→L3→审批归档。人主导，Agent 不替代架构决策/Runtime/批准。

## 四、任务台账（75 项）与 A 轨进度

详见项目记忆 [[tasks-75-track-a]]。A 轨（刘依枫=用户）D1-D15：**D1-D4 已完成**（基线/冒烟/契约/骨架，PR #17）、**D5 已完成**（首个真实垂直链路，代码+VM 验证全绿）、D6-D15 待做（清洗管线/偏好抽取/知识抽取/性能基线/缓存失效/健康/回归/性能报告/发布锁定）。

B 轨（高翌哲）Vector 检索、C 轨（刘承恩）OS Agent/QML、D 轨（周子腾，Reviewer1）基础设施、E 轨（谢嘉然，Reviewer2）业务/安全/评测。审查规则：A 主审 D、安全/数据影响 E 补审；双审=Bridge 敏感数据/跨架构 ABI/检索指标影响。

## 五、硬性约束与证据门禁（麒麟实测）

- **SDK 硬限制**：同进程 dlclose→dlopen 会 Abort；destroy_session→create_session 会挂起；create_session 后必须先成功 embed() 才能安全 destroy。→ Provider 进程级单例共享 Bridge，close 只释引用不 dlclose；dlsym/init_session 失败进不可恢复 fatal 终态（ERR_FATAL_FAILURE 需进程重启）。
- **错误模型（最终）**：dlsym→ERR_DLSYM_FAILED→Provider ERR_SDK_NOT_LOADED；init_session→ERR_SESSION_INIT→ERR_SESSION_FAILED（首次保留原始码+fatal）；fatal 后重试→ERR_FATAL_FAILURE（Provider 0x0203）；destroy 终态→BridgeSessionDestroyedError→ERR_SESSION_DESTROYED。
- **证据硬门禁**：L2 日志必须脚本自动生成、含 Step1 原始输出，Commit/rev-parse HEAD/index.yaml tested_commit/实际被测代码四项一致；禁止无证据上限声明；未实测标注 UNTESTED/HOST_VERIFIED/ABI_VERIFIED。
- **测试可信度**：test_provider_failure_recovery.py 用 fixture 注入假模块 + teardown 无条件恢复 sys.modules（不得退回模块级注入）；全量 pytest 单进程必须顺序无关。
- **改生产代码/正式测试后必须重跑麒麟 VM L2 并回填 tested_commit/checksum**（证据门禁）。

## 六、环境与操作须知

- **git push 必须用 Windows git**（WSL git 无凭据）：`"/mnt/d/Git/cmd/git.exe" -C "//wsl.localhost/Ubuntu/home/fff/projects/kylinOS-agent-memory" push origin <branch>`。
- **GitHub API 写操作**（改 PR body/评论等）：Windows Credential Manager 有 `git:https://github.com` 凭据（lyf-1213），PowerShell CredRead 读取后用于 REST API；**注意 PowerShell 5.1 的 Invoke-RestMethod 发 body 默认 Latin-1，中文会变 `?`——必须 `[Text.Encoding]::UTF8.GetBytes($json)` 传字节 + ContentType "application/json; charset=utf-8"**。
- **麒麟 VM 验证**：`cd /mnt/shared && git rev-parse HEAD && bash scripts/verify_day4_vm.sh`（Day4 唯一入口）；Day5 用 `PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 python -m pytest memory-service/tests/test_embedding_service_real.py`。VM 需手动开机；/tmp 易失（venv 需重建：`python3 -m venv /tmp/day4-venv && pip install pybind11 pytest`）。
- **PowerShell 编码坑**：重定向写 UTF-16/CRLF → 用 Python 写文件；写 .ps1 脚本必须全 ASCII（中文用 \uXXXX 转义）否则 GBK 乱码；写 UTF-8 md 用 write_file + `[IO.File]::ReadAllText(path, UTF8)` 读取。
- **WSL↔VM**：无网络互通，用 vboxsf 共享 /mnt/shared；stat 缓存致 git 误报 → Step1 先 git update-index --refresh。

## 七、下一步动作清单（按优先级）

1. **提醒 Reviewer 完成 Gate 3**（批准 Day3 生命周期 Gate + APPROVE PR #17）——外部依赖，用户侧推动。
2. **Day4 合并 main 后**：Day5 分支 rebase 最新 main（merge 非 rebase 处理冲突；基线 origin/main；只保留 Day5 新增 7 文件）→ 建 Day5 证据条目（index.yaml 新 id，tested_commit=1df7413、VM 验证 8+23+端到端）→ Windows git 推送 feat/day5-minimal-vertical-chain → 走 Day5 PR（按 PR 模板写描述）。
3. **Day6（A 轨下一任务）**：统一事件清洗/时间状态标准化/质量评分管线 + 结构化抽取 Provider + Pydantic 非法输出降级 + 内容指纹/重复检测（见 [[tasks-75-track-a]] D6-A）。开工前按 SOP 建任务卡、契约分析（依赖 E 轨业务 Schema 冻结）。
4. 若 Reviewer 再 REWORK：按 day-pr-review skill 逐项修复 → VM 重跑 verify → 回填 index.yaml → 推送。

## 八、关键文件与证据位置

- 架构基线：团队架构文档 v1（docx，`.reasonix/attachments/`）+ 75 项台账（xlsx）——已读入记忆 [[architecture-v1-requirements]] / [[tasks-75-track-a]]
- Day4 证据：`evidence/l2-kylin-vm/day4_verify_latest.log`（第八轮，被测 939bc2d）、`evidence/index.yaml`（EMBED-CALL-003）
- 历史归档：`docs/project-management/session-archive-day1-4.md`、记忆 [[day1-4-session-archive]]
- 契约/文档：`docs/day3/06_provider_contract_v1.md`、`docs/day4/08_bridge_provider_skeleton.md`、`cpp-bridge/bridge_error_contract.h`、`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`
- 验证脚本：`scripts/verify_day4_vm.sh`（Day4）、Day5 测试 `memory-service/tests/test_embedding_service_real.py` 等
- 项目记忆索引（本会话自动加载）：architecture-v1-requirements / tasks-75-track-a / day4-pr17-round7-pushed / day1-4-session-archive / single-step-inputs-no-iteration
