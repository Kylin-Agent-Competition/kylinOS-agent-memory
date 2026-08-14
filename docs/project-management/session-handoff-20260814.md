# 会话交接文档：Day7（A 轨）偏好抽取深化完成 + Day8 就绪

生成：2026-08-14 ｜ 状态：PR #27（Day6）已合并进 main（2e3f919）；Day7 A 轨任务代码/测试/证据全部完成（feat/day7-preference-extraction @ 本地 HEAD 已推送待合并）；Day8 可开始

## 一、项目基础

麒麟 OS AI Agent 记忆系统（Kylin-Agent-Competition/kylinOS-agent-memory，GitHub 公开仓库）。多源融合偏好与知识记忆系统：不重写聊天 UI/模型运行时/官方向量设施，新增 MemoryClient（UDS 连 Python Memory Service）+ 偏好/知识/版本/冲突/遗忘/混合检索/精准遗忘治理。

技术栈：C++17（dlopen/dlsym SDK Bridge）+ pybind11 + Python 3.10/3.12 + asyncio + Pydantic v2 + SQLite/SQLAlchemy/Alembic/FTS5 + UDS 长度前缀 JSON + CMake + pytest/CTest + Qt5/QML（C 轨）。

环境：Windows + WSL2；实测宿主银河麒麟 V11 x86_64（VirtualBox VM，Runtime 1.3.0）。仓库 WSL 路径 /home/fff/projects/kylinOS-agent-memory。

## 二、当前进度（关键）

### PR #27（Day6）已合并 ✅

- main = 2e3f919（"A-feat(day6): … (#27)"，squash 合入），本地 main 已同步。
- 旧分支 feat/day6-event-quality-pipeline 已不再需要（内容全部在 main）。

### PR（Day7）——feat/day7-preference-extraction @ 本地 HEAD（已推送）

- 基线：main @ 2e3f919。
- 交付：偏好抽取深化三项（见下）+ 任务卡 docs/day7/01_task_card.md + 本地 L1 证据（evidence/l1/day7_pref_extraction_local.log，224 passed + 47 skipped）+ 麒麟 VM L2 证据（evidence/l2-kylin-vm/day7_verify_latest.log）+ evidence/index.yaml 条目 D7-A-PREF-EXTRACTION（HOST_VERIFIED/E4）。
- ⚠️ **PR #36 REWORK 修复中（本轮）**：HIGH-01（TABLE 20 临时原句指令式规则入口）、HIGH-02（required confidence reject 不降级 0.5）、MEDIUM-01（矛盾规范化）已修复并本地验证（224 passed + 47 skipped）；TD-A-D7-CACHE-USER-DIMENSION / TD-A-D7-LLM-HANG-DEGRADE 已登记；**VM L2 待用最终修复 commit 重跑**（届时更新 tested_commit 与 L2 日志）。

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

已关闭且**不得重开**（除非重新引入）：假 Tool 成功 / 敏感 fail-open / provenance 可伪造 / candidate 被当 verified / 跨用户泄漏 / Runtime evidence 与生产代码不匹配。

D7 新增可审项：
- 缓存返回深拷贝、空结果缓存、缓存键含内容指纹（防同 ID 不同内容串键）——有测试
- 超时后后台线程结果丢弃（ThreadPoolExecutor 标准语义），不阻塞 Turn 处理——有测试
- 字段级降级只作用于可选字段，R4 必需字段隔离不弱化——有负向测试
- close() 幂等，close 后规则路径仍独立工作——有测试

## 四、技术债登记（TECHNICAL_DEBT_REGISTER.md）

| TD | 状态 | 备注 |
|----|------|------|
| TD-A-005-01~09 | Open | Day4/5 遗留（超时中断/并行策略/维度副作用/模型名/启动降级等） |
| TD-A-D6-EXEC-RACE | Open（非阻断） | executor shutdown 竞态（D7 全量 -v 曾一次偶发 test_server_lifecycle 复跑即绿） |
| TD-A-D6-TOOL-PARTIAL | Open（非阻断） | partial 保守 fail-safe（漏记非错记） |
| TD-A-D6-LLM-TOOL-INPUT | Open（非阻断） | knowledge LLM 输入绑定 success ToolResult.result（D7 只动偏好路径，验收条件保持） |

D7 未新增 TD（预期内）：缓存/线程生命周期风险点有测试覆盖，未登记。

## 五、任务台账（A 轨刘依枫）

D1-D7 全部完成。D8 起待做（按 [[tasks-75-track-a]]）：
- D8：Fact/Procedure/Case/Template 知识结构化抽取；失败 Tool/取消 Tool/模型推测不同抽取策略；失败降级测试 → 知识抽取留证据与适用条件，失败 Tool 不生成成功知识
- 比赛评分主线（优先）：偏好准确率 ≥85%、知识检索召回 ≥85%、检索响应 ≤500ms、冲突正确率 ≥88%、真实应用案例、麒麟适配、完整端到端演示链

## 六、环境与操作须知

- **push 用 Windows git**：`"/mnt/d/Git/cmd/git.exe" -C "//wsl.localhost/Ubuntu/home/fff/projects/kylinOS-agent-memory" push origin <branch>`
- **本地 pytest**：`/tmp/day7-venv/bin/python -m pytest memory-service/tests/`（venv 由 `/usr/bin/python3 -m venv /tmp/day7-venv && pip install -r memory-service/requirements.txt` 创建；/tmp 易失，重建即可）
- **麒麟 VM 验证**：`cd /mnt/shared && git rev-parse HEAD` → `PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -v`；VM 需手动开机
- **编码坑**：bash heredoc 展开反引号/`$`；write_file 对 `password=[redacted]` 模式脱敏；UTF-8 md 用 write_file + `[IO.File]::ReadAllText(path, UTF8)` 读
- **WSL↔VM**：/mnt/shared 即 WSL 仓库（vboxsf），WSL 侧更新 VM 直接可见；VM 无外网，勿在 VM 内 git fetch

## 七、下一步（按优先级）

1. 提交 PR（feat/day7-preference-extraction），D 主审；安全/评测影响 E 补审（VM L2 已具备）
2. 开始 Day8（A 轨）：知识结构化抽取（六类知识 + 失败 Tool 不同策略 + 失败降级测试），依赖 E 轨知识 Schema（§3.3）与 C 轨 Tool 事件取证
3. 更新交接文档（把 Day7 PR 合并状态写入）——需要时说一声

## 八、关键位置

- 任务卡：`docs/day7/01_task_card.md`（含契约演进记录）
- 代码：`memory-service/providers/preference_rules.py`、`memory-service/providers/extraction_provider.py`
- 测试：`memory-service/tests/test_preference_rules.py`（24）、`memory-service/tests/test_extraction_provider_d7.py`（26）
- 证据：`evidence/l2-kylin-vm/day7_verify_latest.log`（VM 264 passed，被测 e3a3f9e，**PR #36 修复后待重跑**）、`evidence/l1/day7_pref_extraction_local.log`（本地 224 passed + 47 skipped）、`evidence/index.yaml`（D7-A-PREF-EXTRACTION，HOST_VERIFIED/E4，L2 tested_commit 待更新）
- 契约：`docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（§2.5/§2.9/§3.2 偏好）、`docs/day3/06_provider_contract_v1.md`（ExtractionProvider）、`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`
- 历史：`docs/project-management/session-handoff-20260813.md`（Day6）、`session-handoff-20260809.md`（Day4/5）
- 项目记忆（新会话自动加载）：architecture-v1-requirements / tasks-75-track-a / day4-pr17-round7-pushed / day1-4-session-archive / single-step-inputs-no-iteration
