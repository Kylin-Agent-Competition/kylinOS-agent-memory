# 会话交接文档：Day7（A 轨）偏好抽取深化完成 + PR #36 两轮 REWORK 闭环 + Day8 就绪

生成：2026-08-14（更新） ｜ 状态：PR #27（Day6）已合并进 main（2e3f919）；Day7 A 轨任务代码/测试/证据全部完成并推送（feat/day7-preference-extraction @ 7d8ab45）；PR #36 两轮 REWORK 已修复；L1 229+47、VM L2 276 @ e5c52e6 证据闭环；**剩余：PR #36 Body 手动同步（MEDIUM-06）**；Day8 可开始

## 一、项目基础

麒麟 OS AI Agent 记忆系统（Kylin-Agent-Competition/kylinOS-agent-memory，GitHub 公开仓库）。多源融合偏好与知识记忆系统：不重写聊天 UI/模型运行时/官方向量设施，新增 MemoryClient（UDS 连 Python Memory Service）+ 偏好/知识/版本/冲突/遗忘/混合检索/精准遗忘治理。

技术栈：C++17（dlopen/dlsym SDK Bridge）+ pybind11 + Python 3.10/3.12 + asyncio + Pydantic v2 + SQLite/SQLAlchemy/Alembic/FTS5 + UDS 长度前缀 JSON + CMake + pytest/CTest + Qt5/QML（C 轨）。

环境：Windows + WSL2；实测宿主银河麒麟 V11 x86_64（VirtualBox VM，Runtime 1.3.0）。仓库 WSL 路径 /home/fff/projects/kylinOS-agent-memory。

## 二、当前进度（关键）

### PR #27（Day6）已合并 ✅

- main = 2e3f919（"A-feat(day6): … (#27)"，squash 合入），本地 main 已同步。
- 旧分支 feat/day6-event-quality-pipeline 已不再需要（内容全部在 main）。

### PR #36（Day7 评审）——两轮 REWORK 已修复并推送 ✅

- 分支 `feat/day7-preference-extraction`，HEAD `7d8ab45`（19 commits，已推送，工作区干净）。
- **第一轮 REWORK**（commit `8e93118`）：HIGH-01 指令式规则入口（TABLE 20 原句主链可抽取）/ HIGH-02 required confidence reject（删 0.5 降级）/ MEDIUM-01 矛盾规范化 + TD-A-D7-CACHE-USER-DIMENSION、TD-A-D7-LLM-HANG-DEGRADE 登记。
- **第二轮 REWORK**（commit `e5c52e6`）：HIGH-03 strict confidence（`Field(strict=True)`，bool/str 不再自动转换）/ MEDIUM-05 optional None 降级（方案 A）/ MEDIUM-08 指令模式收紧（时态词必选）；MEDIUM-07 evidence_commit 修正。
- **证据闭环**：L1 229 passed + 47 skipped（被测 e5c52e6，checksum 77e8229a…）+ **VM L2 276 passed / 0 skipped（被测 e5c52e6，5.97s，checksum b52d437a…）**——tested_commit == 生产代码最终版本。
- ⚠️ **剩余：MEDIUM-06 GitHub PR #36 Body 手动同步**——token 401 无法 API PATCH；仓库 `docs/day7/02_pr_description.md` 已是最新，由宿主复制粘贴到 PR 页面（测试数量/L1/L2/tested_commit/TD/changed files 全部一致）。

### Day7 A 轨交付内容（xlsx R37）

1. **规则+抽取 Provider 协同**（providers/preference_rules.py 新增 + extraction_provider.py 增强）：
   - 偏好六类识别（架构 TABLE 19：presentation/tool_selection/workflow/safety/environment/scene_specific）
   - 临时指令 vs 长期偏好（TABLE 20 + E 轨 Schema §3.2：is_temporary/should_persist）
   - scope 推导（E 轨 §2.9 五值：global/topic/tool/session/time_window）
   - 类别键派生（§3.2 preference_key：response.language / scene.meeting.preference / safety.confirmation 等）+ explicitness（§2.5）
   - 规则+LLM 合并去重（同 key 规则优先，dedup/conflict 进 audit）
2. **缓存/超时/非法字段降级**：
   - LRU 抽取缓存（键=kind+source_event_id+内容指纹；深拷贝防污染；空结果缓存；TTL/容量可配；stats）
   - LLM 显式超时包装（llm_timeout_ms，超时→空候选+audit，Day3 契约降级不阻塞）
   - 可选字段非法值降级（confidence/scope/category/explicitness/布尔→默认值+audit；必需字段缺失仍 R4 候选级拒绝）
3. **偏好字段级评测统一结果格式**（供 E 轨 D7 偏好评测）：
   - PreferenceExtractionOutput（event_id/provider_mode/candidates/cache_hit/llm_timeout/duration_ms）
   - to_evaluation_record()（字段级：key/value/category/scope/confidence/explicitness/is_temporary/should_persist/evidence/source_event_id/memory_status）
   - export_preference_records()（JSONL 导出）

### 契约演进（已记录在 docs/day7/01_task_card.md）

- PreferenceCandidate.scope：Day3 global/session/project → E 轨 §2.9 五值（global/topic/tool/session/time_window）。
  依据：E 轨 Schema v0.1 为权威业务 Schema；Day3 契约标注"待架构文档确认后调整"。
- PreferenceCandidate 新增字段：category/explicitness/is_temporary/should_persist（均带默认值，向后兼容）。

## 三、Reviewer 关注点（下会话参考，勿重开已关闭问题）

已关闭且**不得重开**（除非重新引入）：假 Tool 成功 / 敏感 fail-open / provenance 可伪造 / candidate 被当 verified / 跨用户泄漏 / Runtime evidence 与生产代码不匹配 / confidence 自动类型转换（strict 已修）/ 指令模式误报（时态词必选已修）。

PR #36 两轮已关闭项（Reviewer 明确 CLOSED）：HIGH-01 / HIGH-02 / MEDIUM-01；两 TD 合法保留（PASS_WITH_DEBT 依据）。

D7 新增可审项：
- 缓存返回深拷贝、空结果缓存、缓存键含内容指纹（防同 ID 不同内容串键）——有测试
- 超时后后台线程结果丢弃（ThreadPoolExecutor 标准语义），不阻塞 Turn 处理——有测试
- 字段级降级只作用于可选字段，R4 必需字段隔离不弱化（confidence strict 为 required reject）——有负向测试
- optional 显式 None → 字段级降级 + audit；字段缺失走 Pydantic 默认值（无 audit）——有测试
- close() 幂等，close 后规则路径仍独立工作——有测试
- 综合验证 29/29 PASS（两轮 Review 全部代码项）——docs/day7/04_final_checklist.md

## 四、技术债登记（TECHNICAL_DEBT_REGISTER.md）

| TD | 状态 | 备注 |
|----|------|------|
| TD-A-005-01~09 | Open | Day4/5 遗留（超时中断/并行策略/维度副作用/模型名/启动降级等） |
| TD-A-D6-EXEC-RACE | Open（非阻断） | executor shutdown 竞态（D7 全量 -v 曾一次偶发 test_server_lifecycle 复跑即绿） |
| TD-A-D6-TOOL-PARTIAL | Open（非阻断） | partial 保守 fail-safe（漏记非错记） |
| TD-A-D6-LLM-TOOL-INPUT | Open（非阻断） | knowledge LLM 输入绑定 success ToolResult.result（D7 只动偏好路径，验收条件保持） |
| TD-A-D7-CACHE-USER-DIMENSION | Open（可作 PASS_WITH_DEBT 合法债务） | 缓存键缺 user 维度（PR #36 MEDIUM-02）；单用户端侧；契约加 user_id 后缓存键必须升级；多用户前必须关闭 |
| TD-A-D7-LLM-HANG-DEGRADE | Open（可作 PASS_WITH_DEBT 合法债务） | LLM 永久挂死 → 永久 busy-skip（PR #36 MEDIUM-03）；真实 LLM 接入前需 worker reset/executor 重建/health recovery 之一 |

D7 新增 TD 共 2 个（上述两项，均已正式登记于 docs/technical-debt/TECHNICAL_DEBT_REGISTER.md，带关闭条件）。

## 五、任务台账（A 轨刘依枫）

D1-D7 全部完成。D8 起待做（按 [[tasks-75-track-a]]）：
- D8：Fact/Procedure/Case/Template 知识结构化抽取；失败 Tool/取消 Tool/模型推测不同抽取策略；失败降级测试 → 知识抽取留证据与适用条件，失败 Tool 不生成成功知识
- 比赛评分主线（优先）：偏好准确率 ≥85%、知识检索召回 ≥85%、检索响应 ≤500ms、冲突正确率 ≥88%、真实应用案例、麒麟适配、完整端到端演示链

## 五·一、核心原则（新会话必读）

**架构红线（不得违反）**：
- R3：source_event_id 系统可信 provenance，LLM 不得伪造/覆盖
- R4：非法候选不进业务真源（candidate-level reject + audit）；required 字段（key/value/evidence/confidence）类型错误必须 reject，不得自动类型转换（strict）
- R5：敏感 fail-open 禁止——规则/LLM 双路径复核 value+evidence（偏好）/fact+conditions（知识）
- B1：成功知识必须建立在真实 success ToolResult 之上（失败/取消/超时/partial 不产生成功知识）
- B2：memory_status 恒 candidate，LLM 不得自封 verified/active

**降级红线（TABLE 54/35）**：不可用→结构化错误+真实降级；无固定样例假实现；LLM 超时/异常→空候选+audit 不阻塞

**技术约定**：Pydantic v2（extra=forbid，候选模型）；规则优先 + LLM 结构化抽取 + Pydantic 校验；确定性（同输入同输出）

**证据门禁**：麒麟验证命令与证据硬门禁——tested_commit 必须绑定被测代码；evidence_commit = 证据正式回填仓库的 commit（≠ tested_commit）；沙箱不能冒充宿主证据；L2 必须在麒麟 VM 真实执行

## 六、环境与操作须知

- **push 用 Windows git**：`"/mnt/d/Git/cmd/git.exe" -C "//wsl.localhost/Ubuntu/home/fff/projects/kylinOS-agent-memory" push origin <branch>`
  - 代理 127.0.0.1:7890 不可达时用直连：追加 `-c http.proxy= -c https.proxy=`（曾多次成功；网络波动时重试）
- **本地 pytest**：`/tmp/day7-venv/bin/python -m pytest memory-service/tests/`（venv 由 `/usr/bin/python3 -m venv /tmp/day7-venv && pip install -r memory-service/requirements.txt` 创建；/tmp 易失，重建即可）
- **麒麟 VM 验证**：`cd /mnt/shared && git rev-parse HEAD` → `PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -v`；VM 需手动开机；结果用 `tee evidence/l2-kylin-vm/day7_verify_latest.log` 落盘共享目录
- **编码坑**：bash heredoc 展开反引号/`$`；write_file 对 `password=[redacted]` 模式脱敏；UTF-8 md 用 write_file + `[IO.File]::ReadAllText(path, UTF8)` 读
- **WSL↔VM**：/mnt/shared 即 WSL 仓库（vboxsf），WSL 侧更新 VM 直接可见；VM 无外网，勿在 VM 内 git fetch
- **GitHub API**：token 曾 401 过期（git credential 里 gho_ 已失效）；PR Body PATCH 需新 `github_pat_...`（Pull requests: Read+write）；push 走 Windows Credential Manager 正常
- **VM 访问探测**：SSH 127.0.0.1:2222（VM 内 sshd 通常未起，Connection refused）、guestcontrol 需凭据、VRDP off——L2 通常需宿主在 VM 内执行

## 七、下一步（按优先级）

1. **PR #36 Body 手动同步**（MEDIUM-06，宿主操作）：复制 `docs/day7/02_pr_description.md` 全文粘贴到 PR #36 编辑页（token 401 无法代更；更新 token 后可代 PATCH）
2. **开始 Day8（A 轨）**：知识结构化抽取（六类知识 + 失败 Tool 不同策略 + 失败降级测试），依赖 E 轨知识 Schema（§3.3）与 C 轨 Tool 事件取证
3. 更新交接文档（把 Day7 PR 合并状态写入）——需要时说一声

## 八、关键位置

- 任务卡：`docs/day7/01_task_card.md`（含契约演进 + PR #36 两轮落实记录）
- PR 描述：`docs/day7/02_pr_description.md`（最新 PR Body 源，同步用）
- 复审响应：`docs/day7/03_review_response_pr36.md`（两轮 REWORK 逐项证据）
- 最终核对：`docs/day7/04_final_checklist.md`（14 项证据链 + 综合验证 29/29）
- 代码：`memory-service/providers/preference_rules.py`、`memory-service/providers/extraction_provider.py`
- 测试：`memory-service/tests/test_preference_rules.py`（24）、`memory-service/tests/test_extraction_provider_d7.py`（43）
- 证据：`evidence/l2-kylin-vm/day7_verify_latest.log`（VM **276 passed @ e5c52e6**，checksum b52d437a…，含元数据头）、`evidence/l1/day7_pref_extraction_local.log`（本地 229 passed + 47 skipped，被测 e5c52e6，checksum 77e8229a…）、`evidence/index.yaml`（D7-A-PREF-EXTRACTION，HOST_VERIFIED/E4，tested_commit e5c52e6，evidence_commit 6b27ec5）
- 契约：`docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（§2.5/§2.9/§3.2 偏好）、`docs/day3/06_provider_contract_v1.md`（ExtractionProvider）、`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`
- 历史：`docs/project-management/session-handoff-20260813.md`（Day6）、`session-handoff-20260809.md`（Day4/5）
- 项目记忆（新会话自动加载）：architecture-v1-requirements / tasks-75-track-a / day4-pr17-round7-pushed / day1-4-session-archive / single-step-inputs-no-iteration
