# 会话交接文档：A 轨 D10 已合并 + D11 施工起点（2026-08-29）

> 生成：2026-08-29 ｜ 状态：**D10 (PR #61) 已合并至 main@4926345**
> 交接对象：下一会话的 AI agent 工具
> 本文件为权威交接文档——开工前必读

## 一、项目一句话

麒麟 OS Agent 多源融合偏好与知识记忆系统（kylinOS-agent-memory）——A 轨负责 Embedding SDK 接入 + Bridge + 抽取 Provider。当前主线：**D10 已合并，D11（同一虚拟机全功能联调）待开始**。

## 二、Git 操作规范

详见 `docs/project-management/git-conventions.md`，开工前必读。

关键约束：
- 分支命名：`<type>/<描述>`（如 `feat/day10-forgetting-deletion`）
- 提交信息：`<type>(<scope>)：<描述>`（如 `fix(embedding-cache)：generation 代次机制`）
- **原子化提交**：小 bug 修完就提交，不要攒大 commit
- **rebase 而非 merge**：PR 前先 rebase main，解决冲突再推送
- **主分支不能直推**，必须通过 PR
- **推送用 PowerShell**：`powershell.exe -Command "cd \\\\wsl.localhost\\Ubuntu\\home\\fff\\projects\\kylinOS-agent-memory; git push ..."`

## 三、git 状态

### 关键分支

| 分支 | HEAD | 状态 | 说明 |
|------|------|------|------|
| `main` | 4926345 | 已推送 | 含 D10 #61 + D4D #65 + D6B #63 + D7E #58 等 |
| `feat/day10-forgetting-deletion` | 2506364 | 已合并可删 | D10 开发分支，合并后已无用 |

### 工作区

工作区有未跟踪文件（docx/xlsx 文档文件，非项目代码，勿提交）。

## 四、D10 交付物清单（已合并）

| 交付物 | 文件 |
|--------|------|
| Embedding 缓存失效 | `embedding/embedding_cache.py`（`invalidate_by_content` + generation 代次） |
| 抽取缓存失效 | `providers/extraction_provider.py`（`invalidate_by_event` / `invalidate_by_content` + event_tombstones） |
| 缓存失效协调器 | `embedding/cache_invalidator.py`（CacheInvalidator + DeletionEvent + ForgetMode/TargetType 枚举） |
| Service 对接 | `embedding/embedding_service.py`（`handle_deletion_event` / `set_extraction_provider`） |
| 测试 | `tests/test_embedding_d10.py`（20 项） |
| VM 验证脚本 | `scripts/verify_day10_vm.sh` |
| L2 证据 | `evidence/l2-kylin-vm/day10_verify_latest.log`（87 passed） |
| 技术债 | `TD-A-D10-CACHE-INVALIDATION`（Outbox 接线待完成） |

## 五、D11 任务（台账）

### 台账内容

| 字段 | 内容 |
|------|------|
| 任务标题 | 同一虚拟机全功能联调 |
| 责任轨道 | 全部 5 轨（A 刘依枫 / B 高翌哲 / C 刘承恩 / D 周子腾 / E 谢嘉然） |
| A 轨具体任务 | ① 处理真实 SDK/ABI/模型状态/性能问题；② 提供 Embedding 健康状态与错误详情；③ 参与跨模块故障定位 |
| 完成定义 | SDK/Bridge 在主演示链中稳定运行并有状态证据 |

### A 轨 D11 任务分析

A 轨 D11 任务**不需要等其他轨道**，可以独立完成：
- 任务①：处理 SDK 问题 — 纯 A 轨
- 任务②：Embedding 健康状态 — `health()` 接口已有，增强即可
- 任务③：跨模块故障定位 — 需要等别人到位，但占比最小

### 建议方向

D11 是集成联调阶段，A 轨的核心工作是保障 Embedding/Bridge 在整个演示链中稳定运行。建议：
1. 先跑一遍全量测试确认 D10 合并后无回归
2. 检查 D 轨的 Outbox/Forget 事务是否已就绪（`memory-service/db/` 和 `memory-service/outbox/`）
3. 如有余力，可以开始将 CacheInvalidator 接通 Outbox 事件总线（关闭 TD-A-D10-CACHE-INVALIDATION）

## 六、麒麟 VM 环境

- SSH `ssh -p 2222 Lyf@127.0.0.1`
- 共享目录 `/mnt/shared` = WSL 仓库实时同步（vboxsf）
- **⚠️ vboxsf 时钟错误 → 增量编译不可靠**：C++ 改动后必须在 VM 本地 `/tmp` 构建
- Python：VM 只有 `/usr/bin/python3.12`；venv 用 `/tmp/day10-venv`
- SDK：`libkylin-coreai-embedding 1.2.0.0-0k0.4`，路径 `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1`

## 七、环境坑

1. **shell 陷阱**：当前会话是 PowerShell，命令用 `wsl -d Ubuntu -- bash -lc "..."` 执行
2. **git push 用 PowerShell**：`powershell.exe -Command "cd \\\\wsl.localhost\\Ubuntu\\home\\fff\\projects\\kylinOS-agent-memory; git push ..."`
3. **venv 易失**：本地用仓库 `.venv`（`/home/fff/projects/kylinOS-agent-memory/.venv/bin/python`）
4. **pytest**：需 `PYTHONPATH=memory-service` 前缀

## 八、每次会话开工前必读文件

| 文件 | 用途 |
|------|------|
| `docs/project-management/git-conventions.md` | Git 操作规范 |
| `docs/project-management/session-handoff-20260829.md` | **本文件** |
| `02_麒麟OS_Agent记忆系统_总体架构_团队分工与标准开发SOP_v1.0_20260726.docx` | 总体架构与团队分工 |
| `04_麒麟OS_Agent记忆系统_Agent_LLM与CodeAgent使用指南_v1.0_20260726.docx` | Agent/LLM 使用指南 |
| `麒麟OS_Agent记忆系统_15天75项个人施工台账_修正版.xlsx` | 75 项施工台账 |

## 九、关键文件索引

| 文件 | 用途 |
|------|------|
| `docs/project-management/git-conventions.md` | Git 操作规范（所有会话必读） |
| `docs/project-management/session-handoff-20260829.md` | 本交接文档 |
| `memory-service/embedding/cache_invalidator.py` | D10 CacheInvalidator + DeletionEvent |
| `memory-service/embedding/embedding_cache.py` | D10 缓存失效（generation 代次） |
| `memory-service/embedding/embedding_service.py` | D10 删除事件对接 |
| `memory-service/providers/extraction_provider.py` | D10 抽取缓存失效（event_tombstones） |
| `memory-service/tests/test_embedding_d10.py` | D10 测试（20 项） |
| `scripts/verify_day10_vm.sh` | VM 验证脚本 |
| `evidence/l2-kylin-vm/day10_verify_latest.log` | D10 L2 证据（87 passed） |