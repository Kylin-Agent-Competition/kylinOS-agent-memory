# 会话交接文档：A 轨 D10 PR 待审查 + D11 施工起点（2026-08-26）

> 生成：2026-08-26 ｜ 状态：**feat/day10-forgetting-deletion 已 rebase main（2 commits），待 push + 创建 PR**
> 交接对象：下一会话的 AI agent 工具
> 本文件为权威交接文档——开工前必读

## 一、项目一句话

麒麟 OS Agent 多源融合偏好与知识记忆系统（kylinOS-agent-memory）——A 轨负责 Embedding SDK 接入 + Bridge + 抽取 Provider。当前主线：**D10 PR 待推送审查，D11（待定）待开始**。

## 二、Git 操作规范

详见 `docs/project-management/git-conventions.md`，开工前必读。

关键约束：
- 分支命名：`<type>/<描述>`（如 `feat/day10-forgetting-deletion`）
- 提交信息：`<type>(<scope>)：<描述>`（如 `feat(embedding-cache)：实现按内容指纹的缓存失效接口`）
- **原子化提交**：小 bug 修完就提交，不要攒大 commit
- **rebase 而非 merge**：PR 前先 rebase main，解决冲突再推送
- **主分支不能直推**，必须通过 PR

## 三、git 状态

### 关键分支

| 分支 | HEAD | 状态 | 说明 |
|------|------|------|------|
| `main` | d12df5a | 已推送 | 含 D9 #48 + D4D #52 等 |
| `feat/day10-forgetting-deletion` | **05ce208** | 待推送 | 2 commits vs main，待 push + 创建 PR |

### 工作区

工作区有未跟踪文件（docx/xlsx 文档文件，非项目代码，勿提交）。

## 四、D10 PR 状态

### 分支 commits（vs main）

| Commit | 说明 |
|--------|------|
| `3777667` | feat(day10)：精准遗忘与删除一致性——缓存失效协调器 + 删除事件集成（代码 + 测试） |
| `05ce208` | docs(day10)：PR 描述 + L2 证据落盘 |

### 待办

1. **rebase main**（已执行，无冲突）
2. **push**：`git push --force-with-lease origin feat/day10-forgetting-deletion`（需代理）
3. **创建 PR**：`gh pr create --base main --head feat/day10-forgetting-deletion --title "..." --body "$(cat docs/day10/02_pr_description.md)"`

### 交付物清单

- 缓存失效：`EmbeddingQueryCache.invalidate_by_content`（按内容哈希）
- 抽取缓存失效：`PreferenceExtractionCache.invalidate_by_event` / `invalidate_by_content`
- 协调器：`CacheInvalidator` + `DeletionEvent`（幂等/按用户/全量失效）
- Service 对接：`EmbeddingService.handle_deletion_event` / `set_cache_invalidator`
- Bridge 安全审计：cpp-bridge 无临时文件/无正文缓存/无日志泄露
- 测试：`test_embedding_d10.py`（15 项）
- 脚本：`verify_day10_vm.sh`
- 证据：`evidence/l2-kylin-vm/day10_verify_latest.log`（82 passed）
- 任务卡：`docs/day10/01_task_card.md`
- PR 描述：`docs/day10/02_pr_description.md`
- 技术债：`TD-A-D10-CACHE-INVALIDATION`

## 五、D11 任务（待定）

D11 任务内容尚未确定。建议从以下方向选择：
1. 缓存失效接通 Outbox 事件总线（关闭 TD-A-D10-CACHE-INVALIDATION）
2. 桥接抽取缓存与 Embedding 缓存的统一失效入口
3. 其他轨道依赖的 A 轨接口

## 六、麒麟 VM 环境

- SSH `ssh -p 2222 Lyf@127.0.0.1`
- 共享目录 `/mnt/shared` = WSL 仓库实时同步（vboxsf）
- **⚠️ vboxsf 时钟错误 → 增量编译不可靠**：C++ 改动后必须在 VM 本地 `/tmp` 构建
- Python：VM 只有 `/usr/bin/python3.12`；venv 用 `/tmp/day10-venv`
- SDK：`libkylin-coreai-embedding 1.2.0.0-0k0.4`，路径 `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1`

## 七、环境坑

1. **shell 陷阱**：当前会话是 PowerShell，命令用 `wsl -d Ubuntu -- bash -lc "..."` 执行；内层引号/括号会与 wsl -c 冲突——写临时脚本到 `.scratch/` 再执行最稳
2. **git push 超时**：WSL 内 push 需代理，`http_proxy=http://172.21.64.1:7890 https_proxy=http://172.21.64.1:7890 git push ...`
3. **venv 易失**：本地用仓库 `.venv`（`/home/fff/projects/kylinOS-agent-memory/.venv/bin/python`）
4. **pytest**：需 `PYTHONPATH=memory-service` 前缀

## 八、关键文件索引

### 每次会话开工前必读

| 文件 | 用途 |
|------|------|
| `docs/project-management/git-conventions.md` | Git 操作规范（**所有会话开工前必读**） |
| `docs/project-management/session-handoff-20260826.md` | 本交接文档（**所有会话开工前必读**） |
| `02_麒麟OS_Agent记忆系统_总体架构_团队分工与标准开发SOP_v1.0_20260726.docx` | 总体架构与团队分工、SOP（**每次会话连读**） |
| `04_麒麟OS_Agent记忆系统_Agent_LLM与CodeAgent使用指南_v1.0_20260726.docx` | Agent/LLM 使用指南（**每次会话连读**） |
| `麒麟OS_Agent记忆系统_15天75项个人施工台账_修正版.xlsx` | 75 项施工台账（**每次会话连读**） |

### D10 交付物

| 文件 | 用途 |
|------|------|
| `docs/day10/01_task_card.md` | D10 任务卡 |
| `docs/day10/02_pr_description.md` | D10 PR 描述（模板格式） |
| `memory-service/embedding/cache_invalidator.py` | D10 CacheInvalidator + DeletionEvent |
| `memory-service/embedding/embedding_cache.py` | D10 缓存失效接口 |
| `memory-service/embedding/embedding_service.py` | D10 删除事件对接 |
| `memory-service/providers/extraction_provider.py` | D10 抽取缓存失效 |
| `memory-service/tests/test_embedding_d10.py` | D10 测试（15 项） |
| `scripts/verify_day10_vm.sh` | VM 验证脚本 |
| `evidence/l2-kylin-vm/day10_verify_latest.log` | D10 L2 证据（82 passed） |