# [D7-A] 偏好抽取深化——规则/Provider 协同 + 缓存/超时/非法字段降级 + 字段级评测统一结果格式

> 分支：`feat/day7-preference-extraction`（基于 main @ `2e3f919`，19 commits：`59171df`…`6f7ca03`）
> PR 模板：架构 v1 附录 D（docs/architecture 18.1 PR 最小内容）

## 背景与目标

Day6（PR #27）已交付统一事件清洗/质量评分管线与结构化抽取 Provider 骨架（规则路径 + LLM 接口预留 + Pydantic 非法输出降级）。Day7 按 75 项台账 **R37**（A 轨 D7：偏好提取与版本管理）深化偏好抽取，目标为"**偏好抽取 Provider 稳定，规则路径可独立工作**"：

1. **规则+抽取 Provider 协同**：偏好六类识别（架构 TABLE 19）、临时指令 vs 长期偏好（TABLE 20 + E 轨 Schema §3.2 `is_temporary`/`should_persist`）、scope 五值推导（E 轨 §2.9）、类别键派生、explicitness（§2.5）、规则/LLM 合并去重（规则优先）
2. **缓存、超时、非法字段降级**：LRU 抽取缓存（深拷贝/空结果缓存/TTL/容量）、LLM 显式超时包装（Day3 契约降级）、可选字段非法值降级（R4 必需字段隔离不变）
3. **偏好字段级评测统一结果格式**：`PreferenceExtractionOutput` / `to_evaluation_record()` / `export_preference_records()`（JSONL），供 E 轨 D7 偏好准确率评测

## 修改范围

- **`memory-service/providers/preference_rules.py`（新增）**：偏好规则纯函数模块——六类识别（presentation/tool_selection/workflow/safety/environment/scene_specific）、临时/长期判定（TABLE 20 原句覆盖）、scope 五值推导、类别键派生、explicitness 判定、规则置信度基线
- **`memory-service/providers/extraction_provider.py`（增强，+414/-49）**：
  - `PreferenceCandidate` v0.2：新增 `category`/`explicitness`/`is_temporary`/`should_persist`，`scope` 对齐 E 轨五值（契约演进，见下）
  - 规则路径接入 preference_rules；规则+LLM 合并去重（同 key 规则优先，dedup/conflict 进 audit）
  - `PreferenceExtractionCache`（LRU：键=kind+source_event_id+内容指纹；深拷贝；空结果缓存；TTL/容量）
  - `_run_llm` 显式超时包装（`llm_timeout_ms` 默认 5000ms；超时→空候选+audit；超时后 in-flight 未完成 → `llm-busy-skip` 不排队拖死）
  - `_degrade_optional_fields`：可选字段非法值 → 默认值+audit（含 unhashable list/dict 值不崩溃）
  - 评测输出：`PreferenceExtractionOutput` / `to_evaluation_record` / `export_preference_records`
- **`memory-service/tests/test_preference_rules.py`（新增，24 项）**：六类/临时长期/scope/key/explicitness/置信度/确定性
- **`memory-service/tests/test_extraction_provider_d7.py`（新增，43 项）**：规则深化（含 TABLE 20 原句 E2E、指令式入口泛化、MEDIUM-08 负向 5 条）、缓存（命中/深拷贝/空结果/串键隔离/TTL/TTL=0/cache hit 不重复调 LLM）、超时（降级/busy-skip/timeout=0）、字段降级（含 unhashable/None 降级 MEDIUM-05）、**confidence strict reject（HIGH-02/HIGH-03，含 missing key/None/bool/str/越界/合法 float）**、矛盾规范化（MEDIUM-01）、协同去重（含 dedup-llm/conflict-llm 标签）、评测输出、close 幂等、R5 evidence/conditions 复核
- **`docs/day7/01_task_card.md`（新增）**：D7-A 任务卡（含契约演进记录）
- **`docs/project-management/session-handoff-20260814.md`（新增）**：Day7 交接文档
- **`evidence/l1/day7_pref_extraction_local.log`、`evidence/l2-kylin-vm/day7_verify_latest.log`（新增）**：L1/L2 证据日志
- **`evidence/index.yaml`（更新）**：`D7-A-PREF-EXTRACTION`（HOST_VERIFIED / E4，tested_commit `e5c52e6`）

## 明确不修改范围

- 不修改 Day4/5/6 已合并的 Bridge/Provider/Embedding/Pipeline 核心（cpp-bridge/、embedding/、pipeline/）
- 不修改 Day3 契约接口签名（`extract_preferences(event)` / `extract_knowledge(event)` 单参数）
- 不实现 SQLite/Outbox 持久化、偏好版本表（D 轨 D7）
- 不实现知识结构化抽取（D8 任务）
- 不接入真实 LLM（无模型凭证；接口预留，规则路径独立工作）
- 不改架构 4.4 冻结 IPC 方法语义

## 关联任务与技术债

- 任务卡：`docs/day7/01_task_card.md`（D7-A，Reviewer：D 主审；安全/评测影响 E 补审）
- TD 新增：**TD-A-D7-CACHE-USER-DIMENSION**（缓存键缺 user 维度，MEDIUM-02）、**TD-A-D7-LLM-HANG-DEGRADE**（LLM 永久挂死 → 永久 busy-skip，MEDIUM-03）——见 docs/technical-debt/TECHNICAL_DEBT_REGISTER.md
- 保持 Open（本 PR 不涉及）：TD-A-D6-LLM-TOOL-INPUT（knowledge LLM 输入绑定，D8 深化）、TD-A-D6-TOOL-PARTIAL、TD-A-D6-EXEC-RACE（全量 -v 本地一次偶发 test_server_lifecycle 复跑即绿；VM 262/264/271 均无此现象）

## 架构与能力边界依据

- 架构 v1 TABLE 19（偏好六类）/ TABLE 20（临时指令 vs 长期偏好）/ 7.1 偏好记忆 / 6.2 数据质量流水线
- E 轨业务 Schema v0.1：§2.5 expression_type、§2.9 preference_scope、§3.2 Preference 对象（is_temporary/should_persist/confidence_score/memory_status）
- Day3 Provider 契约：docs/day3/06_provider_contract_v1.md §ExtractionProvider
- 已关闭红线（不重开）：假 Tool 成功 / 敏感 fail-open / provenance 可伪造 / candidate 被当 verified——本 PR 保持 R3/R4/R5/B1/B2 全部测试与防护

### 契约演进（已记录于 docs/day7/01_task_card.md）

| 项 | Day3 冻结值 | D7 演进值 | 依据 |
|----|------------|-----------|------|
| PreferenceCandidate.scope | `global/session/project` | `global/topic/tool/session/time_window` | E 轨 Schema v0.1 §2.9（权威业务 Schema）；Day3 契约标注"待架构文档确认后调整" |
| PreferenceCandidate 字段 | key/value/scope/confidence/evidence/source_event_id/memory_status | + category/explicitness/is_temporary/should_persist（均带默认值，向后兼容） | E 轨 §3.2 + 架构 TABLE 19 |

## 修改文件清单

| 文件 | 变更 | 摘要 |
|------|------|------|
| memory-service/providers/preference_rules.py | 新增（246 行） | 偏好规则纯函数模块 |
| memory-service/providers/extraction_provider.py | 修改（+414/-49） | v0.2 候选/规则接入/缓存/超时/字段降级/协同/评测输出 |
| memory-service/tests/test_preference_rules.py | 新增（24 项） | 规则单元测试 |
| memory-service/tests/test_extraction_provider_d7.py | 新增（43 项） | D7 深化测试（含 PR #36 两轮修复测试） |
| docs/day7/01_task_card.md | 新增 | D7-A 任务卡 |
| docs/project-management/session-handoff-20260814.md | 新增 | Day7 交接文档 |
| evidence/index.yaml | 修改 | D7-A-PREF-EXTRACTION 条目 |
| evidence/l1/day7_pref_extraction_local.log | 新增 | 本地 L1 证据（229 passed + 47 skipped，被测 e5c52e6） |
| evidence/l2-kylin-vm/day7_verify_latest.log | 新增 | VM L2 证据（276 passed / 0 skipped，被测 e5c52e6） |

## 数据库与配置变化

无。纯 Python Provider 层（无 Migration / 无 SQLite Schema / 无配置/协议变化）。

## 测试结果

### L0 (单元测试 + 静态检查)

```bash
cd memory-service && /tmp/day7-venv/bin/python -m compileall -q providers/ tests/
# → COMPILE-OK（无语法错误）
```

### L1 (组件集成)

```bash
cd memory-service && /tmp/day7-venv/bin/python -m pytest tests/ -q
# → 229 passed, 47 skipped in 3.78s（skipped 为 VM/SDK 专属，WSL 无 SDK）
# 被测 commit: e5c52e6（第二轮 REWORK 修复：HIGH-03 strict confidence / MEDIUM-05 / MEDIUM-08）
# 3 次乱序文件顺序运行均通过（顺序无关）
# 证据：evidence/l1/day7_pref_extraction_local.log
```

### 安全与假实现审查

- 独立审查 1 轮（isolated review）+ 架构红线自查 1 轮 + **PR #36 REWORK 复审修复**：
  - **HIGH-01**（TABLE 20 临时原句无法主链抽取）：规则入口两阶段——显式偏好词 + 指令式模式
    （`PREFERENCE_INSTRUCTION_PATTERN`：时态限定词 + 指令动词，非硬编码特判）；原句
    “这次只用三句话回答”经 `extract_preferences()` 主链产出候选（is_temporary/scope=session/
    memory_status=candidate），新增原句 E2E + 泛化测试，长期原句无回归
  - **HIGH-02**（required confidence 非法值被降级 0.5）：confidence 为契约 required 字段——
    缺失/类型非法/越界一律 candidate-level reject + validation audit（删除 `_DEFAULT_CONFIDENCE`），
    参数化测试 5 种非法形态（missing/"high"/-0.1/1.1/2.0）
  - **MEDIUM-01**（is_temporary && should_persist 矛盾）：按 E 轨 §3.2 规范化
    （is_temporary=True → should_persist=False）+ audit（temporary-implies-no-persist）
  - 前一轮 4 项（unhashable/llm-busy-skip/dedup-llm 标签/R5 evidence-conditions 复核）保持
  - **第二轮（commit e5c52e6）**：
    - **HIGH-03**（confidence 无 strict 类型约束，bool/str 自动转换进入候选）：
      PreferenceCandidate/KnowledgeCandidate confidence 均改 `Field(strict=True, ge=0.0, le=1.0)`——
      True/False/"0.9"/"1"/None/"high"/越界/missing key 全部 reject + validation audit；
      合法 float 0.0/0.5/0.9/1.0 通过（参数化 + 真 missing key 测试）
    - **MEDIUM-05**（optional None 与字段级降级契约不一致）：方案 A——显式 None 视为非法
      optional 值 → 降级默认值 + audit（category→presentation/scope→session/explicitness→explicit/
      is_temporary→False/should_persist→True）；字段缺失仍走 Pydantic 默认值（无 audit）
    - **MEDIUM-08**（指令模式误报）：时态限定词（这次/本次/现在/当前/今天）改为必选——
      “不要慌，再试一次”/“别问了”/“保持联系”/“不要忘记密码”不再误抽取；
      负向测试 5 条 + 正向保留 3 条
- 无 Mock 冒充 Runtime：降级 = 真实规则结果或空列表（非固定样例，TABLE 54）
- 无密钥泄露：audit 不含正文原文（`test_audit_does_not_contain_raw_text`）
- 无硬编码配置：规则置信度/关键词为基线值，标注待 E 轨数据集评测调优

### L2 麒麟虚拟机证据

```bash
cd /mnt/shared && PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service \
  LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 \
  /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -q
# → 276 passed in 5.97s（0 failed / 0 skipped）
# 被测 commit: e5c52e689d3958657d6343fc11bf5d90f93e6813（两轮 REWORK 后最终生产代码）
# 证据：evidence/l2-kylin-vm/day7_verify_latest.log（checksum b52d437a…，含元数据头）
# index.yaml: D7-A-PREF-EXTRACTION（HOST_VERIFIED / E4，tested_commit e5c52e6）
```

### L3 (全链路验收)

不适用。D7 为 Provider 层增量（无安装/无存储/无 IPC 变化）；L3 干净镜像回归按 15 天计划在 D14 执行。

## 性能影响

- **延迟**：抽取为 Post-Turn 异步路径（不阻塞 UI 线程，架构 4.2）；LLM 超时默认 5000ms，超时/异常返回空候选，不拖慢 Turn 事件处理
- **吞吐**：LRU 抽取缓存（默认容量 256）避免同一事件重复触发 LLM；缓存键含内容指纹（同 ID 不同内容不串键）
- **内存**：缓存深拷贝存储+返回副本（防污染）；容量/TTL 可配；`stats` 可观测

## 已知限制

- 未接入真实 LLM（无模型凭证；`LLMExtractor` 接口预留，规则路径独立工作）——`TD-A-D6-LLM-TOOL-INPUT` 验收条件保持 Open
- **implicit 未实现真实推断（LOW-01）**：`explicitness` 仅保留 Schema 枚举与 Provider 接口能力，本阶段未实现基于多 Turn 行为证据的隐式偏好推断（规则路径始终生成 explicit）
- **缓存键缺 user 维度（MEDIUM-02）**：登记 TD-A-D7-CACHE-USER-DIMENSION——TurnFinalizedEvent 为 Day3 冻结契约（无 user_id），键 = kind+source_event_id+内容指纹；单用户端侧场景运行，事件契约加 user_id 后缓存键必须升级，多用户启用前必须关闭该 TD
- **LLM 永久挂死风险（MEDIUM-03）**：登记 TD-A-D7-LLM-HANG-DEGRADE——超时后 in-flight 未完成会 llm-busy-skip；接入真实 LLM 前需提供 worker reset/executor 重建/health recovery 之一
- 规则置信度基线（0.6/0.7/0.75）与类别关键词为基线值，待 E 轨数据集评测调优（偏好准确率 ≥85% 口径）
- knowledge 路径保持 D6 行为（B1 门控/规则提取），结构化知识抽取（六类/失败 Tool 策略）属 D8 任务
- 评测字段定义（LOW-02）：`to_evaluation_record()` 输出含 memory_status（B2 恒 candidate），任务卡/PR 描述/JSONL 字段已统一

## 回滚方式

- 纯新增模块 + 单文件增强，不触碰冻结协议/存储/其他 Provider：
  - 回滚 = 从 main 还原 `memory-service/providers/extraction_provider.py`，删除新增的 `preference_rules.py` 与 2 个测试文件即可
  - 无数据库 Migration、无配置变化、无 IPC 语义变化，回滚不影响 Day4/5/6 已合并功能

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
