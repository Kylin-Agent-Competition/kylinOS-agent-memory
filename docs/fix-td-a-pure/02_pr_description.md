# [A 轨] 技术债批量收口——10 项 TD Resolved + 2 项 Wontfix + 1 项新增 Risk（REWORK 修订版）

> 分支：`fix/td-a-pure`（基于 main @ `5bd2c3e`，Day8 #38 已合并；已推送）
> Reviewer：D 主审；安全/降级/数据影响 E 补审
> 修订记录：2026-08-18 按 D 主审第二轮 REWORK 报告（R-2/R-3/R-4/R-5）修订

## 背景与目标

按技术债台账管理规则第 3 条（"代码合并 ≠ 技术债关闭，关闭需 Reviewer 确认验收标准达成"），将 A 轨**可关闭的 10 项技术债一次性收口**（含 3 项需麒麟 VM 实测的：TD-A-005-01/02/04），另 2 项经 VM 证实 SDK 无能力故标 Wontfix（TD-A-005-01 无 cancel API、TD-A-005-04 get_model_list 外部调用 UAF）。剩余 3 项 Open（D6-EXEC-RACE 非阻断并发风险、D6-TOOL-PARTIAL / D7-CACHE-USER-DIMENSION 契约未定）本次不动，理由见"已知限制"。

## 修改范围

### 生产代码（memory-service/）
- **`providers/embedding_provider.py`**：
  - TD-A-005-03：`get_dimension()` 正常路径不再触发空串 embed（start() 已写入 `_shared_dimension`），消除 IPC 副作用
  - TD-A-005-04：`model_info().name` 返回 Bridge 集中缓存值（SDK 日志确认的默认模型名 `ensemble-embd_gte-base_uint8-text`，非动态查询——SDK get_model_list 外部调用 UAF，见 TD-A-D9-SDK-MODEL-LIST-UAF）——**Wontfix，SDK 无安全动态模型名查询 API**
  - TD-A-005-05：`model_info().loaded` 基于 `_lifecycle==READY` 精确化
  - TD-A-005-06：类级 `_singleton_lock` 保护单例临界区
- **`providers/extraction_provider.py`**：
  - TD-A-D6-LLM-TOOL-INPUT：`_run_llm` 增 `tool_context`——knowledge LLM 输入绑定具体 success ToolResult.result
  - TD-A-D7-LLM-HANG-DEGRADE：`_llm_hang_threshold_ms` 检测挂死超阈值 → `_rebuild_executor()` 恢复
- **`embedding/embedding_service.py`**：
  - TD-A-005-09：构造/start 时 EmbeddingProvider 失败 → 兜底 `_SdkMissingProvider`（UDS server 可启动，embed → ok+degraded 空向量；health → bridge_loaded=false）
  - **[Review #6 已修复]** 构造 except 精确化：`ERR_CONFIG_CONFLICT`（so_path 冲突）上抛，不误判为 SDK 缺失
  - **[Review #7 已修复]** health() 的 `degraded` 反映 `_sdk_missing`（不再恒 false），新增 `sdk_missing` 字段

### C++ Bridge（cpp-bridge/）
- **TD-A-005-04**：`EmbeddingBridge::get_default_model_name()` 返回缓存值
  - **[Wontfix]** SDK get_model_list 外部调用 UAF（10/10 段错误，见 TD-A-D9-SDK-MODEL-LIST-UAF），不通过动态查询获取模型名
  - `refresh_model_name_cache_locked()`：create_session 时缓存 SDK 日志确认的默认模型名
  - `get_default_model_name()` 直接返回缓存值，不再调用 SDK 函数

### 脚本
- **TD-A-005-08**：`verify_day4_vm.sh` 历史备份改放 `/tmp/day4_verify_latest.prev.log`

### 文档 / 证据
- **TD-A-005-07**：轮次标注去硬编码；`embed()` docstring 补 `ERR_FATAL_FAILURE`
- **TD-A-D8-CONTRACT-CATEGORY-SYNC**：Day3 契约 `KnowledgeCandidate.category` 五值→六值
- **[Review #3 已修复]** Day3 契约 `PreferenceCandidate.scope` 三值→五值（global/topic/tool/session/time_window，对齐 E 轨 §2.9）
- 台账：11 项 Resolved + 1 项 Wontfix；TD-A-005-04 能力认证降级（R-1）
- 证据：`evidence/l2-kylin-vm/td_a_005_04_model_name.log`（**补充非判别性说明，R-1**）、`td_a_005_09_sdk_missing.log`
- 测试：`test_td_a_005_03_05.py`（7 项）+ `test_td_a_005_09.py`（4 项）+ `test_td_a_local_batch.py`（6 项）＝ **17 项回归测试**

## 明确不修改范围

- 不修改 Day9 内容（独立分支 `feat/day9-embedding-throughput`）
- 不修改 Day3 冻结契约字段（ToolResult 无 side_effect/rollback；事件无可信 user_id）
- 不实现 Bridge 内部主动超时中断（TD-A-005-01 Wontfix：SDK 无 cancel/abort API）
- 不改 embed_batch 为并行（TD-A-005-02 Resolved：VM 实测并发挂起）
- 不通过 SDK get_model_list 动态查询模型名（TD-A-005-04 Wontfix：外部调用 UAF 10/10 段错误，见 TD-A-D9-SDK-MODEL-LIST-UAF）

## 关联任务与技术债

- 本 PR 关闭：TD-A-005-02/03/05/06/07/08/09 + TD-A-D6-LLM-TOOL-INPUT + TD-A-D7-LLM-HANG-DEGRADE + TD-A-D8-CONTRACT-CATEGORY-SYNC（10 Resolved）+ TD-A-005-01（Wontfix）+ TD-A-005-04（Wontfix，SDK 无安全动态模型名查询 API，见 TD-A-D9-SDK-MODEL-LIST-UAF）
- 维持 Open：TD-A-D6-EXEC-RACE / TD-A-D6-TOOL-PARTIAL / TD-A-D7-CACHE-USER-DIMENSION
- 新增 Open：TD-A-D9-SDK-MODEL-LIST-UAF（Risk/Medium——SDK get_model_list 外部调用 UAF）
- **[Review #2 登记]** TD-A-005-01/02 的 VM 探测（grep 无 cancel API + 4 线程并发挂起）无持久化日志——已在台账标注"宿主终端输出"，证据缺口已关闭（2026-08-18 日志落盘）

## 架构与能力边界依据

- 技术债台账：docs/technical-debt/TECHNICAL_DEBT_REGISTER.md
- Day3 契约：docs/day3/06_provider_contract_v1.md（category 六值 + scope 五值同步）
- SDK API：third_party/kylin-coreai-embedding/reference/embedding_api.h
- 基线：docs/baseline/01_sdk_model_abi_baseline.md（`text_embedding_get_model_list` 原文档标禁调——R-1 依据，TD-A-005-04 降级 PARTIAL）

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `memory-service/providers/embedding_provider.py` | TD-A-005-03/04/05/06 |
| `memory-service/providers/extraction_provider.py` | TD-A-D6-LLM-TOOL-INPUT + TD-A-D7-LLM-HANG-DEGRADE |
| `memory-service/embedding/embedding_service.py` | TD-A-005-09 + Review #6/#7 |
| `cpp-bridge/include/embedding_bridge.h` + `src/embedding_bridge.cpp` + `src/py_module.cpp` | TD-A-005-04 + Review #4/#5 |
| `scripts/verify_day4_vm.sh` | TD-A-005-08 |
| `docs/day3/06_provider_contract_v1.md` + `docs/day4/08_bridge_provider_skeleton.md` | TD-A-005-07 + TD-A-D8 + Review #3 |
| `docs/day8/01_task_card.md` + `02_pr_description.md` | Reviewer TD-01/TD-02 引用 |
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 10 Resolved + 2 Wontfix + 新增 TD-A-D9-SDK-MODEL-LIST-UAF |
| `memory-service/tests/test_td_a_005_03_05.py` | 7 项 |
| `memory-service/tests/test_td_a_005_09.py` | 4 项 |
| `memory-service/tests/test_td_a_local_batch.py` | 6 项（含 Review #8 真并发） |
| `evidence/l2-kylin-vm/td_a_005_04_model_name.log` | 含原始终端输出（exit=0, dim=768, loaded=True） |
| `evidence/l2-kylin-vm/td_a_005_09_sdk_missing.log` | TD-A-005-09 VM 证据 |
| `evidence/l2-kylin-vm/td_a_005_01_no_cancel_api.log` | TD-A-005-01 Wontfix 证据 |
| `evidence/l2-kylin-vm/td_a_005_02_concurrent_hang.log` | TD-A-005-02 Resolved 证据 |

## 数据库与配置变化

无（不涉及 SQLite/Schema/Alembic）

## 测试结果

### L0 (单元测试 + 静态检查)

```
$ python3 -m py_compile memory-service/providers/*.py memory-service/embedding/embedding_service.py
COMPILE OK
$ g++ -std=c++17 -Icpp-bridge -Icpp-bridge/include -fsyntax-only cpp-bridge/src/embedding_bridge.cpp
SYNTAX OK
```

### L1 (组件集成)

```
$ /home/fff/projects/kylinOS-agent-memory/.venv/bin/python -m pytest tests/ -q
272 passed, 49 skipped
```
- 新增 **17 项** TD 回归测试（7+4+6，含 Review #8 真并发互斥）全绿
- skipped 47→49：新增 2 项 `test_embedding_service_real.py` 用例（KYLIN_L2=1 门控，本地无 SDK skip，VM 上真实执行）

### 安全与假实现审查

- R3/R4/R5 红线保持（D 主审确认"无 Mock 冒充 Runtime；_SdkMissingProvider 为空向量降级非假实现"）
- TD-A-005-09 降级语义：明确空向量 + degraded 标记，非假数据
- [Review #6] ERR_CONFIG_CONFLICT 不再被误判为 SDK 缺失

### L2 麒麟虚拟机证据

- TD-A-005-09（判别性充分）：so 缺失 embed ok/degraded=True/dim=0 + health bridge_loaded=False；apt 重装后 dim=768 复验
- TD-A-005-04（Wontfix）：SDK get_model_list 外部调用 UAF（10/10 段错误），无安全动态查询路径。模型名来自 SDK 日志确认的硬编码值（VM 实测 exit=0，dim=768，loaded=True，evidence/l2-kylin-vm/td_a_005_04_model_name.log 含原始终端输出）
- TD-A-005-01/02：宿主终端探测日志已落盘（td_a_005_01_no_cancel_api.log + td_a_005_02_concurrent_hang.log）

### L3 (全链路验收)

不适用（技术债收口）

## 性能影响

- TD-A-005-04：model_info() 直接返回缓存值（无 SDK 调用，零开销）
- TD-A-D7-LLM-HANG-DEGRADE：挂死检测 O(1)，仅超阈值重建 executor（一次性）
- TD-A-005-09：降级路径不调用 SDK（纯返回空向量）
- Review #5：get_default_model_name 持 mutex_（与 embed 相同开销，无额外）

## 已知限制

- **TD-A-005-01 Wontfix**：SDK 无 cancel/abort API，现有超时保护为最终方案
- **TD-A-005-02 Resolved 语义**：SDK 单会话串行，顺序调用为正确决策
- **TD-A-005-04 Wontfix**：SDK get_model_list 外部调用 UAF（10/10 段错误），无安全动态查询路径；模型名集中到 Bridge 单点缓存（SDK 日志确认值）
- **维持 Open（3 项）**：D6-EXEC-RACE（非阻断并发风险）、D6-TOOL-PARTIAL（partial result 无格式 + 契约字段）、D7-CACHE-USER-DIMENSION（契约无可信 user_id）
- **新增 Open（1 项）**：TD-A-D9-SDK-MODEL-LIST-UAF（Risk/Medium——SDK get_model_list 外部调用 UAF）

## 回滚方式

- `git revert 622d3c3`（连同其下 7 commits）即恢复 main @ 5bd2c3e 基线
- 新增测试文件随之移除；生产代码回退后恢复原 TD 状态（Open），不影响既有功能
- C++ 改动回退后 `model_info()` 回退原硬编码默认名（原行为，不破坏契约，当前实现亦为硬编码）

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
