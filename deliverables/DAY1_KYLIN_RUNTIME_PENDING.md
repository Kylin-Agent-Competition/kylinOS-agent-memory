# Day1 麒麟 VM 运行时待执行任务清单

> **创建日期**: 2026-08-05
> **上下文**: PR #21 Review Action Items — Day1 代码层面修复已基本完成，所有麒麟 VM 运行时任务待执行
> **上游文档**: `deliverables/PR21_REVIEW_ACTION_ITEMS.md`
> **PR 链接**: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/21

---

## 状态总览

| 维度 | 代码/文档层面 | 麒麟 VM 运行时 |
|------|:----------:|:------------:|
| Day1-1 环境基线 | — | 🔴 全部待做 |
| Day1-2 证据索引 | ✅ ECHO-005 状态已修正 | 🔴 真实证据采集 |
| Day1-3 回退锚点 | ✅ 诚实声明已到位 | 🔴 原始状态采集 + 验证 |
| Day1-4 部署可执行 | ✅ 脚本修复完成 | 🔴 端到端验证 |

---

## 任务清单

### 阶段一：准备 — 冻结 VM 快照

| # | 任务 | 详细要求 | 产出 |
|---|------|---------|------|
| P1 | 创建 VM 干净快照 | 在麒麟 VM 上创建快照，命名为 `gate0_day1_baseline_YYYYMMDD`，记录快照名称和创建时间 | 快照名称 + 时间戳 |
| P2 | 确认测试用户 | 确认用于测试的麒麟系统用户（非 root），记录用户名和 UID | 用户名、UID |
| P3 | 确认测试目录 | 确认干净的测试工作目录（建议 `/home/<user>/uds-echo-test/`），记录路径 | 测试目录路径 |

---

### 阶段二：采集 — Day1-1 环境基线

> **产出文件**: `evidence/gate0_echo/final/environment.log`

| # | 采集项 | 采集命令 | 说明 |
|---|--------|---------|------|
| E1 | 仓库 tested_commit | `cd <repo> && git rev-parse HEAD` | 当前 repo HEAD commit hash |
| E2 | PR Head | `git log -1 --format='%H %s'` | PR 分支最新 commit |
| E3 | 麒麟系统版本 | `cat /etc/kylin-release` 或 `lsb_release -a` | 完整版本号 |
| E4 | 麒麟 VM 镜像或快照编号 | 从虚拟机管理获取 | 镜像文件名或快照 ID |
| E5 | 虚拟机快照名称与创建时间 | 从虚拟机管理获取 | 快照名称 + 时间戳 |
| E6 | Python 版本 | `python3 --version` | 完整版本号 |
| E7 | g++ 版本 | `g++ --version` | 完整版本号 |
| E8 | CMake 版本 | `cmake --version` | 完整版本号 |
| E9 | systemd 版本 | `systemd --version` | 完整版本号 |
| E10 | Kaiming/麒灵宿主版本 | `rpm -qa \| grep -i kaiming` 或 `dpkg -l \| grep -i kaiming` | 宿主包名+版本 |
| E11 | KYSEC 当前状态 | `cat /sys/kernel/security/kysec/status` 或等效命令 | 内核安全模块状态 |
| E12 | 测试用户 | `whoami && id` | 用户名、UID、GID |
| E13 | 测试目录 | `pwd && ls -la` | 工作目录路径和权限 |
| E14 | 原始 Socket 状态 | `ls -la /run/kylin-memory-echo/ 2>/dev/null; ls -la /tmp/kylin-memory-echo/ 2>/dev/null` | 是否存在残留 socket |
| E15 | 原始 unit 文件 | `systemctl list-units --type=service \| grep -i echo` | 是否有残留 service |
| E16 | 原始进程状态 | `ps aux \| grep -i echo \| grep -v grep` | 是否有残留进程 |

**要求**: 每条命令记录必须包含：命令本身、完整输出、退出码（`echo $?`）、ISO 8601 时间戳。

---

### 阶段三：采集 — Day1-3 原始状态冻结

> **产出文件**: `evidence/gate0_echo/final/baseline.json`

| # | 采集项 | 采集方法 | 说明 |
|---|--------|---------|------|
| B1 | 原始 package/version | `rpm -qa \| grep -i kaiming` 或 `dpkg -l` | 相关包清单 |
| B2 | 原始文件路径 + SHA-256 | `find /usr/local/bin /opt /etc/systemd/system -name "*echo*" -o -name "*kaiming*" 2>/dev/null \| xargs sha256sum` | 扫描 Kaiming/Echo 相关文件 |
| B3 | 原始 unit 文件 | `systemctl list-unit-files \| grep -i -E "echo\|kaiming"` | 列出相关 unit |
| B4 | 原始 service 状态 | `systemctl is-active <service>` 逐个检查 | active/inactive 状态 |
| B5 | 原始 owner/group/mode | 对 B2 中发现的每个文件执行 `stat -c '%U %G %a %n'` | 权限记录 |
| B6 | 原始 ACL | 对 B2 中发现的每个文件执行 `getfacl` | ACL 记录 |
| B7 | 原始 Socket 路径 | `ls -la /run/kylin-memory-echo/ /tmp/kylin-memory-echo/ 2>&1` | socket 目录是否存在 |
| B8 | 原始 Kaiming/Hook 文件 | `find / -name "*.so" -path "*kaiming*" 2>/dev/null \| head -20` | Hook 共享库文件 |
| B9 | VM 快照 | 记录阶段一创建的基线快照名称 | 用于后续回退 |

**baseline.json 格式**:

```json
{
  "captured_at": "<ISO 8601 timestamp>",
  "captured_by": "<username>",
  "vm_snapshot": "<快照名称>",
  "system": {
    "kylin_version": "...",
    "kernel_version": "...",
    "python_version": "...",
    "gcc_version": "...",
    "cmake_version": "...",
    "systemd_version": "..."
  },
  "packages": [
    {"name": "...", "version": "..."}
  ],
  "files": [
    {
      "path": "/path/to/file",
      "sha256": "...",
      "owner": "...",
      "group": "...",
      "mode": "...",
      "acl": "..."
    }
  ],
  "units": [
    {"name": "...", "status": "active|inactive|not-found"}
  ],
  "sockets": {
    "/run/kylin-memory-echo/echo.sock": "absent",
    "/tmp/kylin-memory-echo/echo.sock": "absent"
  },
  "kysec_status": "...",
  "kaiming_host_version": "..."
}
```

---

### 阶段四：验证 — Day1-4 端到端部署

> **产出文件**: `evidence/gate0_echo/final/build.log`, `evidence/gate0_echo/final/deploy.log`

| # | 任务 | 命令 | 预期结果 |
|---|------|------|---------|
| D1 | 干净部署 | 从 VM 基线快照启动后执行 `deploy_echo.sh` | 上传全部文件成功 |
| D2 | CMOS 构建 | `cmake -S . -B build && cmake --build build` | `echo_client` + `kaiming_memory_client` 均编译成功 |
| D3 | 手动开发模式启动 | `python3 memory_echo_server.py --dev` | 服务端绑定 `/tmp/kylin-memory-echo/echo.sock` |
| D4 | echo_client 测试 | `./build/echo_client --socket /tmp/kylin-memory-echo/echo.sock` | 全部 Echo 测试 PASS |
| D5 | kaiming_memory_client 测试 | `./build/kaiming_memory_client --socket /tmp/kylin-memory-echo/echo.sock` | 全部测试 PASS（含 KAIMING-STORE 返回 UNSUPPORTED_METHOD） |
| D6 | systemd 模式测试 | 执行 `test_systemd_lifecycle.sh` | 安装→启动→测试→停止→卸载→验证 全流程 PASS |
| D7 | KYSEC ACL 测试 | 执行 `kysec_authorize.sh` | ACL 设置成功，权限正确 |
| D8 | Rollback 测试 | 执行 `test_rollback.sh` | 清理成功，状态验证通过 |
| D9 | 回退到基线快照 | 恢复阶段一创建的 VM 快照 | 系统回到 Day1 冻结状态 |

---

### 阶段五：Day1-2 真实证据回填

> **产出文件**: `evidence/gate0_echo/final/evidence.jsonl`, `evidence/index.yaml` (更新)

完成阶段二~四后，回填以下字段：

| # | 字段 | 来源 | 填写位置 |
|---|------|------|---------|
| F1 | `tested_commit` | 阶段二 E1 采集的 HEAD commit | `evidence/index.yaml` ECHO-005 |
| F2 | `evidence_commit` | 提交 evidence 文件的 commit | `evidence/index.yaml` ECHO-005 |
| F3 | `checksum_sha256` | `sha256sum evidence/gate0_echo/final/evidence.jsonl` | `evidence/index.yaml` ECHO-005 |
| F4 | `evidence.jsonl` | 汇总阶段二~四所有测试结果 | `evidence/gate0_echo/final/evidence.jsonl` |
| F5 | 冻结 D 任务卡 | 汇总 UDS Echo / Hook / 安装 / 启动 / KYSEC / 回退 / 证据收集 | `deliverables/` 目录 |

**evidence.jsonl 格式**（每行一条 JSON）：

```json
{"test_id": "ECHO-001", "tested_commit": "...", "command": "python3 memory_echo_server.py --dev", "exit_code": 0, "status": "PASS", "timestamp": "...", "environment": "麒麟 VM baseline", "source_log": "evidence/gate0_echo/final/server.log", "sha256": "..."}
```

---

### 阶段六：最终提交到 evidence/gate0_echo/final/ 的文件清单

完成所有阶段后，以下文件必须全部存在：

```
evidence/gate0_echo/final/
├── environment.log       # 阶段二产出 — 环境基线
├── baseline.json         # 阶段三产出 — 原始状态冻结
├── build.log             # 阶段四 D2 产出 — CMOS 构建日志
├── deploy.log            # 阶段四 D1 产出 — 部署日志
├── server.log            # 阶段四 D3 产出 — 服务端日志
├── client.log            # 阶段四 D4-D5 产出 — 客户端测试日志
├── systemd_lifecycle.log # 阶段四 D6 产出 — systemd 生命周期日志
├── kysec_acl.log         # 阶段四 D7 产出 — KYSEC/ACL 日志
├── rollback.log          # 阶段四 D8 产出 — 回退日志
└── evidence.jsonl        # 阶段五产出 — 汇总证据
```

---

## 执行依赖关系

```
阶段一 (VM 快照)
  ↓
阶段二 (环境基线) ──→ 阶段三 (原始状态冻结)
  ↓                         ↓
阶段四 (端到端部署) ────────┘
  ↓
阶段五 (证据回填)
  ↓
阶段六 (文件清单验证)
```

阶段二和阶段三可以并行执行（都在基线快照状态下采集），阶段四依赖阶段一快照（用于最终回退验证），阶段五依赖阶段二~四全部完成。

---

## 关联文档

- `deliverables/PR21_REVIEW_ACTION_ITEMS.md` — 上游 Review Action Items
- `deliverables/DAY1-1_麒麟VM信息填写表.md` — VM 信息填写模板
- `deliverables/DAY1-1_ENVIRONMENT_BASELINE_TASK_BREAKDOWN.md` — 环境基线任务分解
- `evidence/index.yaml` — 证据索引（ECHO-005 已改为 UNVERIFIED）
- `scripts/check_kylin_environment.sh` — 环境检查脚本

---

## 备注

- 所有采集命令必须保留原始输出，不得截断或修改
- 每个阶段执行前确认 VM 处于正确的快照状态
- 若某步骤失败，记录完整错误信息和退出码，不要跳过
- 任何无法完成的步骤必须如实记录原因