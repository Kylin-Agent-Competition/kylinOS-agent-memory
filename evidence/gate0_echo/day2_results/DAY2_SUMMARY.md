# Day2 麒麟 VM 运行时验证 — 证据汇总
# Timestamp: 2026-08-06T09:51:06

## 产出文件清单

| E1_build.log | 干净CMake构建日志 |
| E2_client_kaiming_store.log | KAIMING-STORE修复后测试输出 |
| E4_systemd_lifecycle_rerun.log | 修复后完整生命周期重跑 |
| E5_kysec_acl_systemd.log | Systemd模式ACL授权/回退 |
| E7_kaiming_hook_attempt.log | 真实Hook尝试过程 |
| D2_3_deploy_startup.log | 部署和启动可复现 |
| E9_socket_path_audit.log | 全链路Socket路径一致性审计 |
| D2_6_kysec_scope.log | KYSEC授权口径确认 |
| E8_rollback_baseline_compare.log | 回退对照基线逐项对比 |

## 验证结果总览

详见各阶段日志文件。
