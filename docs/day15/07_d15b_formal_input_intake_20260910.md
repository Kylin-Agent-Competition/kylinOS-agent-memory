# D15B：D14B Formal Input Intake 更新（2026-09-10）

## 结论

`main@c5573c1ce75ad08427b86e3551074e18ed806279`（PR #174）已补齐并可消费 D13D/D14D/capture 三份机器可读 handoff、四个生产 capture runner、VM 访问事实和一次 SQLite truth capture/receipt。D15B 的 formal-input 状态由“全部缺失”收窄为 `PARTIALLY_REMEDIATED`。

这不是 Formal L3 完成：原始 `kylin-memory-a-d14a-0.1.0-d14a.tar.gz` 字节仍不可得。新提交的 `rebuilt-ba3b50e` 包 SHA 为 `de4050ee22d3c70f67c3cbf314ada1a76ac7d8d0527d7ba397477122553a30d8`，其身份被明确标为 provenance-labeled rebuild，不得作为原冻结 tar SHA `2222c904cd2fca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` 的替代。

## 已接收的 control-plane 输入

| 输入 | SHA-256 | 结论 |
| --- | --- | --- |
| `release/handoff/d13d-handoff.json` | `4138e4f839971132315f3109cd521a32a31685dccf80bbb9210508b98c915b3a` | `D13D_FROZEN`，tested commit 为 `ba3b50e…`。 |
| `release/handoff/d14d-handoff.json` | `1265d7fd27b0d2c986d21b5e2f1c4ed2a2da83bc6a0a58d88ceaa6f0ad206130` | `L3_READY`，保留 `release_ready=false` / `production_ready=false` 边界。 |
| `release/handoff/d14b-capture-handoff.json` | `8457db5a8ec773cb968e80e7e8226212324cdc6ba2ef957fd42ffe0523707ec2` | 固定 SQLite truth、FTS5、Vector、RRF 四类 runner 的路径、SHA 和 command ID。 |

## 当前停止线

1. `run_d14b_preflight.py` 强制验证实际 package tar 与 manifest 的原冻结身份；当前不可通过此 gate；
2. 未获得原始字节时，只能等待有权主体作出新的 package identity/refreeze 决定，不能由 B 将 rebuild 自行升级；
3. package-bytes gate 通过后，才可在正式 clean VM 使用已固定 runner 生成新的 Formal L3 evidence root 和 receipts；
4. sealed retrieval eval inputs、正式 execution binding 和 final metrics 仍是独立的 E/D/B 后续条件。

## 跨轨验证风险

在本 Windows 工作站，新加的 `test_preflight_accepts_a_clean_matching_handoff` 失败于 `source_bindings.*.production_db_path` 的 POSIX `/home/...` 路径被 `pathlib.Path.is_absolute()` 视为非绝对路径。该测试/脚本属于 D14B control-plane，本记录不修改它；D 轨应调整 host-independent 路径验证或明确将该用例限制为 Linux。PR #174 的 Linux CI 为 green，这不构成对 Windows 回归的替代证明。
