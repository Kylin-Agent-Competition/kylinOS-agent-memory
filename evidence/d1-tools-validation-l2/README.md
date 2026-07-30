# D1 工具脚本 L2 验证证据

本目录包含 D1 工具脚本在银河麒麟虚拟机上的 L2 级别验证证据。

## 测试环境总览

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03+08:00 |
| 操作者 | ZhouYifan |

## 测试用例与证据

| 编号 | 测试项 | 证据文件 | 状态 |
| --- | --- | --- | --- |
| 01 | env_check.sh 环境自检 | 01_env_check_test.md | PASS |
| 02 | install_memory_service.sh 安装测试 | 02_install_service_test.md | PASS |
| 03 | uninstall_memory_service.sh 卸载测试 | 03_uninstall_service_test.md | PASS |
| 04 | snapshot_package_versions.sh 版本快照 | 04_snapshot_packages_test.md | PASS |
| 05 | rollback_packages.sh 安全回退 | 05_rollback_test.md | PASS |
| 06 | kysec_allow.sh KYSEC 放行 | 06_kysec_allow_test.md | PASS |

## 测试结果汇总

| 指标 | 数值 |
| --- | --- |
| 总测试项 | 6 |
| 通过 | 6 |
| 失败 | 0 |
| 跳过 | 0 |

## 证据文件格式

每个测试证据文件必须包含以下字段：
- Commit / 分支 / 银河麒麟版本 / 架构
- VirtualBox 虚拟机与快照名称
- 执行时间 / 操作者
- 前置条件
- 执行命令
- stdout/stderr 原始输出
- 退出码
- 执行前/后状态
- 日志路径
- 已知限制

原始日志文件存放在 `raw_logs/` 目录下，截图存放在 `screenshots/` 目录下。