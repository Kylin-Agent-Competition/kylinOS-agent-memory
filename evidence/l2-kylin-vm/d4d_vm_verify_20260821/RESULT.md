# D4D VM L2 验证结果（2026-08-21 补录 2026-08-22）

## 证据 commit 绑定（PR#52 Issue 6 / U-2 修正）

- ① 原始验证 commit：`ed9949c`（feat(D4D): IPC Gateway + 数据库层…骨架）→ 当前分支 rebase 后对应 `b2a3d04`
- ② 补录验证 commit：`35e8c54`（init_schema 触发器幂等 + UDS stop unlink）→ rebase 后 `2770e26`；PR#52 审查收尾 `d2b7205` → rebase 后 `9fe84c7`
- ③ 实际上传并验证的文件 SHA256（补录 commit `2770e26` 处文件内容）：
  - migrations/versions/001_initial_schema.py = `01c3f53c63c9f9f8017b7226e043c1d91d3bd408448c7fc61f0d1fa99ea6b88a`
  - memory-service/db/schema.py = `510aaa9a5a8c834bdae1301ddc24dfb2caacd294b4fdf236a3b91541d43f279f`
  - memory-service/db/engine.py = `3ffdb97a607dc6c6ce4c423310bbe4ae88556f76e44bd29df0d826cd59b9e796`
  - memory-service/gateway/server.py = `9da2ab4b07be2f49942b07391771e6ff5588131c5a712d73c2c156e2c133d2a5`
- ④ 当前最终证据对应 HEAD：`9fe84c7`（`fix(D4D): PR#52 审查收尾…`，rebase 后）

> 说明：本证据的 IDEMPOTENT_OK / UDS unlink 等结果由补录 commit（`35e8c54`→`2770e26`）
> 修复后的 schema/migration 产生，非原始 `ed9949c` 版本；原始版本存在「trigger already
> exists」非幂等缺陷，无法通过幂等自检。故 commit 绑定以补录版为事实依据，不再将
> `ed9949c` 单独标为证据归属。

- 迁移验收（2.1 upgrade / 2.2 schema / 2.3 往返）: PASS / PASS / PASS
- systemd 部署（启动/重启/回退/日志/socket）: PASS / PASS / PASS / PASS / PASS
- FTS5 中文+软删除: PASS
- busy_timeout 降级: PASS
- UDS 断开/超时: PASS
- 幂等自检（init_schema 二次调用）: PASS（IDEMPOTENT_OK）
- socket 权限位: srw------- / 0600 / kylin-agent:kylin-agent
- 执行人: kylin-agent（手动执行，SSH 自动化辅助）
- 补录说明: 2026-08-22 修复 init_schema() 触发器幂等 + UDS stop unlink（TD-IPC-001）后重跑第 4/5/6 步；归档重跑不再报 trigger already exists
- 缺陷注记1: alembic.ini script_location=migrations，须在仓库根以 -c migrations/alembic.ini 执行
- 缺陷注记2: UDSGatewayServer.stop() 已修复 unlink socket 文件（TD-IPC-001 Resolved）
