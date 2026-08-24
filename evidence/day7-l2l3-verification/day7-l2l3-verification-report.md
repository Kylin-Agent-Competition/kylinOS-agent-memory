# Day7E L2/L3 麒麟 VM 独立验证报告

- **验证对象**：`docs/day7/day7-e-l2-l3-verification-checklist.md`（L2-D-01~08、L2-C-01~07、L3-01~04）
- **验证性质**：独立验证（非 C/D 轨自我回填；只采集真实命令 + 退出码 + stdout/stderr，零冒充）
- **验证日期**：2026-08-24
- **执行者轨道**：E（记忆业务，独立核验）
- **被测仓库 commit（本地当前分支）**：`1ba5e6b`（分支 `feat/e-d7-preference-business-semantics`）
- **VM 部署仓库 commit（实测）**：`ed9949c`（分支 `feat/d4d-ipc-db-outbox`，`feat(D4D): IPC Gateway + 数据库层…`）

---

## 一、验证方法与证据

| 证据文件 | 内容 | SHA256 |
|----------|------|--------|
| `day7-l2l3-vm-verification.log` | 系统基线、memory 服务/进程、sqlite3 可用性 | `2e86ee5e4c7035fa72c8cebadc65acec347ce429554ff7062822bee5174b6cf7` |
| `day7-l2l3-vm-deployed.log` | 已部署 repo 树、git HEAD、QML/SQL/DB 文件勘察、`current_version`/`memory_entries`/`sqlite3` 引用 | `f571259d5277c574a3f2eb30e2135a6e1d049670661c485a934ac23cf24159c3` |
| `day7-l2l3-vm-db-schema.log` | D4d `db/schema.py`/`repositories.py`、migration 001、落盘 `kylin_memory.db` 实际 schema | `b82dd9369cd0e163ee032183646142ae2f9eaa553c52c76290c8df881b6129fb` |

验证脚本：`_verify.py`、`_verify2.py`、`_verify3.py`（paramiko 连接 `127.0.0.1:2222`，用户 `kylin-agent`，凭证取自环境变量 `KYLIN_VM_PASSWORD`，无硬编码）。

---

## 二、VM 真实运行态结论（实测事实）

### 2.1 系统与已部署服务

- OS：银河麒麟桌面 V11 2603 Release x86_64（`/etc/.kyinfo`：`dist_id=Kylin-Desktop-V11-2603-Release-20260228`）。
- 用户：`kylin-agent`（uid 1000，sudo 组）。
- **VM 上确实运行着一个 memory-service**：`/home/kylin-agent/d4d-venv/bin/python /home/kylin-agent/kylinOS-agent-memory/memory-service/app.py --socket /run/user/1000/kylin-memory/memory.sock`。
- **但该部署仓库停在 D4D 提交** `ed9949c`，分支 `feat/d4d-ipc-db-outbox`（IPC Gateway + SQLAlchemy/Alembic/UoW + Outbox 骨架），**并非 Day7E 分支，也不含 Day7E 代码**。

### 2.2 D 轨版本持久化 —— 未实现

| 核查项 | 实测结果 | 对照 L2-D 判据 |
|--------|----------|----------------|
| Day7E 策略代码是否存在 | VM `memory-service/service/` 仅 `candidate_governance.py`/`contracts.py`/`__init__.py`，**无 `preference_version_policy.py` / `preference_business_policy.py`** | 需 `current_version` 指针切换（L2-D-01/06）→ 缺 |
| `current_version` 指针列 | `db/schema.py` `memory_entries` 表**无 `current_version` 列**；落盘 `kylin_memory.db` `.schema` 中 `current_version` 命中为空 | L2-D-01/02/06/07 依赖该指针 → 缺 |
| `previous_version_id` 版本链 | schema 与 DB 均**无 `previous_version_id`** | L2-D-02（v1→v2→v3 链）→ 缺 |
| 乐观锁 `version` | 存在：`memory_entries.version INTEGER NOT NULL`（D4d 乐观锁，default 1） | L2-D-03 仅「乐观锁字段」在场，但**并发冲突检测/失败处理为 D 轨实现职责，未实现** |
| 偏好版本语义落库（CREATE/UPDATE/ROLLBACK/NO_OP/COEXIST） | D4d 层仅 `memory_entries` 通用表，**无偏好版本链持久化逻辑** | L2-D-01/02/04/06/07/08 → 缺 |
| 跨用户隔离落库 | D4d `memory_entries.user_id` 存在，但**无 Day7E 跨用户拒绝语义的版本层实现** | L2-D-05 → 未实现 |

> 结论：D 轨 Day7E 版本持久化（`current_version` 指针 + `previous_version_id` 链 + 五动作落库）**未实现**。VM 上存在的 D4d 数据库层是 Day4 的通用 `memory_entries`（乐观锁 `version`），不是 Day7E 偏好版本语义。

### 2.3 C 轨偏好 UI —— 未实现

| 核查项 | 实测结果 |
|--------|----------|
| QML 生产文件 | VM 全盘 `find -name '*.qml'` 无偏好/记忆相关生产文件；本地 `memory-client/` 仅 `README.md`（「仅建立目录和职责边界，尚无生产实现」） |
| 真实 UDS 连接链路的偏好 UI | 不存在；无 `PreferenceEditor.qml` / `MemoryQueryPanel.qml` / `memory_client.cpp` 等任何生产实现 |

> 结论：C 轨 QML 偏好 UI 全部未实现，L2-C-01~07 无任何可交互对象，无法进行「真实 UDS 连接链路」的真实交互验证。

### 2.4 L3 干净镜像发布验证 —— 无法执行

- L3-01/02/03/04 依赖 D/C 轨已实现并在干净快照上完成安装/升级/卸载/回退全链路。当前 D 轨版本持久化、C 轨 UI 均未实现，**无发布候选可验证**，L3 全部无执行对象。

---

## 三、逐条验证结论

> 状态口径：`RUNTIME_UNVERIFIED`（保持）＋ 原因。**本报告不产生任何 `HOST_VERIFIED`。**

### L2-D（D 轨版本持久化）

| 编号 | 结论 | 原因 |
|------|------|------|
| L2-D-01 | ⬜ RUNTIME_UNVERIFIED | `current_version` 指针未实现 |
| L2-D-02 | ⬜ RUNTIME_UNVERIFIED | `previous_version_id` 版本链未实现 |
| L2-D-03 | ⬜ RUNTIME_UNVERIFIED | 仅乐观锁 `version` 字段在场，并发冲突检测/失败处理未实现 |
| L2-D-04 | ⬜ RUNTIME_UNVERIFIED | 回滚不删中间版本逻辑未实现 |
| L2-D-05 | ⬜ RUNTIME_UNVERIFIED | 跨用户隔离的版本层拒绝语义未实现 |
| L2-D-06 | ⬜ RUNTIME_UNVERIFIED | CREATE 首版落库未实现 |
| L2-D-07 | ⬜ RUNTIME_UNVERIFIED | NO_OP 不写版本逻辑未实现 |
| L2-D-08 | ⬜ RUNTIME_UNVERIFIED | COEXIST 独立首版未实现 |

### L2-C（C 轨偏好 UI）

| 编号 | 结论 | 原因 |
|------|------|------|
| L2-C-01~07 | ⬜ RUNTIME_UNVERIFIED | QML 偏好 UI 未实现，无真实 UDS 交互对象 |

### L3（干净镜像发布验证）

| 编号 | 结论 | 原因 |
|------|------|------|
| L3-01~04 | ⬜ RUNTIME_UNVERIFIED | 无发布候选，D/C 轨未实现 |

---

## 四、与「禁止冒充」条款的合规声明

1. 未以 E 轨策略 L1 pytest 结果冒充 L2/L3 验收（本报告全部 L2/L3 保持 `RUNTIME_UNVERIFIED`）。
2. 未以 UI 截图 / 数据库 schema 截图 / 静态代码存在冒充真实交互验收。
3. 未以 Mock 冒充真实 UDS 交互。
4. 本报告只陈述 VM 实测事实（真实命令 + 退出码 + stdout），不宣称任何 C/D 轨功能已通过。

## 五、结论

按 `day7-e-l2-l3-verification-checklist.md` 在麒麟 VM 上执行独立验证后，**全部 L2/L3 条目保持 `RUNTIME_UNVERIFIED`**，根因是：

1. **C 轨 QML 偏好 UI 未实现**（`memory-client/` 仅 README，无任何 .qml / C++ 生产实现）。
2. **D 轨 Day7E 版本持久化未实现**（`current_version` 指针、`previous_version_id` 链、五动作落库均缺；VM 部署仓库停留在 D4D 提交 `ed9949c`，且不含 Day7E E 轨策略代码；落盘 `kylin_memory.db` 仅含 D4d 通用 `memory_entries` 乐观锁 `version`，无偏好版本链字段）。

后续需由 C/D 轨分别实现其职责范围内功能并在麒麟 VM 真实执行后，方可回填 `HOST_VERIFIED`。
