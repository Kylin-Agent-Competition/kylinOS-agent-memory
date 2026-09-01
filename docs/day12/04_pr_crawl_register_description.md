# PR 描述：历史 PR 技术债爬取补登 + A 轨需求落地（TD-047~052 + A-REQ-01/02）

## 背景

按 Day11 跨轨对接需求（`Day11跨轨依赖与需求清单_对接版_20260901.md`）与 D12 功能冻结阶段要求，爬取 GitHub 全量历史 PR（70 个），对照 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 技术债总账，核查是否存在「声称已登记 / 已声明已知限制」但实际从未写入总账的技术债；并对 A 轨 P1/P2 需求（A-REQ-01 生产接线、A-REQ-02 治理）做实际落地。

## 一、发现并补登的技术债（TD-047~052）

| TD | 来源 | 标题 | 严重度 |
|---|---|---|---|
| TD-047 | 对接版 A-REQ-01（P1） | production 删除 consumer 未接线（删除事件生产组装缺口）——**本 PR 已实现** | Medium |
| TD-048 | 对接版 A-REQ-02 | TD-A-D10-CACHE-INVALIDATION 代码/PR 声称「已关闭」但总账仍 Open（D11A #84 未回写；time_window 未实现）——治理不一致 | Low |
| TD-049 | PR #57 | 声明登记的 TD-1~3（/tmp 固定跨用户路径 / L2-C1 sudo mv 测试设施风险 / evidence metadata 精化）从未写入总账 | Medium |
| TD-050 | PR #36 LOW-01 | implicit 隐式偏好推断未实现（explicitness 仅保留枚举/接口，规则路径恒 explicit） | Low |
| TD-051 | PR #42 | 声称「登记 TD 前置项」的 cmake 系统包未安装（C++ Bridge 编译阻塞）未入账 | Medium |
| TD-052 | PR #100（D12A） | `_embed_hang_threshold_ms` 默认 60s 进程级硬编码未参数化到 config.toml | Low |

## 二、A 轨需求落地

### A-REQ-01：删除 consumer 生产接线（P1）——已实现

架构归属：`EmbeddingService` + `CacheInvalidator` 位于 embedding UDS 子服务进程（`embedding/server.py`），故删除 consumer 在此进程接线而非 `app.py`。

- `embedding/server.py`：新增 `--register-deletion-consumer`/`--db` seam，构造 `build_deletion_consumer(EmbeddingService)` + 启动 `OutboxWorker` 消费删除事件 → `CacheInvalidator`；不 `init_schema`（schema 由主服务/Alembic 管理，FR-DB-002）。
- `embedding/outbox_consumer.py`：对齐权威事件类型 `forget.executed`（`repositories.EVENT_FORGET_EXECUTED`），向后兼容 `memory.deletion`/`deletion`（`DELETION_EVENT_TYPES` 集合）。
- 验收：无 consumer/异常时保持 retry/Dead Letter；麒麟 VM 用 `--register-deletion-consumer --db <db>` 真实验证（待 VM 跑）。

### A-REQ-02：TD-A-D10-CACHE-INVALIDATION 治理（P2）——已修正

- `TECHNICAL_DEBT_REGISTER.md`：TD-A-D10 状态行补治理说明——条件①（Outbox 消费接线）由 A-REQ-01 推进；条件②（time_window 批量失效）未实现 → 保持 **Open**，不得改 Resolved，time_window 独立跟踪 TD-048。

## 三、修改范围

- `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`：新增 TD-047~052 + TD-A-D10 治理说明。
- `memory-service/embedding/server.py`：A-REQ-01 接线 seam。
- `memory-service/embedding/outbox_consumer.py`：事件类型对齐（`forget.executed`）。
- `docs/day12/04_pr_crawl_register_description.md`：本文件。

## 四、验证

- 注册表 12 列结构合法；TD-047~052 均唯一存在。
- `server.py`/`outbox_consumer.py` `py_compile` 通过；`bash -n` 通过（verify 脚本）。
- A 轨回归：`test_embedding_service + d9 + d10 + d12a` = 80 passed（含 forget.executed 对齐测试）。
- A-REQ-01 L2 麒麟 VM 证据待 VM 运行后回填。

## 五、关联

- 关联 PR：#100（D12A，含 TD-046 与 verify_day12a_vm.sh、test_embedding_d12a.py）
- 关联文档：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
