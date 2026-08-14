# PR #36 最终核对清单（两轮 Review 全部项证据链）

> 分支：`feat/day7-preference-extraction`｜HEAD：`d221464`（最新；生产代码 `e5c52e6`）
> 生成：2026-08-14 ｜ 用途：Reviewer 逐项核对的完整证据链（两轮 REWORK 共 14 项 + Evidence）

## 一、综合验证结果（最终代码实测，29/29 PASS）

```text
PASS | HIGH-01 原句主链（这次只用三句话回答 → temp/persist=False/scope=session/candidate）
PASS | HIGH-01 长期无回归（以后所有会议总结都控制在三段内 → topic/长期）
PASS | HIGH-02/03 reject conf=True/False/'0.9'/'1'/'high'/‑0.1/1.1/2.0（validation audit）
PASS | HIGH-03 missing key（raw dict 不含 confidence 键）
PASS | HIGH-03 legal float 0.0/0.5/0.9/1.0（通过）
PASS | MEDIUM-01 矛盾规范化（temporary-implies-no-persist audit）
PASS | MEDIUM-05 category/scope/explicitness/is_temporary/should_persist=None → 默认值 + audit
PASS | MEDIUM-08 负向 不要慌，再试一次/别问了/保持联系/不要忘记密码/今天天气不错（0 候选）
PASS | MEDIUM-08 正向 这次只用三句话回答/这次不要用表格/这次至少列出三个要点（1 候选）
```

## 二、两轮 Review 项核对

| 项 | 状态 | 证据位置 |
|----|------|----------|
| HIGH-01 TABLE 20 原句主链抽取 | ✅ CLOSED | test_extraction_provider_d7.py `test_d7_rule_table20_temporary_original_sentence` + 综合验证 |
| HIGH-02 confidence→0.5 降级 | ✅ CLOSED | `_degrade_optional_fields` 已删 _DEFAULT_CONFIDENCE；`test_field_reject_invalid_confidence` |
| HIGH-03 confidence 无 strict 类型约束 | ✅ 已修复 | `Field(strict=True, ge=0.0, le=1.0)`（Preference+Knowledge）；10 种非法输入 reject + 合法 float 通过 |
| MEDIUM-01 is_temporary/should_persist 矛盾 | ✅ CLOSED | `_validate_candidate` 规范化 + `temporary-implies-no-persist` audit |
| MEDIUM-02 缓存键缺 user 维度 | ✅ TD 登记 | TD-A-D7-CACHE-USER-DIMENSION |
| MEDIUM-03 LLM 永久挂死 → busy-skip | ✅ TD 登记 | TD-A-D7-LLM-HANG-DEGRADE |
| MEDIUM-04 L1 Evidence 旧版本 | ✅ 已刷新 | evidence/l1（229+47，被测 e5c52e6，checksum 77e8229a…，含元数据头） |
| MEDIUM-05 optional None 降级契约 | ✅ 方案 A | 显式 None → 默认值+audit；缺失不降级；`test_field_degrade_none_optional` |
| MEDIUM-06 GitHub PR Body 旧数据 | ⚠️ 仓库已最新，**PR 页面待同步** | docs/day7/02_pr_description.md；token 401 需宿主更新或手动粘贴 |
| MEDIUM-07 evidence_commit 不一致 | ✅ 已修正 | evidence/index.yaml evidence_commit=691db29（≠ tested_commit=8e93118）；index_contract 补语义 |
| MEDIUM-08 指令模式误报 | ✅ 已修复 | PREFERENCE_INSTRUCTION_PATTERN 时态词必选；5 负向 + 3 正向测试 |
| LOW-01 implicit 未实现 | ✅ 已注明 | 任务卡/PR 描述已知限制 |
| LOW-02 评测字段文档统一 | ✅ 已统一 | to_evaluation_record 含 memory_status |
| LOW-03 缓存/超时边界测试 | ✅ 已补充 | TTL=0 / timeout=0 / cache-hit 不重复调 LLM |

## 三、Evidence 状态

| 层级 | 状态 | 数值 |
|------|------|------|
| L0 | ✅ compileall | — |
| L1 | ✅ 已刷新 | **229 passed + 47 skipped**（被测 e5c52e6，checksum 77e8229a…） |
| L2 | ⏳ **待 VM 重跑** | 现有 271 @ 8e93118（HIGH-03 修复前）；e5c52e6 预期 **276 passed** |
| L3 | 不适用 | Provider 层增量，按计划 D14 |

## 四、待宿主执行

1. **VM L2 重跑**（约 9 秒）：
   ```bash
   cd /mnt/shared && PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service \
     LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 \
     /tmp/day6-venv/bin/python -m pytest memory-service/tests/ -q 2>&1 | tee evidence/l2-kylin-vm/day7_verify_latest.log
   ```
   预期 **276 passed / 0 skipped**；完成后回填 evidence（tested_commit=e5c52e6）→ index.yaml → 推送。
2. **GitHub PR #36 Body 同步**（MEDIUM-06）：更新 token 后 PATCH，或手动用 docs/day7/02_pr_description.md 更新 PR 页面。

完成上述两项后，若无新 HIGH/BLOCKER，PR #36 达到 Reviewer 目标结论 **PASS_WITH_DEBT**（保留 TD-A-D7-CACHE-USER-DIMENSION / TD-A-D7-LLM-HANG-DEGRADE）。
