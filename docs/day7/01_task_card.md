# D7-A 任务卡：偏好提取深化——规则/抽取 Provider 协同 + 缓存/超时/非法字段降级 + 字段级评测统一结果格式（A 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D7-A |
| 任务标题 | 完善规则+抽取 Provider 协同；增加缓存、超时和非法字段降级；偏好字段级评测统一结果格式 |
| 责任轨道 | A（刘依枫） |
| Reviewer | D 主审；安全/评测影响时 E 补审 |
| 基线分支 | feat/day7-preference-extraction（基于 main @ 2e3f919，PR #27 已合并） |
| 目标 | 偏好抽取 Provider 稳定：规则路径独立工作并承担偏好类别/临时-长期/作用域判定；LLM 路径协同（合并去重）；缓存/超时/非法字段降级；输出统一字段级评测结果格式（供 E 轨 D7 偏好准确率评测） |
| 完成定义（台账 R37） | 偏好抽取 Provider 稳定，规则路径可独立工作 |

## 修改范围

- `memory-service/providers/preference_rules.py`（新增）：偏好规则纯函数模块
  - 偏好类别识别（架构 TABLE 19 六类：presentation / tool_selection / workflow / safety / environment / scene_specific）
  - 临时指令 vs 长期偏好（架构 TABLE 20 + E 轨 Schema §3.2 `is_temporary`/`should_persist`）
  - scope 推导（E 轨 Schema §2.9 五值：global / topic / tool / session / time_window）
  - 显式/隐式表达判定（E 轨 Schema §2.5 `expression_type`：explicit / implicit）
- `memory-service/providers/extraction_provider.py`（增强）：
  - `PreferenceCandidate` v0.2：新增 `category`/`explicitness`/`is_temporary`/`should_persist`；`scope` 对齐 E 轨 §2.9 五值（契约演进：Day3 契约标注"待架构文档确认后调整"，E 轨 Schema v0.1 为权威业务 Schema）
  - 规则路径接入 preference_rules（六类识别 + 临时/长期 + scope + 类别键 key 派生）
  - LLM 协同：规则 + LLM 结果合并去重（同 key 规则优先，LLM 重复候选丢弃并审计）
  - 缓存：LRU 抽取缓存（键 = kind + source_event_id + 内容指纹），返回不可变副本，容量/TTL 可配
  - 超时：LLM 调用显式超时包装（`llm_timeout_ms`，超时 → 空候选 + audit，Day3 契约降级）
  - 非法字段降级：可选字段非法值 → 剥离 + 默认值 + audit（必需字段缺失/类型错误保持 R4 候选级隔离）
  - 评测输出：`PreferenceExtractionOutput`（含 event_id/模式/candidates/缓存命中/耗时）+ `export_preference_records()` JSONL 导出 + 单候选 `to_evaluation_record()` 统一字段格式
- `memory-service/tests/test_preference_rules.py`（新增）：规则单元测试
- `memory-service/tests/test_extraction_provider_d7.py`（新增）：D7 增强测试（缓存/超时/字段降级/协同/评测输出/契约演进）
- `docs/day7/01_task_card.md`（本任务卡）

## 禁止修改范围

- 不修改 Day4/5/6 已合并的 Bridge/Provider/Embedding/Pipeline 核心（cpp-bridge/、embedding/、pipeline/）
- 不修改 Day3 契约接口签名（`extract_preferences(event)` / `extract_knowledge(event)` 单参数）
- 不实现 SQLite/Outbox 持久化（D 轨 D7）、偏好版本表（D 轨）、业务规则冻结（E 轨）
- 不接入真实 LLM（无模型凭证；接口预留，规则路径独立工作）
- 不实现知识结构化抽取（D8 任务）
- 不改架构 4.4 冻结 IPC 方法语义

## 输入契约

- PreferenceCandidate（docs/day3/06_provider_contract_v1.md §ExtractionProvider；scope 值域调整见输出契约）
- E 轨业务 Schema v0.1 §3.2 Preference 对象（expression_type/preference_scope/is_temporary/should_persist/memory_status）
- 架构 v1 TABLE 19 偏好六类、TABLE 20 临时指令 vs 长期偏好、7.1 偏好记忆
- 架构 v1 §6.2 数据质量流水线第 6 步（低质量事件不进入长期记忆）

## 输出契约

- `PreferenceCandidate` v0.2：
  - `key`（类别键，如 `response.language`）、`value`、`category`（六类枚举）、
  - `scope`（global/topic/tool/session/time_window，E 轨 §2.9 五值）、`confidence`（0.0–1.0）、
  - `explicitness`（explicit/implicit）、`is_temporary`、`should_persist`、
  - `evidence`、`source_event_id`（R3 系统可信）、`memory_status`（B2 恒 candidate）
- `PreferenceExtractionOutput`：event_id / provider_mode（rules|llm|coop）/ candidates / cache_hit / llm_timeout / duration_ms
- `export_preference_records(events, provider, path) -> int`：JSONL 输出（每行一个 output），供 E 轨偏好评测
- `to_evaluation_record(candidate) -> dict`：字段级统一结果格式（key/value/category/scope/confidence/explicitness/is_temporary/should_persist/evidence/source_event_id/memory_status，与 E 轨 §3.2 口径一致）

## 错误语义

- 超时（LLM 超过 `llm_timeout_ms`）：返回空候选列表 + audit 记录 `timeout`（Day3 契约降级，不阻塞 Turn 处理）
- 非法字段（可选字段值非法）：剥离该字段 + 默认值 + audit 记录 `field-degraded:<field>`，候选仍返回（字段级降级）
- 必需字段缺失/类型错误：候选级拒绝，仅进 audit（R4 保持——非法候选不进入业务真源）
- 缓存命中：返回候选深拷贝（调用方修改不影响缓存）

## 安全边界

- R3：source_event_id 系统可信，LLM 无法伪造/覆盖（保持）
- R4：非法 LLM 输出不进入正常 candidates（保持，仅可选字段做字段级降级）
- R5：候选正文命中 high/critical 敏感 → 拒绝进审计（保持，规则/LLM 双路径）
- B2：memory_status 恒 candidate，LLM 不能自封 verified（保持）
- 缓存键基于内容指纹，不含原始载荷全文；缓存副本不落明文日志

## WSL 可测项

- 全部 D7 新测试 + 既有全量 pytest（本地全绿 + 顺序无关）

## 麒麟 L2 必测项

- 全量 pytest 在麒麟 VM 无 Skip 通过（回归 Day4/5/6 测试）；D7 纯规则/降级逻辑不依赖宿主 SDK，L2 为回归性质

## 交付物

- preference_rules.py + extraction_provider.py 增强 + 2 个新测试文件（本地全绿 + 顺序无关）
- 本任务卡 + 证据回填 index.yaml（新 id，D7-A）

## 验收标准

- 规则路径独立工作：无 LLM 时六类偏好可识别、临时/长期可区分、scope 可推导（有测试断言）
- 同一事件重复抽取命中缓存且结果一致（确定性）；LLM 超时不阻塞返回空候选
- 可选字段非法值被降级（候选保留 + audit），必需字段非法候选仍被隔离（R4 无回归）
- 评测输出 JSONL 字段与 E 轨 §3.2 口径一致（category/scope/confidence/explicitness/is_temporary/should_persist）
- 全量 pytest 本地通过、顺序无关；无固定样例假实现

## 契约演进记录（D7）

| 项 | Day3 冻结值 | D7 演进值 | 依据 |
|----|------------|-----------|------|
| PreferenceCandidate.scope | `global/session/project` | `global/topic/tool/session/time_window` | E 轨 Schema v0.1 §2.9（权威业务 Schema）；Day3 契约标注"待架构文档确认后调整" |
| PreferenceCandidate 字段 | key/value/scope/confidence/evidence/source_event_id/memory_status | + category/explicitness/is_temporary/should_persist | E 轨 §3.2（expression_type/preference_scope/is_temporary/should_persist）+ 架构 TABLE 19 |

## 审查报告（PR #36 REWORK）落实记录（Day7 复审修复同步）

| 报告项 | 处置 | 位置 |
|--------|------|------|
| HIGH-01 TABLE 20 临时原句无法主链抽取 | 已修复：规则入口两阶段（显式偏好词 + 指令式模式 `PREFERENCE_INSTRUCTION_PATTERN`），原句 "这次只用三句话回答" 经 Provider 主链产出候选（非硬编码特判）；新增原句 E2E + 泛化测试；长期原句无回归 | preference_rules.py / extraction_provider.py |
| HIGH-02 required confidence 非法值被降级 0.5 | 已修复：confidence 为契约 required 字段，缺失/类型非法/越界一律 candidate-level reject + validation audit，不做默认值替换（删除 _DEFAULT_CONFIDENCE）；参数化测试 5 种非法形态 | extraction_provider.py |
| MEDIUM-01 is_temporary && should_persist 矛盾 | 已修复：E 轨 §3.2 语义规范化（is_temporary=True → should_persist=False）+ audit（temporary-implies-no-persist） | extraction_provider.py |
| MEDIUM-02 缓存键缺 user 维度 | 已登记 TD-A-D7-CACHE-USER-DIMENSION（单用户端侧运行；契约加 user_id 后缓存键必须升级；多用户前必须关闭） | TECHNICAL_DEBT_REGISTER.md |
| MEDIUM-03 LLM 永久挂死 → 永久 busy-skip | 已登记 TD-A-D7-LLM-HANG-DEGRADE（接入真实 LLM 前需 worker reset/executor 重建/health recovery 之一） | TECHNICAL_DEBT_REGISTER.md |
| MEDIUM-04 L1 Evidence 旧版本 | 已修复：最终修复 commit 重跑 L1 并刷新 evidence/l1/day7_pref_extraction_local.log（224 passed + 47 skipped），PR 描述/交接文档/index.yaml/log 数字统一 | evidence/l1/ |
| LOW-01 implicit 无真实实现 | 已注明：implicit 仅保留 Schema 枚举与 Provider 接口能力，本阶段未实现基于多 Turn 行为证据的隐式偏好推断 | 本任务卡 / PR 描述 |
| LOW-02 评测字段文档未含 memory_status | 已统一：任务卡/PR 描述/JSONL 输出字段定义均含 memory_status | 本任务卡 / PR 描述 |
| LOW-03 缓存/超时边界测试 | 已补充：TTL=0 / llm_timeout_ms=0 / cache hit 不重复调用 LLM | test_extraction_provider_d7.py |

## 审查报告（PR #27）相关记录（不重开已关闭问题）

- TD-A-D6-LLM-TOOL-INPUT（knowledge LLM 输入绑定）：本任务仅偏好路径，知识路径不动，验收条件保持 Open 待真实 LLM
- TD-A-D6-TOOL-PARTIAL（partial 高级语义）：不涉及，保持 Open
- 本任务不引入新 TD（预期）；如出现缓存/线程生命周期风险点，登记后随 PR 提交
