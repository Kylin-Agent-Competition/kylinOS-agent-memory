# D8-A 任务卡：知识结构化抽取——六类知识 + 失败/取消 Tool 不同策略 + 失败降级测试（A 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D8-A |
| 任务标题 | 为 Fact/Procedure/Case/Template 等知识提供结构化抽取支持；对失败 Tool、取消 Tool 和模型推测实施不同抽取策略；增加失败降级测试 |
| 责任轨道 | A（刘依枫） |
| Reviewer | D 主审；安全/评测影响时 E 补审 |
| 基线分支 | feat/day8-knowledge-extraction（基于 main @ d37fb95，PR #36 已合并） |
| 目标 | 知识抽取保留证据与适用条件，失败 Tool 不生成成功知识（台账 R42 完成定义） |
| 完成定义（台账 R42） | 知识抽取保留证据与适用条件，失败 Tool 不生成成功知识 |

## 修改范围

- `memory-service/providers/knowledge_rules.py`（新增）：知识规则纯函数模块
  - 六类知识识别（架构 TABLE 21 + E 轨 Schema §2.6：fact / workflow / case / template / constraint / failure_experience），优先级 failure > constraint > template > case > workflow > fact
  - Tool 状态 → 抽取策略（架构 TABLE 31 ToolExecutionEvent.status）：success → 成功知识（0.85，TABLE 17 高可信）；failure → 仅 failure_experience（0.6，中可信）；cancelled/其他 → skip 不沉淀
  - 失败经验结构化（架构 TABLE 21 FailureMemory）：失败原因 / 环境（tool+args）/ 避免条件 / 替代方案（未知不臆造）
  - 规则路径置信度基线（TABLE 17 来源可信度）
- `memory-service/providers/extraction_provider.py`（增强）：
  - `KnowledgeCandidate` v0.2：`category` 六值对齐 E 轨 §2.6（契约演进：Day3 五值 fact/procedure/case/template/constraint → 六值，procedure → workflow 命名对齐 E 轨，新增 failure_experience）；新增六类结构化字段（evidence/steps/expected_result/problem/outcome/reproducible/template_body/parameters/priority/failure_reason/avoid_condition/alternative，全可选向后兼容）
  - 规则路径按 Tool 状态分派（success → 六类识别 + evidence + conditions；failure → failure_experience；cancelled → 跳过）
  - B1 门控保持：无真实 success Tool evidence 时 LLM 成功知识整体拒绝（架构 TABLE 22：Tool 事实高于模型自述）
  - 失败降级：knowledge LLM 非法 category → 默认 fact + audit；结构化字段非法值 → 剥离 + audit（必需字段 fact/confidence 保持 R4 候选级拒绝）
  - R5 敏感复核覆盖结构化字段（evidence/failure_reason/template_body 等，D8 增强）
  - 评测输出：`KnowledgeExtractionOutput` / `to_knowledge_evaluation_record()` / `export_knowledge_records()`（E 轨 §3.3 口径）
- `memory-service/tests/test_knowledge_extraction_d8.py`（新增，26 项：24 项 + 2 项 Review 回归）：六类识别 / 不同 Tool 状态策略 / 失败降级 / 评测输出 / 契约保持
- `memory-service/tests/test_extraction_provider.py`（更新）：`test_rules_tool_failure_no_knowledge` → `test_rules_tool_failure_produces_failure_experience`；`test_b1_failure_tool_llm_knowledge_rejected` 断言随契约演进同步（失败经验可保留、成功知识仍拒绝）
- `docs/day8/01_task_card.md`（本任务卡）、`docs/day8/02_pr_description.md`
- `evidence/l1/day8_knowledge_extraction_local.log`、`evidence/index.yaml`（更新 D8-A 条目）

## 禁止修改范围

- 不修改 Day4/5/6/7 已合并的 Bridge/Provider/Embedding/Pipeline 核心（cpp-bridge/、embedding/、pipeline/）
- 不修改 Day3 契约接口签名（`extract_preferences(event)` / `extract_knowledge(event)` 单参数；新增 `extract_knowledge_with_meta` 为评测扩展不替代契约接口）
- 不实现 SQLite/Outbox 持久化（D 轨 D8 memory_relation/memory_conflict）、知识索引（B 轨 D8）、冲突引擎（E 轨 D8）
- 不接入真实 LLM（无模型凭证；接口预留，规则路径独立工作）
- 不改架构 4.4 冻结 IPC 方法语义

## 输入契约

- KnowledgeCandidate（docs/day3/06_provider_contract_v1.md §ExtractionProvider；category 值域演进见输出契约）
- E 轨业务 Schema v0.1 §2.6 knowledge_type 六值、§3.3 Knowledge 对象字段
- 架构 v1 TABLE 21 知识六类必须保留结构、TABLE 22 Tool 事实高于模型自述、TABLE 31 ToolExecutionEvent、TABLE 17 来源可信度
- B1 红线：成功知识必须建立在真实 success ToolResult 之上（失败/取消/超时/partial 不产生成功知识）

## 输出契约

- `KnowledgeCandidate` v0.2：
  - `fact`（知识正文）、`category`（六值枚举：fact/workflow/case/template/constraint/failure_experience）、
  - `conditions`（适用条件：tool 名/环境/场景）、`evidence`（证据描述，R3 系统可信来源）、
  - `source_event_id`（R3）、`confidence`（strict float 0.0–1.0）、`memory_status`（B2 恒 candidate）、
  - 六类结构化字段（全可选）：steps/expected_result（workflow）、problem/outcome/reproducible（case）、
    template_body/parameters（template）、priority（constraint）、failure_reason/avoid_condition/alternative（failure）
- `KnowledgeExtractionOutput`：event_id / provider_mode / candidates / cache_hit / llm_timeout / duration_ms
- `export_knowledge_records(events, provider, path) -> int`：JSONL 输出（每行一个 output），供 E 轨 D8 知识评测
- `to_knowledge_evaluation_record(candidate) -> dict`：字段级统一结果格式（E 轨 §3.3 口径）

## 错误语义

| 场景 | 行为 | 依据 |
|------|------|------|
| success Tool + 空/短 result | 跳过（不生成知识） | B1 |
| failure Tool | 生成 failure_experience（不生成成功知识） | B1 + TABLE 21/22 |
| cancelled / timeout / partial / 未知状态 | 跳过（不沉淀任何知识） | B1 + 架构 8 章 |
| 模型推测（无真实 success Tool 证据） | LLM 成功知识整体拒绝 + audit(no-success-tool-evidence) | B1 + TABLE 22 |
| LLM 非法 category | 默认 fact + audit(field-degraded:category) | D8 字段级降级 |
| LLM 结构化字段非法值（非 str） | 剥离 + audit | D8 字段级降级 |
| LLM 必需字段缺失/类型错误 | 候选级拒绝 + audit(validation) | R4 |
| LLM 超时 | 空候选 + audit(timeout)，不阻塞 | Day3 契约降级 |
| 候选含 high/critical 敏感 | 拒绝 + audit(sensitive-content-rejected) | R5 |

## 契约演进记录

1. `KnowledgeCandidate.category`：Day3 五值（fact/procedure/case/template/constraint）→ E 轨 §2.6 六值（fact/workflow/case/template/constraint/failure_experience）。
   - 依据：E 轨 Schema v0.1 为权威业务 Schema；架构 TABLE 21 六类（FactMemory/ProcedureMemory/CaseMemory/TemplateMemory/ConstraintMemory/FailureMemory）与 E 轨六值一一对应（ProcedureMemory ↔ workflow）。
   - procedure → workflow 为命名对齐（语义不变：步骤和工作流）。
   - 向后兼容：既有 LLM 输出 category="fact" 不受影响；新六值枚举由 `_degrade_knowledge_fields` 校验，非法值降级默认 fact。
2. 失败 Tool 语义：Day3/6 实现"失败 Tool 不生成任何知识"→ Day8 演进为"失败 Tool 不生成**成功**知识，但生成 **failure_experience**（失败经验知识）"。
   - 依据：架构 TABLE 21 FailureMemory 明确失败经验为六类知识之一；TABLE 17 来源可信度标注"Tool 失败/取消=中，可用于失败案例、风险偏好"。
   - B1 红线语义不变：成功知识必须建立在真实 success ToolResult 之上；failure_experience 不是成功知识类别。
   - 既有测试 `test_rules_tool_failure_no_knowledge` / `test_b1_failure_tool_llm_knowledge_rejected` 断言随演进同步（文档本任务卡 + PR 描述记录）。

## 证据

- L1：`evidence/l1/day8_knowledge_extraction_local.log`（253 passed + 47 skipped @ 25ec565，checksum 133715d6…，含元数据头）
- L2：`evidence/l2-kylin-vm/day8_verify_latest.log`（**302 passed / 0 skipped**，被测生产代码 95fcad8，实测 HEAD 5057551，checksum 7f32f404…；302 = L1 255+47，VM 上 47 个 SDK 用例真实执行不再 skip）

## 技术债

- **沿用**：TD-A-D6-EXEC-RACE（全量 -v 偶发 test_server_lifecycle 竞态，复跑即绿，非阻断）、TD-A-D7-CACHE-USER-DIMENSION（缓存键缺 user 维度，知识缓存同受约束）、TD-A-D7-LLM-HANG-DEGRADE（LLM 永久挂死 busy-skip，知识路径同受约束）、TD-A-D6-LLM-TOOL-INPUT（Knowledge LLM 事件级门控，候选级 ToolResult provenance 绑定待真实 LLM 接入前完成，本 PR 不修改生产代码）
- **本 PR 新增登记**：TD-A-D8-CONTRACT-CATEGORY-SYNC（Day3 Provider 文档 category 五值 vs Day8 六值实现——契约同步债，当前六类方向合理仅文档未同步，关闭条件见台账）
