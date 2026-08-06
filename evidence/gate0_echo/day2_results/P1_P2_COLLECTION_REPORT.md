# Day2 P1+P2 证据收集汇总报告
# Timestamp: 2026-08-06T13:32:57

## 收集的证据文件

| 文件 | 对应缺口 | 状态 |
|------|---------|:----:|
| E3_client_all_6x6.log | P1-1: E3 独立6项全量测试 | ✅ |
| E6_kysec_acl_dev.log | P1-2: E6 独立Dev模式ACL | ✅ |
| P1_3_rollback_reachability.log | P1-3: test_rollback.sh 可达性 | ✅ |
| P1_4_P1_5_unverified_check.log | P1-4/P1-5: UNVERIFIED标注 | ✅ |
| P1_6_to_P1_10_rollback_detail.log | P1-6~P1-10: 回退逐项对比 | ✅ |
| P2_2_runtime_dir_check.log | P2-2: RuntimeDirectory重查 | ✅ |
| P2_3_kysec_consistency.log | P2-3: KYSEC记录一致性 | ✅ |

## 仍需人工处理

- **P2-1**: index.yaml 补充登记 4 条 (D2-3, D2-4, D2-6, D2-7) — 需本地编辑
- **P0 问题**: 需修改代码后重新部署 (不在本次收集范围)

