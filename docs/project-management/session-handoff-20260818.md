# 会话交接文档：A 轨技术债收口 + Day9 施工中（2026-08-18）

> 生成：2026-08-18 ｜ 状态：fix/td-a-pure（REWORK 修订版）已推送待复审；Day9 独立分支未推送；Day10 未开始
> 交接对象：下一会话的 AI agent 工具
> 本文件为**权威交接文档**——开工前必读，配合 [[day8-knowledge-extraction-status]] 记忆

---

## 一、项目一句话

麒麟 OS Agent 多源融合偏好与知识记忆系统（kylinOS-agent-memory）——A 轨（刘依枫）负责 Embedding SDK 接入 + Bridge + 抽取 Provider。当前主线：**技术债批量收口（fix/td-a-pure 待复审）+ Day9 待推送 + Day10 待开始**。

## 二、git 状态（开工前必核对）

### 关键分支

| 分支 | HEAD | 状态 | 说明 |
|---|---|---|---|
| `main` | 5bd2c3e | 已推送 | Day8 PR #38 已合并 + C 轨 D3 #37 |
| `fix/td-a-pure` | **d8307a5** | ✅ 已推送 | **当前活跃**：技术债收口 REWORK 修订版（9 commits vs main） |
| `feat/day9-embedding-throughput` | 469be56 | ⚠️ 未推送 | Day9 内容（Embedding 吞吐/缓存/积压）——与 TD 分支**相互独立** |
| `fix/td-a-005-03-05-dimension-loaded` | dc0f525 | 已并入 td-a-pure | 可删 |
| `fix/td-a-local-batch` | 5afe7e7 | 已并入 td-a-pure | 可删 |
| `feat/day8-knowledge-extraction` | 5587742 | 已合并 | Day8 历史分支，可删 |

### 工作区

- 当前分支 `fix/td-a-pure`，工作区仅 2 个未跟踪历史文档（`docs/project-management/session-handoff-20260809/13.md`，**非本次改动，勿误提交**）
- `tmp/` 目录的临时脚本（fix_*.py）已清理，无残留

## 三、fix/td-a-pure 分支内容（9 commits，含 REWORK 修订）

### 关闭的 11 项 TD（Resolved）+ 1 项 Wontfix

| TD | 内容 | 认证 |
|---|---|---|
| TD-A-005-02 | embed_batch 并行 | Resolved（VM 实测 4 线程×100 并发挂起 → SDK 单会话串行，顺序调用正确） |
| TD-A-005-03 | get_dimension 空串副作用 | Resolved（start 已写 _shared_dimension，正常路径无 IPC 副作用） |
| TD-A-005-04 | 真实模型名 | **Resolved（SOURCE_VERIFIED + ABI_VERIFIED + PARTIAL）**——R-1 降级 |
| TD-A-005-05 | model_info.loaded 精确化 | Resolved（仅 _lifecycle==READY 才 loaded） |
| TD-A-005-06 | Singleton 并发锁 | Resolved（_singleton_lock 类级锁） |
| TD-A-005-07 | 文档轮次标注收口 | Resolved |
| TD-A-005-08 | verify_day4 .prev 清理 | Resolved（备份改放 /tmp） |
| TD-A-005-09 | SDK 缺失降级 | Resolved（_SdkMissingProvider 兜底，VM 端到端） |
| TD-A-D6-LLM-TOOL-INPUT | LLM 输入绑定 ToolResult | Resolved（tool_context 参数） |
| TD-A-D7-LLM-HANG-DEGRADE | LLM 挂死恢复 | Resolved（_rebuild_executor） |
| TD-A-D8-CONTRACT-CATEGORY-SYNC | category 五→六值文档 | Resolved |
| TD-A-005-01 | 主动超时中断 | **Wontfix**（SDK 无 cancel/abort API，grep /usr/include/kylin* 确认） |

### 维持 Open（3 项，勿动）

- **TD-A-D6-EXEC-RACE**：并发安全敏感、非阻断，现有 6 项 lifecycle 测试保障主路径
- **TD-A-D6-TOOL-PARTIAL**：partial result 自由文本无格式 + side_effect/rollback 卡 ToolResult 契约字段
- **TD-A-D7-CACHE-USER-DIMENSION**：事件契约无可信 user_id（Day3 冻结）

### REWORK 修订要点（D 主审 2026-08-18）

- **R-1（必改，已完成）**：TD-A-005-04 认证降级 PARTIAL——L2 证据非判别性（model name 输出与硬编码回退名相同），未证明动态查询路径在宿主生效；ABI 头保持 UNTESTED（embedding_abi_compat.h:34-35/68）；基线文档标注 `text_embedding_get_model_list` 原文档标禁调
- **#3-#8（已完成）**：Day3 scope 五值同步、C++ mutex/泄漏说明、except 精确化（ERR_CONFIG_CONFLICT 上抛）、health degraded 反映 _sdk_missing、真并发测试、PR 描述修正
- **#2 登记**：TD-A-005-01/02 的 VM 探测无持久化日志（宿主终端输出），证据缺口

## 四、Day9 分支内容（feat/day9-embedding-throughput，未推送）

Day9（台账 R47）：Embedding 吞吐/查询缓存/积压指标——与 TD 分支**完全独立**，不要混淆。

- `embedding/embedding_cache.py`：EmbeddingQueryCache（LRU + 维度+原文哈希键 + 深拷贝 + 空向量不缓存）+ EmbeddingCoalescer（同文本并发合并）
- `embedding/embedding_metrics.py`：EmbeddingBacklogTracker（backlog/oldest_pending_age，backlog_warn=32/oldest_warn=0.2s）
- `embedding/embedding_service.py`：embed 路径接入缓存/合并/积压 + health 扩展
- `scripts/benchmark_embedding.py`：吞吐测量（P50/P95/P99 + req/s + JSON）
- `scripts/verify_day9_vm.sh`：VM 一键验证
- `tests/test_embedding_d9.py`（18 项）+ L2 证据 `evidence/l2-kylin-vm/day9_verify_latest.log`
- **L2 真实吞吐基线（宿主已跑）**：串行 13.75 req/s / P99 148.69ms（<180ms 预算达标）；并发 4/8 时 P99 863/1145ms（**Bridge 线程池 max_workers=2 是瓶颈**）

> ⚠️ Day9 分支基于旧 main（d37fb95），若后续推送需先 rebase 到最新 main（5bd2c3e）。宿主可能已单独发 Day9 PR（未确认）。

## 五、麒麟 VM 环境（宿主操作记录）

- **访问**：SSH `ssh -p 2222 Lyf@127.0.0.1`（曾 guestcontrol 不通、SSH 2222 后通；当前状态需重新探测）
- **共享目录**：`/mnt/shared` = WSL 仓库实时同步（vboxsf）——WSL 侧改文件 VM 立即可见，无需 git fetch
- **Python**：VM 只有 `/usr/bin/python3.12`（无 `python` 命令、无 pybind11）
- **pybind11**：已装（`apt python3-pybind11` 2.11.1）；构建：`cmake -B build -Dpybind11_DIR=$(python3 -m pybind11 --cmakedir) && cmake --build build -j4`
- **venv**：`/tmp/day8-venv` 易失（已多次被清）——本地测试用 **仓库 `.venv`**（`/home/fff/projects/kylinOS-agent-memory/.venv/bin/python`）
- **SDK**：`libkylin-coreai-embedding 1.2.0.0-0k0.4`；`.so` 路径 `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1`
- **SDK 恢复**：`sudo apt-get install --reinstall libkylin-coreai-embedding`

### 宿主待办（两项证据补齐，复审前提）

1. **TD-A-005-04 判别性证据**：打印 `get_default_model_name()` 原始返回值（区分动态查询 vs 回退）——补齐后可升级 HOST_VERIFIED
2. **TD-A-005-01/02 探测日志落盘**：grep 无 cancel API 输出 + 并发挂起输出

## 六、测试与证据

- **L1**：`272 passed + 49 skipped`（.venv 跑；skip 49 = 47 基础 + 2 项 real 用例 KYLIN_L2 门控，VM 上真实执行）
- **L2 证据**（evidence/l2-kylin-vm/）：
  - `td_a_005_04_model_name.log`（非判别性，R-1 已注明）
  - `td_a_005_09_sdk_missing.log`（so 缺失降级 + apt 恢复）
  - `day8_verify_latest.log` / `day9_verify_latest.log`（Day8/9）
- **证据门禁**：tested_commit 绑定被测代码；L2 日志含 Step1 原始输出；checksum 三处一致（index.yaml = 工作区 = git 提交版）

## 七、环境坑（必读，防踩）

1. **shell 陷阱**：当前会话 shell 是 Windows PowerShell（`&&`/`||` 不解析、无 grep/sed）——命令用 `wsl -d Ubuntu -- bash -lc "..."` 执行；**内层 heredoc/引号会与外层 wsl -c 引号冲突**——写临时 py 脚本到 `tmp/` 再执行最稳
2. **heredoc 反引号**：bash heredoc 里反引号会被执行——改用 write_file 写脚本文件
3. **awk `$` 展开**：PowerShell/bash 双引号内 `$` 展开——用单引号或写文件
4. **venv 易失**：`/tmp/day8-venv` 常被清——本地用仓库 `.venv`
5. **并发测试坑**：全量跑时 `providers.embedding_provider.EmbeddingProvider` 类可能被其他测试 monkeypatch 成 function（test_td_a_005_09 的字符串 patch）——**并发测试必须用独立 lock 解耦，不依赖类属性**
6. **git push**：wsl 内 push 会超时（凭证弹窗）——用 Windows git：`& "D:\Git\cmd\git.exe" -C "\\wsl.localhost\Ubuntu\home\fff\projects\kylinOS-agent-memory" push ...`（stderr 显示为错误是正常现象，看进度行确认成功）
7. **evidence tested_commit 回填**：commit 后 amend 会改 hash——证据标注写"见 index.yaml"而非硬编码 hash

## 八、下一步建议（优先级）

1. **宿主补齐两项证据**（005-04 判别性 + 005-01/02 日志）→ 005-04 升级 HOST_VERIFIED → fix/td-a-pure 复审
2. **确认 Day9 是否已单独发 PR**（分支 469be56 未推送，若未发需 rebase main 后推送）
3. **Day10**（台账 R50？）：缓存失效/临时文件清理/异常恢复——需先看 75 项台账确认 Day10 A 轨任务
4. 工作区 2 个历史未跟踪文档（session-handoff-20260809/13.md）——可归档到 docs/project-management/ 或删除

## 九、关键文件索引

| 文件 | 用途 |
|---|---|
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 技术债台账（权威状态） |
| `docs/day8/01_task_card.md` + `02_pr_description.md` | Day8 任务卡/PR 描述 |
| `docs/fix-td-a-pure/02_pr_description.md` | **fix/td-a-pure 的 PR 描述（REWORK 修订版）** |
| `docs/baseline/01_sdk_model_abi_baseline.md` | SDK/模型/ABI 基线（含禁调标注） |
| `docs/day3/06_provider_contract_v1.md` | Provider 契约（category 六值 + scope 五值已同步） |
| `third_party/kylin-coreai-embedding/reference/embedding_api.h` | SDK API 头文件参考 |
| `evidence/index.yaml` | 证据索引 |
| `scripts/verify_day4_vm.sh` / `verify_day9_vm.sh` | VM 验证脚本 |
| `scripts/benchmark_embedding.py` | 吞吐测量脚本 |
