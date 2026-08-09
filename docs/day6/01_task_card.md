# D6-A 任务卡：多源接入、质量与安全（A 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D6-A |
| 任务标题 | 统一事件清洗/质量评分管线 + 结构化抽取 Provider + 内容指纹/重复检测 |
| 责任轨道 | A（刘依枫） |
| Reviewer | D 主审；安全/评测影响时 E 补审 |
| 基线分支 | feat/day6-event-quality-pipeline（基于 feat/day5 @ 74bda33） |
| 目标 | 实现可复用的统一事件清洗/时间状态标准化/质量评分技术管线；结构化抽取 Provider（规则优先 + Pydantic 非法输出降级）；内容指纹与重复检测辅助函数 |
| 完成定义（台账） | 清洗和抽取管线可复用，非法输出不进入业务真源 |

## 修改范围

- `memory-service/pipeline/`（新增子包）：
  - `schemas.py`：MemorySourceEvent v0.1 Pydantic 模型（对齐 E 轨 Schema）+ 清洗输出 NormalizedEvent + 质量评分 QualityScore
  - `cleaner.py`：EventCleaner——字段校验（Pydantic 拒绝缺失/类型错误/未知高风险字段）、时间标准化（occurred_at/captured_at → ISO8601 UTC）、状态标准化（source_business_status/processing_status 枚举归一）、Tool 参数结构与来源标识标准化
  - `sensitive.py`：敏感信息识别（API Key/Token/密码/私钥/手机号/身份证/敏感路径正则）→ sensitivity 等级 + is_sensitive_matched
  - `quality.py`：QualityScorer——completeness/validity/reliability/freshness/consistency/extractability 六维评分（架构 6.2 第 5 步）
  - `fingerprint.py`：内容指纹（sha256 归一化正文）+ 重复检测辅助函数（event_id/tool_call_id/内容指纹）
  - `pipeline.py`：EventPipeline 编排（清洗→敏感→指纹→评分→提取门控）
- `memory-service/providers/extraction_provider.py`：ExtractionProvider（Day3 契约接口）——规则优先抽取（真实规则，可解释）+ LLM 结构化抽取接口（provider 可注入，未接入时返回规则结果）+ Pydantic 非法输出降级（校验失败 → 候选不进入业务真源，进审计）
- `memory-service/tests/`：test_pipeline_cleaner.py / test_pipeline_quality.py / test_pipeline_fingerprint.py / test_pipeline_sensitive.py / test_extraction_provider.py
- `docs/day6/01_task_card.md`（本任务卡）

## 禁止修改范围

- 不修改 Day4/Day5 已合并的 Bridge/Provider/Embedding 核心
- 不实现 SQLite/Outbox 持久化（D 轨 D6）、日志脱敏/跨用户 Repository 约束（D 轨）、业务 Schema 冻结（E 轨）
- 不接入真实 LLM（无模型凭证；接口预留，规则路径独立工作）
- 不改架构 4.4 冻结 IPC 方法语义

## 输入契约

- MemorySourceEvent v0.1（docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md §3.1，25 字段）
- ExtractionProvider（docs/day3/06_provider_contract_v1.md §ExtractionProvider）
- 架构 v1 §6.2 数据质量流水线六步、§6.3 来源可信度基线

## 输出契约

- `EventCleaner.clean(raw: dict) -> NormalizedEvent`（校验失败抛 `EventValidationError`，结构化）
- `QualityScorer.score(event) -> QualityScore`（六维 0.0–1.0 + overall + 是否进入提取的 Gate 判定）
- `content_fingerprint(text) -> str`（sha256）；`is_duplicate(candidates, fingerprint) -> bool`（辅助函数）
- `ExtractionProvider.extract_preferences/extract_knowledge(event) -> list[Candidate]`（Day3 契约签名）

## 错误语义

- Pydantic 校验失败：抛 `EventValidationError(code, message)`，结构化错误，不静默吞掉
- LLM 输出非法（非 dict / 缺字段 / 类型错）：降级——该候选标记 `validation_failed=True` 进审计，不进入业务真源；整体返回规则路径结果（真实结果或空列表，非固定样例）
- 超时：按 Day3 契约返回空候选列表（降级）

## 安全边界

- 敏感信息识别只做标记（is_sensitive_matched/sensitivity），不落明文日志
- 指纹基于归一化正文，不包含原始载荷全文

## WSL 可测项

- 全部管线单元测试（清洗/敏感/评分/指纹/抽取规则路径）——本地 pytest 全绿 + 顺序无关

## 麒麟 L2 必测项

- 全量 pytest 在麒麟 VM 无 Skip 通过（回归 Day4/5 测试）
- 真实 Tool/Turn 事件结构尚缺 C 轨取证（HD-SCHEMA-02），本任务不依赖

## 交付物

- pipeline/ 子包 + ExtractionProvider + 测试（本地全绿 + 顺序无关）
- 本任务卡 + 证据回填 index.yaml（新 id，D6-A）

## 验收标准

- 清洗/抽取管线可复用：同一输入多次清洗结果一致（确定性）；非法输出不进入候选（有测试断言）
- 全量 pytest 本地通过、顺序无关
- 无固定样例假实现（降级 = 真实规则结果或空列表）
