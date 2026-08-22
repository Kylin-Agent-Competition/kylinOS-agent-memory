# D4D VM L2 验证结果（2026-08-21）
- commit: ed9949c
- 迁移验收（2.1 upgrade / 2.2 schema / 2.3 往返）: PASS / PASS / PASS
- systemd 部署（启动/重启/回退/日志/socket）: PASS / PASS / PASS / PASS / PASS
- FTS5 中文+软删除: PASS
- busy_timeout 降级: PASS
- UDS 断开/超时: PASS
- 执行人: kylin-agent（手动执行，SSH 自动化辅助）
- 缺陷注记1: alembic.ini `script_location=migrations`，须在仓库根以 `-c migrations/alembic.ini` 执行（手册 cd migrations 会报 Path doesn't exist: migrations）
- 缺陷注记2: UDSGatewayServer.stop() 未 unlink socket 文件；Linux 下停后 connect 成功、请求被 ECONNRESET 拒绝（建议登记技术债 TD-IPC）
