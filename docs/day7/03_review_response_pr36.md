# PR #36 复审响应（REWORK 落实逐项证据）

> 分支：`feat/day7-preference-extraction` @ `8e93118`（Review 修复 commit，已推送）
> 本文档供 Reviewer 逐项核对 REWORK 结论（HIGH-01/02、MEDIUM-01~04、LOW-01~03）的落实情况与证据位置。

## 一、Reviewer 下一轮复审重点：三件事的真实性确认（均已有直接证据）

### 1️⃣ TABLE 20 临时原句真正经过 `ExtractionProvider.extract_preferences()` 主链产生正确 candidate

- **修复**（`memory-service/providers/extraction_provider.py`）：规则入口两阶段——`PREFERENCE_EXPLICIT_PATTERN`（显式偏好词）未命中时启用 `PREFERENCE_INSTRUCTION_PATTERN`（`memory-service/providers/preference_rules.py`：时态限定词 这次/本次/现在/当前/今天 + 指令动词 只用/控制在/保持/不要/改用…，**通用模式，非固定字符串硬编码特判**）
- **验证输出**（最终代码实测）：

```
HIGH-01 OK: 原句主链 -> response.length | temp= True persist= False scope= session
HIGH-01 OK: 长期原句无回归 -> scene.meeting.preference scope= topic
```

- **E2E 回归测试**：`tests/test_extraction_provider_d7.py::test_d7_rule_table20_temporary_original_sentence`（原句 `这次只用三句话回答`，断言 `len==1`、`is_temporary is True`、`should_persist is False`、`scope=="session"`、`memory_status=="candidate"`）+ `test_d7_rule_instruction_generalizes`（同类临时指令"这次不要用表格"，证明非特判）
- 长期原句 `以后所有会议总结都控制在三段内` 无回归（`test_d7_rule_long_term_example` 保持通过）

### 2️⃣ required confidence 恢复 R4 candidate-level isolation，不再用 0.5 掩盖非法输入

- **修复**（`extraction_provider.py::_degrade_optional_fields`）：删除 `_DEFAULT_CONFIDENCE` 与 confidence 降级分支；docstring 明确 confidence 为契约 required 字段（Day3 契约 + E 轨 §3.2 `confidence_score`）
- **验证输出**（最终代码实测）：

```
HIGH-02 OK: missing/'high'/‑0.1/1.1/2.0 全部 candidate-level reject + validation audit
```

- **回归测试**：`test_field_reject_invalid_confidence`（参数化 `"high"/-0.1/1.1/2.0`）+ `test_field_reject_missing_confidence`（缺失）——均断言 `cands == []` + `validation` audit 含 `confidence`

### 3️⃣ 修复后最终代码重新取得可信 L1 / 麒麟 VM L2 Evidence

- **L1 已刷新**：`evidence/l1/day7_pref_extraction_local.log` —— **224 passed + 47 skipped**（checksum `a3224638c0c7fa1614b9cd84b6ab5a2af224fa0e559cffc26194d06e88c889f5`），含最终修复 commit `8e93118` 全部测试
- **L2 麒麟 VM**：⏳ **待执行**——生产代码已变更（`8e93118`），旧证据（264 @ `e3a3f9e`）不再覆盖；VM 侧执行命令与预期如下（见"四、L2 待办"）

## 二、逐项响应（P0 必须修复）

| 项 | 处置 | 证据位置 |
|----|------|----------|
| HIGH-01 TABLE 20 原句主链抽取 | ✅ 已修复：指令式规则入口（通用模式） | preference_rules.py `PREFERENCE_INSTRUCTION_PATTERN`；extraction_provider.py `_extract_preferences_rules`（两阶段）；测试见上 |
| HIGH-02 confidence 非法值降级 0.5 | ✅ 已修复：required 字段候选级拒绝 + audit | extraction_provider.py `_degrade_optional_fields`；测试 `test_field_reject_*` |
| 长期原句无回归 | ✅ 已验证 | `test_d7_rule_long_term_example` 保持通过 + 综合验证输出 |

## 三、逐项响应（P1 建议 + Evidence）

| 项 | 处置 | 证据位置 |
|----|------|----------|
| MEDIUM-01 is_temporary && should_persist 矛盾 | ✅ 已修复：E 轨 §3.2 规范化（is_temporary=True → should_persist=False）+ audit（`temporary-implies-no-persist`） | extraction_provider.py `_validate_candidate`；测试 `test_llm_temporary_persist_contradiction_normalized` |
| MEDIUM-02 缓存键缺 user 维度 | ✅ 已登记 **TD-A-D7-CACHE-USER-DIMENSION**（含 5 条关闭条件） | docs/technical-debt/TECHNICAL_DEBT_REGISTER.md |
| MEDIUM-03 LLM 永久挂死 → 永久 busy-skip | ✅ 已登记 **TD-A-D7-LLM-HANG-DEGRADE**（验收：真实 LLM 接入前需 worker reset/executor 重建/health recovery 之一） | docs/technical-debt/TECHNICAL_DEBT_REGISTER.md |
| MEDIUM-04 L1 Evidence 旧版本 | ✅ 已刷新（224 passed + 47 skipped）；PR 描述/交接文档/index.yaml/L1 日志数字统一 | evidence/l1/day7_pref_extraction_local.log |
| LOW-01 implicit 无真实实现 | ✅ 已注明：implicit 仅保留 Schema 枚举与 Provider 接口能力，本阶段未实现基于多 Turn 行为证据的隐式偏好推断 | docs/day7/01_task_card.md（PR #36 落实记录）、docs/day7/02_pr_description.md（已知限制） |
| LOW-02 评测字段文档统一 | ✅ to_evaluation_record 输出含 memory_status，任务卡/PR 描述/JSONL 字段已统一 | docs/day7/01_task_card.md / 02_pr_description.md |
| LOW-03 缓存/超时边界测试 | ✅ 已补充 TTL=0（`test_cache_ttl_zero_expires_immediately`）、timeout=0（`test_llm_timeout_ms_zero_immediate_timeout`）、cache hit 不重复调 LLM（`test_cache_hit_does_not_call_llm_again`） | tests/test_extraction_provider_d7.py |
| L0 | ✅ compileall 通过 | — |
| L1 | ✅ 224 passed + 47 skipped（顺序无关） | evidence/l1/day7_pref_extraction_local.log |
| L2 | ⏳ 待 VM 重跑（见下） | — |
| L3 | 不适用（Provider 层增量，按计划 D14 执行） | — |

## 四、L2 待办（唯一剩余项）

麒麟 VM（当前运行中）执行：

```bash
cd /mnt/shared && PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -q
```

预期：**271 passed / 0 skipped / 0 failed**（= 224 + 47）。完成后回填：
- `evidence/l2-kylin-vm/day7_verify_latest.log`（tested_commit = `8e93118`）
- `evidence/index.yaml`（D7-A-PREF-EXTRACTION：tested_commit/evidence_commit/checksum 更新）
- 同步 PR 描述与交接文档数字

> 作者侧无法代跑：SSH 端口转发（2222→22）Connection refused（VM 内 sshd 未监听）、VBoxManage guestcontrol 无 guest 凭据——L2 需宿主执行人（或提供 guest 访问凭据）。
