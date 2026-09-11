# M2 RC10 真实绑定与生产导入证据包

本目录是 M2（RC10 真实 Main binding + production import + readback + replay + conflict）
的 Main 侧证据包，由 `scripts/main_to_data_m2_receipt.py` 机械化校验并生成
`interfaces/main_to_data/m2_import_receipt.json`。

> `status=PASS` 只表示 **Main 侧证据就绪**（`MAIN_M2_EVIDENCE_READY=true`）。
> 最终 `M2=PASS` 仍由 Data-R 在独立复核后一次性裁定（`final_m2_adjudication=PENDING_DATA_R_REVIEW`）。

## 输入（Data 侧，未改写）

- `data_in/m2_main_binding_request.json` — Data 预绑定请求（PR #68）
- `data_in/m2_prebinding_candidates_10.jsonl` — `os_kb_0001..os_kb_0010` 候选
- `data_in/m2_prebinding_manifest.json` — 预绑定 manifest
- `data_in/v4.1_M2_DATAR_ADMISSION_20260911.json` — Data-R 准入 receipt
  （`APPROVED_FOR_M2_RC_PREBINDING_ONLY`，10/10）

冻结 KB400 候选源未被改写；本证据包只消费上述只读交接物。

## Main 侧执行（真实路径，非 mock）

1. **受控来源供给**：`scripts/main_to_data_m2_provision_sources.py`
   通过正式 `event.ingest` 处理器（EventPipeline + `SourceAdmissionPolicy` +
   `repo.insert_source_event`）为 10 条候选生成同用户、`allow_extraction` 的
   真实 source event。未手工 INSERT `source_events`，未手填 admission 决策。
   受控来源层为 `os_controlled_authored`，`source_reference` 由候选 provenance
   推导：`os_controlled_authored://OSRETR-01/retr_d1c_000X`。
2. **真实绑定**：`scripts/main_to_data_m2_bind.py`（只读）逐条校验来源事件
   存在、同用户、已准入、descriptor 一致、内容与 provenance 兼容，输出
   `main_out/m2_rc_binding_response.json`（10/10，checks 全 0）。
3. **Data-B 最终 RC 组装**（Data 仓 `feat/B-m2-rc-final-assembly` 基线新增的
   `scripts/v4/build_m2_final_rc.py`）：join Data-R receipt + Main binding
   response，生成 `final_rc/input_rc_10.jsonl` + RFC 8785 `source_manifest.json`，
   不写任何生产身份。
4. **真实生产导入**：`scripts/main_to_data_m2_import.py` 对真实 migrated Main DB
   执行 M1-KB v2 导入；首次接受机械断言 `v1/candidate`，随后授权读回、
   same-request replay、same-key/different-request conflict 探针。

证据运行于干净提交 `0148abe4e6d2ec9ee75a2ca612e1e9cb6bc7d25e`
（`source_main_commit_dirty=false`）。

## 关键哈希

- `input_rc_10.jsonl` exact SHA-256：`8879a54a2c2b95fc58d6af54d2d91962748728231ef64ab354a069e4ad48c756`
- RFC 8785 `source_manifest.json` SHA-256：`9b83ccdcd00095a517360feed55217957b69900f617a8ad29514b1debf711874`
- M1-KB contract SHA-256：`3b2b3ee1664f5f740b231640f545baa50f8dff63d691a76855c228eeca9a645c`
- migrated DB（Alembic head `20260911_main_to_data_m2_registry`）SHA-256：
  `d8a3c4519819de47b9c019d473948c0e41ace7cdc95060fb95831c960acd1210`（外部运行库，见 `db/`）

## 执行结果（由 receipt 机械校验）

- `RC10_BINDING = 10/10`；`CROSS_USER=0`；`SOURCE_NOT_ADMITTED=0`；`PROVENANCE_MISMATCH=0`
- `imported_count=10`；`rejected_count=0`；首次接受 `accepted_version=1 / v1 / candidate`
- 授权读回 10/10（`current_version=1`，`current_memory_status=candidate`）
- same-request replay 10/10：`replayed=true`，身份快照不变，生产状态零增量
- same-key/different-request conflict 10/10：`idempotency_conflict`，生产状态零增量
- durable registry：`main_to_data_import_registry` / `main_to_data_manifest_registry`，无 TTL

## 复算与门禁

```bash
PYTHONPATH=memory-service python3 scripts/main_to_data_m2_receipt.py \
  --evidence-dir evidence/main_to_data/runtime_gate/m2_rc_import \
  --check interfaces/main_to_data/m2_import_receipt.json
```

CI（`.github/workflows/baseline-check.yml`）在 M2 L1 测试后执行同一守卫，
任何证据/收据漂移都会在合并前失败。

## 边界

- 本证据包不宣称 M3、Runtime Gate 或 Data 侧冻结源语义。
- 受控来源供给是 worklist 允许的“走 Main 正常 source-event ingestion/admission
  路径生成可审计来源”，不是替代证据；它不写生产知识身份。
