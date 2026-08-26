# Day7E 偏好 UI 与版本持久化 —— 麒麟 VM L2/L3 验证清单

- **版本**：v1
- **状态**：`RUNTIME_UNVERIFIED`
- **阶段定位**：Day7 / E 轨验收规范配套的宿主验证清单（对 `day7-e-ui-version-acceptance-v1.md` 第六、七章证据清单的可执行化）
- **作者轨道**：E（记忆业务，整理验收判据为可执行清单）
- **执行轨道**：C（QML 偏好 UI）；D（SQLite 版本持久化）
- **Reviewer 轨道**：D（周子腾）主审

---

## 〇、定位与前提说明

1. **本清单不新增验收判据**：全部条目均源自 `day7-e-ui-version-acceptance-v1.md`（下称「验收规范」）第五、六、七章已列明的 C/D 轨证据清单，此处仅做**分层（L2/L3）、编号化与可执行化**，供 C/D 轨在麒麟 VM 内逐项执行并回填证据。
2. **E 轨纯业务策略无需 L2**：`preference_business_policy.py` / `preference_version_policy.py`（D7E-01/02/03）为纯函数/Pydantic 层，已完成 **L1**（退出码 0；具体 passed 数量以各次执行证据为准，不以固定数值作为当前态），不涉及 Embedding 维度 / UDS / QML / Hook，**不在本清单 L2 范围**。
3. **证据状态口径**：本清单所有条目初始状态均为 `RUNTIME_UNVERIFIED`；须由 C/D 轨在银河麒麟 VM（VirtualBox V11 x86_64）真实执行并保留真实命令、退出码、stdout/stderr 与日志后，方可回填 `HOST_VERIFIED`。
4. **禁止冒充**：
   - 不得以 E 轨策略的 L1 pytest 结果冒充本清单任一条目的验收通过（验收规范第九章）。
   - 不得以 UI 截图 / 数据库 schema 截图 / 静态代码存在冒充真实交互验收（验收规范第七章、第二章 §2）。
   - QML 真实交互须为 VM 内可操作的真实行为（真实 UDS 连接链路），不得以 Mock 冒充（验收规范 §七末尾）。

---

## 一、L2 —— 麒麟 VM 功能验证（C/D 轨各自职责）

### 1.1 D 轨：版本持久化（SQLite + `current_version` 指针）

| 编号 | 验证项 | 对应验收案例 | 验证要点 | 证据要求 | 状态 |
|------|--------|--------------|----------|----------|------|
| L2-D-01 | `current_version` 指针切换 | 5.1 CREATE / 5.3 UPDATE / 5.5 ROLLBACK | CREATE/UPDATE/ROLLBACK 后 `current_version` 正确指向目标版本，切换原子提交（事务一致性） | 真实执行日志 + 退出码 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-02 | 版本链事务完整性 | 5.3 UPDATE / 5.5 ROLLBACK | 事务提交/回滚后版本链一致：v1→v2→v3 链完整，`previous_version_id` 逐级指向正确 | 真实事务日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-03 | 并发更新冲突检测 | 5.4 NO_OP（并发场景） | 对 `memory_entries.version` 乐观锁字段的并发更新冲突检测与失败处理 | 并发测试日志 + 冲突错误码 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-04 | 回滚不删除中间版本 | 5.5 ROLLBACK | ROLLBACK 后 v1/v2/v3 历史记录仍完整保留在持久化层（不物理删除未来版本） | 落库查询结果 + 日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-05 | 跨用户查询隔离 | 5.7 跨用户隔离 | 不同 `user_id` 读写/回滚相互隔离，跨用户访问被拒绝且不静默允许 | 跨用户操作拒绝证据 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-06 | CREATE 首版落库 | 5.1 CREATE | `version=1`、`previous_version_id=None`、`current_version` 指向 v1 | 落库查询结果 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-07 | NO_OP 不写版本 | 5.4 NO_OP | 同 key+scope+value 重复提交不产生新版本记录、不推进 `current_version` | 版本计数不变证据 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-D-08 | COEXIST 独立首版 | 5.2 COEXIST | 同 key 不同 scope 各建独立 v1，旧 scope active 偏好不被 supersede | 落库查询结果 | ⬜ `RUNTIME_UNVERIFIED` |

### 1.2 C 轨：偏好 UI（QML，真实 UDS 连接链路）

| 编号 | 验证项 | 对应验收案例 | 验证要点 | 证据要求 | 状态 |
|------|--------|--------------|----------|----------|------|
| L2-C-01 | QML 历史列表渲染 | 5.3 UPDATE / 5.5 ROLLBACK | 偏好历史版本列表按版本链正确渲染（UPDATE 保留 v1、ROLLBACK 保留中间版本） | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-02 | 修改交互 | 5.3 UPDATE | 用户修改偏好触发 UPDATE，当前值更新为 vN 且历史保留 | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-03 | 回滚交互 | 5.5 ROLLBACK | 回滚操作触发 ROLLBACK，当前值切换为目标历史版本且中间版本历史保留 | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-04 | 临时/长期区分展示 | 5.6 临时偏好边界 | 临时偏好明确标注临时/会话级/到期，不误展示为稳定 global 长期偏好 | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-05 | 跨用户不可见 | 5.7 跨用户隔离 | 仅渲染当前用户数据，其他用户偏好历史不可见、不可操作 | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-06 | 多 scope 共存展示 | 5.2 COEXIST | 同 key 不同 scope 同时展示、局部 scope 当前值优先、global 历史可回溯不被隐藏 | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L2-C-07 | 首版无历史入口 | 5.1 CREATE | 首版偏好 v1 不显示「历史版本」入口（无历史可回溯） | 真实交互日志 | ⬜ `RUNTIME_UNVERIFIED` |

---

## 二、L3 —— 干净镜像发布验证（发布候选）

| 编号 | 验证项 | 验证要点 | 证据要求 | 状态 |
|------|--------|----------|----------|------|
| L3-01 | 干净快照安装/重启/升级/卸载/回退 | 在干净麒麟 V11 x86_64 快照上完成安装、重启、升级、卸载、回退全链路（对应 95% 目标要求，02 §1.3） | 全链路命令 + 退出码 + 日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L3-02 | 版本持久化跨重启一致性 | 重启后 `current_version` 与版本链（v1→vN）状态不丢失、`previous_version_id` 链完整 | 重启前后落库对比 | ⬜ `RUNTIME_UNVERIFIED` |
| L3-03 | KYSEC 最小授权验证（若涉及） | 仅对单个测试二进制设 verified，禁止全局关闭（03 §3.2/§8.1-8.2） | kysec 登记表 / ACL 日志 | ⬜ `RUNTIME_UNVERIFIED` |
| L3-04 | 回退后数据一致性 | 版本回退后偏好历史数据完整、无残留脏版本指针 | 回退后落库查询结果 | ⬜ `RUNTIME_UNVERIFIED` |

---

## 三、执行边界与禁止事项

1. **KYSEC 只对单个测试二进制设 verified**，禁止全局关闭；禁止 `apt upgrade/dist-upgrade/autoremove` 或单独升级 AI 栈组件（03 §3.2/§8.1-8.2）。
2. **WSL 是开发环境，麒麟 VirtualBox VM 才是 Runtime 证据来源**；Agent 沙箱结果不构成宿主证据（03 §1.4、04 §1）。
3. **证据来自当前 Commit 的真实宿主**：接口返回成功 ≠ 业务正确，须核对向量维度、落库变化、`current_version` 实际指向、删除残留等实际结果（01 §1.3）。
4. **不修改冻结契约**：本清单执行不得改动 IPC 协议、SQLite DDL、QML 组件名等冻结/候选契约；若实现中发现判据与真实宿主/存储能力不可调和，由对应轨道提出修订任务，不在本任务内降级判据（验收规范第三章）。

---

## 四、证据回写要求

完成验证后须同步回写：

1. **证据索引** `evidence/index.yaml`：新增 L2/L3 条目，绑定 `tested_commit`、`evidence_commit`、checksum 与证据路径。
2. **能力矩阵**：若能力状态由 `UNTESTED`/`RUNTIME_UNVERIFIED` 变更为 `HOST_VERIFIED`，回写对应能力边界文档（01 §11、§13.2）。
3. **验收规范状态**：`day7-e-ui-version-acceptance-v1.md` 中各案例的 `RUNTIME_UNVERIFIED` 标记逐条更新为已验证状态。

---

## 五、变更记录

| 版本 | 日期 | 作者 | 变更说明 | 状态 |
|------|------|------|----------|------|
| v1 | 2026-08-24 | E 轨道 | 初稿：将 `day7-e-ui-version-acceptance-v1.md` 第六、七章 C/D 轨证据清单可执行化为 L2/L3 分层编号清单；全部条目 `RUNTIME_UNVERIFIED` | `RUNTIME_UNVERIFIED` |
| v2 | 2026-08-26 | E 轨道 | 将 §〇.2「L1 本地 100 passed」改为不易漂移表述（退出码 0 + passed 数量以实际执行证据为准），避免 passed 数量漂移误导；同步 PR #58 审查收敛补记状态 | `RUNTIME_UNVERIFIED` |
| v3 | 2026-08-26 | E 轨道 | 登记 TD-019/TD-020（跨用户 Rollback 拒绝载荷回显他人 key/scope + rollback 后 UPDATE 版本号冲突，均 Medium/In Progress），同步 HEAD `85f7754` 独立复测 109 passed 与跨阶段 305 passed 的 L1 时点（非 Runtime 证据）；全部 L2/L3 条目保持 `RUNTIME_UNVERIFIED` | `RUNTIME_UNVERIFIED` |
