# 会话交接文档：A 轨技术债全闭环 + Day9 待推送（2026-08-18 更新版）

> 生成：2026-08-18 ｜ 更新：2026-08-18（TD-A-005-04 正式解决 + 全量重编教训）
> 状态：**fix/td-a-pure 全闭环（12 Resolved + 1 Wontfix + 3 Open）已推送待复审**；Day9 独立分支未推送；Day10 未开始
> 交接对象：下一会话的 AI agent 工具
> 本文件为**权威交接文档**——开工前必读，配合记忆 `day8-knowledge-extraction-status`

---

## 一、项目一句话

麒麟 OS Agent 多源融合偏好与知识记忆系统（kylinOS-agent-memory）——A 轨（刘依枫）负责 Embedding SDK 接入 + Bridge + 抽取 Provider。当前主线：**技术债收口全闭环（fix/td-a-pure 待复审）+ Day9 待推送 + Day10 待开始**。

## 二、git 状态（开工前必核对）

### 关键分支

| 分支 | HEAD | 状态 | 说明 |
|---|---|---|---|
| `main` | 5bd2c3e | 已推送 | Day8 PR #38 已合并 + C 轨 D3 #37 |
| `fix/td-a-pure` | **98baa0f** | ✅ 已推送 | **当前活跃**：技术债收口全闭环（12 Resolved/1 Wontfix/3 Open） |
| `feat/day9-embedding-throughput` | 469be56 | ⚠️ 未推送 | Day9 内容（Embedding 吞吐/缓存/积压）——与 TD 分支**相互独立**，需 rebase main 后推送 |
| `fix/td-a-005-03-05-dimension-loaded` | dc0f525 | 已并入 td-a-pure | 可删 |
| `fix/td-a-local-batch` | 5afe7e7 | 已并入 td-a-pure | 可删 |
| `feat/day8-knowledge-extraction` | 5587742 | 已合并 | Day8 历史分支，可删 |

### 工作区

- 当前分支 `fix/td-a-pure`，工作区仅 2 个未跟踪历史文档（`docs/project-management/session-handoff-20260809/13.md`，**非本次改动，勿误提交**）
- `tmp/` 目录临时脚本已清理

## 三、fix/td-a-pure 分支内容（全闭环，12 Resolved + 1 Wontfix + 3 Open）

### Resolved（12 项）

| TD | 内容 | 认证 |
|---|---|---|
| TD-A-005-02 | embed_batch 并行 | Resolved（VM 实测 4 线程×100 并发 **28.8s 完成零错误** ≈13.9 req/s → SDK 内部串行排队**不挂起**；此前"挂起"系 400 次耗时超 30s timeout 被杀误判；顺序调用保持） |
| TD-A-005-03 | get_dimension 空串副作用 | Resolved（start 已写 _shared_dimension） |
| **TD-A-005-04** | 真实模型名 | **Resolved（SOURCE+ABI+HOST_VERIFIED）**——2026-08-18 判别性证据：void* 显式调用 + 模型名缓存（详见"七、环境坑"） |
| TD-A-005-05 | model_info.loaded 精确化 | Resolved |
| TD-A-005-06 | Singleton 并发锁 | Resolved（_singleton_lock + 真并发测试） |
| TD-A-005-07 | 文档轮次标注收口 | Resolved |
| TD-A-005-08 | verify_day4 .prev 清理 | Resolved（备份改放 /tmp） |
| TD-A-005-09 | SDK 缺失降级 | Resolved（_SdkMissingProvider，VM 端到端） |
| TD-A-D6-LLM-TOOL-INPUT | LLM 输入绑定 ToolResult | Resolved（tool_context） |
| TD-A-D7-LLM-HANG-DEGRADE | LLM 挂死恢复 | Resolved（_rebuild_executor） |
| TD-A-D8-CONTRACT-CATEGORY-SYNC | category 五→六值文档 | Resolved |
| TD-02（Reviewer 登记） | Day8 契约同步 | Resolved（Day9 分支台账） |

### Wontfix（1 项）

- **TD-A-005-01**：SDK 无 cancel/abort API（证据 `td_a_005_01_no_cancel_api.log`），现有超时保护为最终方案

### Open（3 项，勿动）

- **TD-A-D6-EXEC-RACE**：并发安全敏感、非阻断
- **TD-A-D6-TOOL-PARTIAL**：partial result 无格式 + 契约字段
- **TD-A-D7-CACHE-USER-DIMENSION**：契约无可信 user_id

### REWORK 修订要点（D 主审 2026-08-18，全部完成）

- **R-1**：TD-A-005-04 曾降级 PARTIAL → **2026-08-18 判别性证据后升级 HOST_VERIFIED**（台账/证据日志已回写）
- **#3-#8**：Day3 scope 五值、C++ mutex/泄漏说明、except 精确化、health degraded、真并发测试、PR 描述修正
- **#2**：005-01/02 VM 探测日志已落盘（证据缺口关闭）

## 四、Day9 分支内容（feat/day9-embedding-throughput，未推送）

Day9（台账 R47）：Embedding 吞吐/查询缓存/积压指标——与 TD 分支**完全独立**。

- `embedding/embedding_cache.py`：EmbeddingQueryCache（LRU + 维度+原文哈希键 + 深拷贝 + 空向量不缓存）+ EmbeddingCoalescer
- `embedding/embedding_metrics.py`：EmbeddingBacklogTracker（backlog/oldest_pending_age）
- `embedding/embedding_service.py`：embed 路径接入缓存/合并/积压 + health 扩展
- `scripts/benchmark_embedding.py` + `scripts/verify_day9_vm.sh` + `tests/test_embedding_d9.py`（18 项）
- **L2 真实吞吐基线（宿主已跑）**：串行 13.75 req/s / P99 148.69ms（<180ms 预算达标）；并发 4/8 时 P99 863/1145ms（Bridge 线程池 max_workers=2 瓶颈）
- ⚠️ 分支基于旧 main（d37fb95），推送前需 rebase 到最新 main（5bd2c3e）

## 五、麒麟 VM 环境（宿主操作记录）

- **访问**：SSH `ssh -p 2222 Lyf@127.0.0.1`
- **共享目录**：`/mnt/shared` = WSL 仓库实时同步（vboxsf）
- **Python**：VM 只有 `/usr/bin/python3.12`（无 `python` 命令、无 pybind11）
- **pybind11**：已装（`apt python3-pybind11` 2.11.1）；构建：`cmake -B build -Dpybind11_DIR=$(python3 -m pybind11 --cmakedir) && cmake --build build -j4`
- **⚠️ C++ 改后必须 `rm -rf build` 全量重编**（vboxsf 时钟错误导致增量编译产物不可靠——TD-A-005-04 段错误反复的元凶之一）
- **venv**：`/tmp/day8-venv` 易失——本地用仓库 `.venv`（`/home/fff/projects/kylinOS-agent-memory/.venv/bin/python`）
- **SDK**：`libkylin-coreai-embedding 1.2.0.0-0k0.4`；`.so` 路径 `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1`
- **SDK 恢复**：`sudo apt-get install --reinstall libkylin-coreai-embedding`

## 六、测试与证据

- **L1**：`272 passed + 49 skipped`（.venv 跑；skip 49 = 47 基础 + 2 项 real 用例 KYLIN_L2 门控）
- **L2 证据**（evidence/l2-kylin-vm/）：
  - `td_a_005_04_model_name.log`（**判别性结论已追加**：RAW 非空 + model_info 二次调用走缓存稳定）
  - `td_a_005_09_sdk_missing.log`（so 缺失降级 + apt 恢复）
  - `td_a_005_01_no_cancel_api.log` + `td_a_005_02_concurrent_hang.log`（新增）
  - `day8_verify_latest.log` / `day9_verify_latest.log`
- **证据门禁**：tested_commit 绑定被测代码；L2 日志含 Step1 原始输出；checksum 三处一致

## 七、环境坑（必读，防踩）

1. **shell 陷阱**：当前会话 shell 是 Windows PowerShell——命令用 `wsl -d Ubuntu -- bash -lc "..."` 执行；**内层 heredoc/引号会与外层 wsl -c 引号冲突**——写临时 py 脚本到 `tmp/` 再执行最稳
2. **heredoc 反引号**：bash heredoc 里反引号会被执行——改用 write_file 写脚本文件
3. **awk `$` 展开**：PowerShell/bash 双引号内 `$` 展开——用单引号或写文件
4. **venv 易失**：`/tmp/day8-venv` 常被清——本地用仓库 `.venv`
5. **并发测试坑**：全量跑时 `EmbeddingProvider` 类可能被其他测试 monkeypatch 成 function——**并发测试必须用独立 lock 解耦**（importlib.reload 隔离验证）
6. **git push**：wsl 内 push 超时——用 Windows git：`& "D:\Git\cmd\git.exe" -C "\\wsl.localhost\Ubuntu\home\fff\projects\kylinOS-agent-memory" push ...`（stderr 显示为错误是正常，看进度行）
7. **evidence tested_commit 回填**：commit 后 amend 会改 hash——证据标注写"见 index.yaml"而非硬编码 hash
8. **⚠️ TD-A-005-04 教训（重要）**：
   - SDK `get_model_list` **重复调用 use-after-free**（第一次成功、第二次段错误）——**必须缓存模型名**（cached_model_name_ + model_name_cached_，session 生命周期内不变，destroy_unlocked 清缓存）
   - 不透明指针类型（`EmbeddingModelList*`/`EmbeddingModelInfo*`）在 pybind 编译下的函数指针调用有 **ABI 差异**——用 **void* 显式声明函数指针**（与 ctypes 一致）
   - **vboxsf 时钟错误 → 增量编译产物不可靠（行为反复无常）——C++ 改动后必须 `rm -rf build` 全量重编**；若仍见"时钟错误"警告，先 `git update-index --refresh` + `touch` 源码再重编
   - 判别性证据方法：打印 `get_default_model_name()` 原始返回值（绕过 Provider 回退分支）才能证明动态查询路径生效

## 八、下一步建议（优先级）

1. **宿主复审 fix/td-a-pure**（R-1 + #3-#8 + 005-04 判别性全闭环，证据完整）
2. **确认 Day9 是否已单独发 PR**（分支 469be56 未推送，若未发需 rebase main 后推送）
3. **Day10**（缓存失效/临时文件清理/异常恢复）——需先看 75 项台账确认 Day10 A 轨任务
4. 工作区 2 个历史未跟踪文档（session-handoff-20260809/13.md）——可归档或删除

## 九、关键文件索引

| 文件 | 用途 |
|---|---|
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 技术债台账（权威状态） |
| `docs/day8/01_task_card.md` + `02_pr_description.md` | Day8 任务卡/PR 描述 |
| `docs/fix-td-a-pure/02_pr_description.md` | fix/td-a-pure 的 PR 描述（REWORK 修订版） |
| `docs/project-management/session-handoff-20260818.md` | 本交接文档（权威） |
| `docs/baseline/01_sdk_model_abi_baseline.md` | SDK/模型/ABI 基线（含禁调标注） |
| `docs/day3/06_provider_contract_v1.md` | Provider 契约（category 六值 + scope 五值） |
| `third_party/kylin-coreai-embedding/reference/embedding_api.h` | SDK API 头文件参考 |
| `evidence/index.yaml` | 证据索引 |
| `cpp-bridge/src/embedding_bridge.cpp` + `include/embedding_bridge.h` | Bridge（含 TD-A-005-04 void* 调用 + 模型名缓存） |
| `scripts/verify_day4_vm.sh` / `verify_day9_vm.sh` | VM 验证脚本 |
| `scripts/benchmark_embedding.py` | 吞吐测量脚本 |
