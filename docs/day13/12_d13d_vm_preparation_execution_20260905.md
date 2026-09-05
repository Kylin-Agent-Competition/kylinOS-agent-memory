# D13D 麒麟 VM 环境准备执行记录（2026-09-05）

## 状态

`PREPARED` / `BLOCKED`。本批完成候选基线的 VM 隔离部署准备和 L2 UDS 预检；未执行正式 D13B 评测，未发布正式指标，也未将 D13D 标记为 `FROZEN`。

## 已完成

- 被测代码：`7242935bee5f230cee0535d5e28dbe1e60a302f6`。
- VM：`Kylin-desktop-neo D12-TDR`，UUID `32070b0e-c7f5-45bd-b086-2262ba960f08`，Kylin V11 2603、kernel `6.6.0-76-generic`、8 CPU、8 GB RAM。
- 先创建回滚点：`d13d-pre-7242935-20260905-0858`，UUID `ea4f8a16-3b43-47c0-9cd5-5df823089aaa`。
- 候选工作树：`/home/kylin-agent/kylinOS-agent-memory-d13d-7242935`，来宾 HEAD 等于被测提交且 `git status --porcelain` 为空。
- 候选使用独立 SQLite、UDS socket 和 state 路径启动；Alembic head 为 `20260902_add_memory_relation_conflict`。
- 长度前缀 JSON `health` 和 `echo` 均收到成功 envelope。`health.data.status=degraded` 是 `--no-outbox` 隔离预检的预期结果，不能作为正式运行健康结论。
- 旧的 active `kylin-memory.service` 未改动，仍指向旧工作树 `053754d...`。
- B 轨回执所引用的 D13B CLI、评测模块与测试入口在 `053754d...` / `7242935...` 间 blob ID 相同，D13D-04 关闭。

## 原始证据

目录：`evidence/l2-kylin-vm/d13d_20260905T090507Z/`

其中包含 VM probe、部署前状态、bundle hash、候选 clone、独立迁移/启动、UDS probe、结构化环境清单和 `SHA256SUMS`。本批证据的限制及未关闭门禁以 `environment_freeze.json` 的 `freeze_status=BLOCKED` 为准。

## 仍然阻塞

1. D13E Dataset/Gold 仍为候选状态，未经过 D Reviewer 封存。
2. 正式 PASS/FAIL 阈值、批准记录与 hash 未交付。
3. 没有可填入 D13B bundle 的受批准实值 provenance，因此未运行正式 CLI。
4. 正式 user-service 尚未切换到候选基线；必须在输入封存后按本轮快照执行，或得到等价部署方案批准。
5. 证据索引尚未登记正式结果，因为本批没有正式评测报告。

## 回滚

若后续部署失败，可恢复 VirtualBox 快照 `d13d-pre-7242935-20260905-0858`。本批保留的隔离候选进程、socket 和数据库均在 `d13d-7242935` 命名空间内，未替换现有 user service 的 wrapper、unit、生产 socket 或默认数据库。
