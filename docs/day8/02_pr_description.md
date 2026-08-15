# [D8-A] 知识结构化抽取——六类知识 + 失败/取消 Tool 不同策略 + 失败降级测试

> 分支：`feat/day8-knowledge-extraction`（基于 main @ `d37fb95`，PR #36 已合并；本 PR 1 commit：`25ec565`）
> PR 模板：架构 v1 附录 D（docs/architecture 18.1 PR 最小内容）

## 背景与目标

Day7（PR #36 已合并）交付偏好抽取深化（规则/Provider 协同 + 缓存/超时/非法字段降级 + 字段级评测统一结果格式）。Day8 按 75 项台账 **R42**（A 轨 D8：知识、冲突与生命周期——知识结构化抽取）实施知识抽取深化，目标为"**知识抽取保留证据与适用条件，失败 Tool 不生成成功知识**"：

1. **六类知识结构化抽取支持**：`KnowledgeCandidate` category 对齐 E 轨 Schema §2.6 六值（fact/workflow/case/template/constraint/failure_experience），新增六类结构化字段（架构 TABLE 21 必须保留的结构：证据/步骤/问题结果/模板正文/优先级/失败原因避免条件替代方案）
2. **失败 Tool、取消 Tool、模型推测不同抽取策略**：success → 六类成功知识（0.85）；failure → 仅 failure_experience（0.6）；cancelled/timeout/partial/未知 → 不沉淀；模型推测（无真实 success Tool 证据）→ LLM 成功知识门控拒绝（B1 + 架构 TABLE 22 Tool 事实高于模型自述）
3. **失败降级测试**：LLM 非法 category → fact+audit；结构化字段非法值 → 剥离+audit；必需字段 R4 拒绝；超时 → 空候选不阻塞；R5 敏感复核覆盖结构化字段

## 修改范围

- **`memory-service/providers/knowledge_rules.py`（新增）**：知识规则纯函数模块
  - 六类知识识别（failure > constraint > template > case > workflow > fact 优先级，正则确定性）
  - `tool_status_knowledge_policy`：Tool 状态 → 抽取策略（success/failure/skip）
  - `build_failure_experience`：失败 Tool → failure_experience 结构（失败原因/环境/避免条件/替代方案，0.6 中可信）
  - 置信度基线（TABLE 17：真实 Tool 成功=0.85 高；失败=0.6 中）
- **`memory-service/providers/extraction_provider.py`（增强）**：
  - `KnowledgeCandidate` v0.2：category 六值 + 12 个结构化可选字段（向后兼容）
  - `_extract_knowledge_rules`：按 Tool 状态分派（success → 六类识别 + evidence + conditions；failure → failure_experience；cancelled → skip）
  - `_degrade_knowledge_fields`：knowledge LLM 可选字段非法值降级（category 默认 fact；结构化字段剥离 + audit）
  - `_validate_candidate` R5 敏感复核覆盖全部结构化字段
  - `extract_knowledge_with_meta` / `KnowledgeExtractionOutput` / `to_knowledge_evaluation_record` / `export_knowledge_records`
- **`memory-service/tests/test_knowledge_extraction_d8.py`（新增，24 项）**：六类识别（6）/ Tool 状态策略（success/failure/cancelled/timeout/partial/mixed，8）/ 失败降级（category/结构化字段/R4/超时/R5，5）/ B1 门控（1）/ 评测输出（3）/ 契约保持（2）
- **`memory-service/tests/test_extraction_provider.py`（更新，2 项断言演进）**：
  - `test_rules_tool_failure_no_knowledge` → `test_rules_tool_failure_produces_failure_experience`（失败 Tool 生成 failure_experience，不生成成功知识）
  - `test_b1_failure_tool_llm_knowledge_rejected`：失败经验可保留，LLM 声称的成功知识仍拒绝
- **`docs/day8/01_task_card.md`、`docs/day8/02_pr_description.md`（新增）**：任务卡 + 本 PR 描述
- **`evidence/l1/day8_knowledge_extraction_local.log`（新增）**：L1 证据（255 passed + 47 skipped @ 95fcad8，checksum 6f78fd48…）
- **`evidence/index.yaml`（更新）**：`D8-A-KNOWLEDGE-EXTRACTION`（HOST_VERIFIED / E4，tested_commit 95fcad8）

## 明确不修改范围

- 不修改 Day4/5/6/7 已合并的 Bridge/Provider/Embedding/Pipeline 核心（cpp-bridge/、embedding/、pipeline/）
- 不修改 Day3 契约接口签名（`extract_preferences(event)` / `extract_knowledge(event)` 单参数；`extract_knowledge_with_meta` 为评测扩展，不替代契约接口）
- 不实现 SQLite/Outbox 持久化（D 轨 D8 memory_relation/memory_conflict）、知识 FTS/Vector 索引（B 轨 D8）、六类知识业务规则冻结（E 轨 D8）
- 不接入真实 LLM（无模型凭证；接口预留，规则路径独立工作）
- 不改架构 4.4 冻结 IPC 方法语义

## 契约演进记录

1. **`KnowledgeCandidate.category` 五值 → 六值**（Day3 契约 → E 轨 §2.6 权威）：
   - `fact/procedure/case/template/constraint` → `fact/workflow/case/template/constraint/failure_experience`
   - `procedure` → `workflow` 命名对齐（语义不变：步骤和工作流，架构 TABLE 21 ProcedureMemory）
   - 新增 `failure_experience`（架构 TABLE 21 FailureMemory：失败 Tool 的失败经验知识）
   - 非法值降级默认 `fact` + audit（`_degrade_knowledge_fields`）
2. **失败 Tool 语义演进**：Day3/6"失败 Tool 不生成任何知识" → Day8"失败 Tool 不生成成功知识，但生成 failure_experience（失败经验）"。B1 红线语义不变（成功知识必须建立在真实 success ToolResult 之上；failure_experience 非成功类别）。依据：架构 TABLE 21 FailureMemory + TABLE 17（Tool 失败/取消=中可信，可用于失败案例）。

## 关联任务与技术债

- 关联：B 轨 D8（知识 FTS/Vector 索引字段）、D 轨 D8（memory_relation/memory_conflict 持久化）、E 轨 D8（六类知识/证据关系/冲突优先级业务规则）
- 无新增 TD；沿用 TD-A-D6-EXEC-RACE（全量 -v 偶发 test_server_lifecycle 竞态，复跑即绿，非阻断）、TD-A-D7-CACHE-USER-DIMENSION、TD-A-D7-LLM-HANG-DEGRADE（知识路径同受约束）

## L0-L3 命令与证据

| 级别 | 命令 | 结果 |
|------|------|------|
| L0 | `python -m py_compile memory-service/providers/knowledge_rules.py memory-service/providers/extraction_provider.py` | COMPILE OK |
| L1 | `/tmp/day8-venv/bin/python -m pytest tests/ -v` | **255 passed + 47 skipped** @ 95fcad8（新增 26 项 D8 测试：24 项 + 2 项 Review 回归；Day7 基线 229+47 → 255+47） |
| L2 | 麒麟 VM：`cd /mnt/shared && git rev-parse HEAD` → `PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -v` | 待 VM 执行（evidence/l2-kylin-vm/day8_verify_latest.log） |

## 性能与安全影响

- 性能：无新增外部调用；knowledge 抽取与 preference 共用同一缓存/超时框架，规则路径纯函数 O(n)
- 安全：R5 敏感复核扩展至全部结构化字段（此前仅 fact+conditions）——防 LLM 把敏感原文藏进 evidence/failure_reason/template_body 等；failure_experience 的 evidence=错误详情为系统可信来源（R3），LLM 无法伪造

## 回滚方式

- 回滚 `25ec565` 即恢复 Day7 基线（main @ d37fb95）；新增文件（knowledge_rules.py/test_knowledge_extraction_d8.py）随之移除；`extraction_provider.py` 回退后 KnowledgeCandidate 恢复五值枚举，失败 Tool 恢复"不生成任何知识"语义（旧行为，不破坏契约）
