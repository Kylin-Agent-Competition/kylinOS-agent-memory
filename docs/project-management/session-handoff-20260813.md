# 会话交接文档：Day6 PR #27 全部收口待合并 + Day7 就绪

生成：2026-08-13 ｜ 状态：Day6（A 轨）代码与文档全部完成，Reviewer 第四轮 REWORK 5 项收口已交付（b9dd917 已推送）；PR #27 待用户合并后即进入 PASS_WITH_DEBT 复核；Day7 可开始

## 一、项目基础

麒麟 OS AI Agent 记忆系统（Kylin-Agent-Competition/kylinOS-agent-memory，GitHub 公开仓库）。多源融合偏好与知识记忆系统：不重写聊天 UI/模型运行时/官方向量设施，新增 MemoryClient（UDS 连 Python Memory Service）+ 偏好/知识/版本/冲突/遗忘/混合检索/精准遗忘治理。

技术栈：C++17（dlopen/dlsym SDK Bridge）+ pybind11 + Python 3.10/3.12 + asyncio + Pydantic v2（Day6 引入）+ SQLite/SQLAlchemy/Alembic/FTS5 + UDS 长度前缀 JSON + CMake + pytest/CTest + Qt5/QML（C 轨）。

环境：Windows + WSL2；实测宿主银河麒麟 V11 x86_64（VirtualBox VM，Runtime 1.3.0）。仓库 WSL 路径 /home/fff/projects/kylinOS-agent-memory。

## 二、当前进度（关键）

### PR #27（Day6）——待用户合并，Reviewer 预期 PASS_WITH_DEBT

- 分支：`feat/day6-event-quality-pipeline @ b9dd917`（已推送，ahead 10 / behind 0，与最新 main 同步）
- **Reviewer 四轮历程**：BLOCKED（12 项）→ BLOCKED（收敛 4 项）→ REWORK（5 项收口）→ 预期 PASS_WITH_DEBT
- 第四轮收口（b9dd917）：① 同步 main（merge 4dd7c0e，不碰 Day6 代码）；② payload_security_checked 契约补入 MEMORY_BUSINESS_SCHEMA_V0.1.md；③ EMBED-CALL-005 details 旧描述清除；④ Task Card 三处修正；⑤ 登记 TD-A-D6-LLM-TOOL-INPUT
- **用户已确认：收口完成后即合并 PR #27**（"详细说明在 comment 里"——PR comment 中已有 Reviewer 说明）

### Day6 交付内容（memory-service/pipeline/ + providers/extraction_provider.py）

- `schemas.py`：MemorySourceEvent（D3 契约八值状态/五级敏感/四值类型/五值处理状态/should_ignore/payload_security_checked）+ NormalizedEvent + QualityScore
- `cleaner.py`：EventCleaner（Pydantic 校验拒绝 + 时间 UTC 标准化 + 确定性）
- `sensitive.py`：敏感识别（API Key/JWT/密码 leetspeak/手机号/身份证/敏感路径 → critical/high/medium）
- `quality.py`：QualityScorer 六维评分 + 提取门控（阈值 0.5 + 可靠性下限 0.4）
- `fingerprint.py`：content_fingerprint / is_duplicate / event_duplicate_key
- `pipeline.py`：EventPipeline（清洗→敏感→指纹→评分→安全 Gate→质量 Gate，fail-close）
- `extraction_provider.py`：Day3 契约单参数接口 + 规则优先 + LLM 注入 + Pydantic 非法输出降级（audit 隔离）+ 系统可信 provenance + 防御性敏感复核 + **success Tool evidence 门控** + memory_status=candidate
- `memory-service/requirements.txt`：pydantic>=2,<3 + pytest + pybind11
- `memory-service/tests/`：13 文件，全量本地 162 passed + 47 skipped（顺序无关）；麒麟 VM 209 passed / 0 skipped / 0 failed（7.95s）

### main 状态

origin/main = 4dd7c0e（PR #23 = PR#21 R3 修复，最新）。已合入：Day4 (#17)、E轨 D3 (#26)、Day5 (#25)、PR#21 修复 (#23)。

## 三、关键新发现（环境，重要！）

### VM /mnt/shared 即 WSL 仓库的 vboxsf 挂载

- VM 配置文件 `D:\VMs\KylinV11\KylinV11.vbox`：
  - `SharedFolder name="kylinOS-agent-memory" hostPath="\\wsl.localhost\Ubuntu\home\fff\projects\kylinOS-agent-memory" autoMountPoint="/mnt/shared"`
- **含义**：VM 里 `/mnt/shared` 就是 WSL 仓库目录本身（vboxsf 共享），**WSL 侧代码更新后 VM 直接可见，无需在 VM 内 git fetch/pull**
- **VM 无外网**：`git fetch origin` 报 `Could not resolve host: github.com` / `RPC failed: curl 7 Recv failure` 会卡住——**不要在 VM 里跑 git fetch/checkout/reset 拉新代码**
- VM 里验证前只需：`cd /mnt/shared && git rev-parse HEAD` 确认分支/commit（本地分支已存在），然后直接跑 pytest

## 四、Reviewer 关注点（下会话参考，勿重开已关闭问题）

已关闭且**不得重开**（除非重新引入）：
- 假 Tool 成功 / 敏感 fail-open / provenance 可伪造 / candidate 被当 verified / 跨用户泄漏 / Runtime evidence 与生产代码不匹配

Review 范围声明：不应继续扩大为完整 Tool Execution Framework / rollback 系统 / Memory lifecycle / production executor 并发状态机 / Raw Payload 存储脱敏 / 真实 LLM 集成。

## 五、技术债登记（TECHNICAL_DEBT_REGISTER.md）

| TD | 状态 | 备注 |
|----|------|------|
| TD-A-005-01~08 | Open | Day4/5 遗留（超时中断/并行策略/维度副作用/模型名等） |
| TD-A-005-09 | Open | server 启动期 SDK 缺失降级（注入点已铺路，完整修复独立 PR） |
| TD-A-D6-EXEC-RACE | Open（非阻断） | executor shutdown 竞态（含当前保障/关闭条件） |
| TD-A-D6-TOOL-PARTIAL | Open（非阻断） | partial 保守 fail-safe（漏记非错记） |
| TD-A-D6-LLM-TOOL-INPUT | Open（非阻断） | knowledge LLM 输入绑定 success ToolResult.result（验收条件已记录） |

## 六、任务台账（A 轨刘依枫）

D1-D6 全部完成（基线/冒烟/契约/骨架/垂直链路/清洗质量管线）。D7 起待做（按 [[tasks-75-track-a]]）：
- D7-A 起：偏好/知识抽取深化、知识检索、性能基线、缓存失效、健康、回归、性能报告、发布锁定
- 比赛评分主线（优先）：偏好准确率 ≥85%、知识检索召回 ≥85%、检索响应 ≤500ms、冲突正确率 ≥88%、真实应用案例、麒麟适配、完整端到端演示链

## 七、环境与操作须知

- **push 用 Windows git**：`"/mnt/d/Git/cmd/git.exe" -C "//wsl.localhost/Ubuntu/home/fff/projects/kylinOS-agent-memory" push origin <branch>`
- **GitHub API 写**（改 PR/评论）：token 曾 401 失效——`git credential fill` 返回的 password 可能是过期的；push 走 Windows Credential Manager manager helper 正常。需要写 PR 时先测 `/user` 认证，失效则让用户手动更新
- **麒麟 VM 验证**：`cd /mnt/shared && git rev-parse HEAD`（应显示 WSL 侧分支/commit）→ `PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -v`；VM 需手动开机；/tmp 易失（venv 重建：python3 -m venv /tmp/day6-venv && pip install -r memory-service/requirements.txt）
- **编码坑**：写 .ps1 必须全 ASCII（中文 \uXXXX）；bash heredoc 会展开反引号/`$`（写含反引号内容用 write_file 或 Python 脚本）；write_file 对 `password=`/`$token=` 等模式会脱敏（用拼接规避）；UTF-8 md 用 write_file + [IO.File]::ReadAllText(path, UTF8) 读
- **WSL↔VM**：无网络互通，vboxsf 共享（见第三节）；stat 缓存致 git 误报 → Step1 先 git update-index --refresh

## 八、下一步（按优先级）

1. **用户合并 PR #27**（已确认要合并）——合并后 main 将含 Day6 全部内容
2. 合并后若需：将本地 Day6 分支对齐新 main（merge 非 rebase；此时 Day6 已合入 main，本地分支可删除或归档）
3. 开始 Day7（A 轨）：按 SOP 建任务卡——建议从比赛评分主线入手（偏好准确率/知识检索），依赖 B 轨检索契约（docs/day3/08_vector_retrieval_contract_v1.md，状态 REWORK 待 B 轨）
4. 更新交接文档（把 PR #27 合并状态写入）——需要时说一声

## 九、关键位置

- 证据：`evidence/l2-kylin-vm/day6_verify_latest.log`（第三轮，被测 1d98fdd，209 passed）、`evidence/index.yaml`（EMBED-CALL-005）
- 契约：`docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（含 payload_security_checked）、`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`、`docs/day3/06_provider_contract_v1.md`（ExtractionProvider）、`docs/day3/08_vector_retrieval_contract_v1.md`（B 轨检索）
- 技术债：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`
- 任务卡：`docs/day6/01_task_card.md`（含审查落实记录）
- 历史：`docs/project-management/session-handoff-20260809.md`（Day4/5 交接）、`docs/project-management/session-archive-day1-4.md`
- 项目记忆（新会话自动加载）：architecture-v1-requirements / tasks-75-track-a / day4-pr17-round7-pushed / day1-4-session-archive / single-step-inputs-no-iteration
