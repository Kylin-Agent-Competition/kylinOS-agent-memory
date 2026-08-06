# 会话归档：A 轨 Day1–Day4（2026-07-31 ~ 2026-08-07）

> 用途：新会话初始化上下文，快速继承本项目技能、技术栈、进度与卡点。
> 生成时间：2026-08-07。状态：Day4 PR #17 已推送待复审，Day5 分支待合并后同步。

---

## 一、项目基础信息

1. **项目类型与技术栈**
   - 银河麒麟 OS AI Agent 记忆系统（比赛项目，GitHub: `Kylin-Agent-Competition/kylinOS-agent-memory`），后端为主。
   - 技术栈：**C++17（dlopen/dlsym 动态加载 SDK）+ pybind11 + Python 3.12 + CMake + pytest/CTest**。
   - 宿主：银河麒麟 V11 x86_64（VirtualBox 虚拟机，Runtime 1.3.0）；开发：Windows + WSL2（Ubuntu）。

2. **Agent 工具与运行模式**
   - Agent：Reasonix（Windows 侧部署）。工作区经 UNC 路径 `\\wsl.localhost\Ubuntu\home\fff\projects\kylinOS-agent-memory` 访问 WSL 仓库。
   - 运行模式：交互式 goal 模式 + AutoResearch；写文件/命令经 WSL 层执行。
   - 使用场景：按天（Day1~Day5）产出可合并 PR，麒麟 VM 实测证据归档。

3. **开发核心需求 / 业务定位**
   - 为麒麟 AI Runtime 的 Embedding SDK（`libkysdk-coreai-embedding.so.1`）建立 **C++ Bridge → pybind11 → Python EmbeddingProvider** 垂直链路。
   - 每阶段冻结契约（Provider 输入输出、Bridge 错误类型/超时/取消/模型状态），所有声明必须有麒麟 VM 实测证据，禁止无证据假实现。

---

## 二、项目目标与硬性约束

1. **长期最终目标**
   - 实现内存（memory）服务的 Embedding 向量化能力：真实向量或明确空降级，无固定样例假实现。
   - 按 Day1→Day5 递进：证据收口 → 最小调用 → Provider/Bridge 契约 → 工程骨架可编译可调用 → 最小垂直链路。

2. **短期阶段功能预期**
   - Day4（当前）：`cpp-bridge/`（C++ Bridge dlopen/dlsym + 错误码契约）、`memory-service/providers/`（EmbeddingProvider）、pybind11 模块、编译/导入/异常映射测试。
   - Day5（已建分支未推送）：EmbeddingService（UDS + 协议 + 真实降级）+ 线程池不阻塞。

3. **硬性限制（麒麟实测结论，必须遵守）**
   - **同进程 `dlclose → dlopen` 会 Abort**（SDK 限制）。
   - **同进程 `destroy_session → create_session` 会挂起**。
   - **`create_session` 后必须先完成至少一次成功 `embed()`（模型就绪）才能安全 `destroy_session`**，否则 `terminate called without an active exception`。
   - 结论：Provider 采用**进程级单例 Bridge 共享 SDK 会话**，close 只释放引用，不 dlclose；`destroy` 后进入不可恢复终态（`ERR_SESSION_DESTROYED` / `ERR_FATAL_FAILURE`）。
   - 证据硬门禁：最终 L2 日志必须**脚本自动生成**，含 Step 1 原始输出（`git rev-parse HEAD` / `git status --porcelain --untracked-files=all` / `git diff --exit-code` / `git diff --cached --exit-code`），日志顶部 Commit、rev-parse HEAD、index.yaml `tested_commit`、实际被测代码四项一致。
   - Review 要求：不允许"建议 8192 bytes 固定上限"类无证据声明；未实测项必须标注 UNTESTED / HOST_VERIFIED / ABI_VERIFIED，禁止统一模糊 VERIFIED。

---

## 三、开发进度 & 当前阶段

1. **已完成并落地**
   - **Day1**（PR 已合并）：`evidence/l2-kylin-vm/` 归档 runtime_identity.log / embedding_abi_symbols.log / minimal_embedding_run.log，index.yaml 状态字段规范化；ABI 兼容头 `cpp-bridge/embedding_abi_compat.h`（opaque forward typedef）；三方 LICENSE（LGPL-2.1-or-later）归档；文档修正 nm/readelf 只确认符号导出、原型来自头文件。
   - **Day2**（PR #9 已合并 main，commit `8c2017d`）：最小同步 Embedding 调用 5 用例（中文/英文/偏好/单字符/空输入），维度 768、L2=1.0；`day2_smoke_test.cpp`。
   - **Day3**（PR 已合并 main，commit `c532871`）：`docs/day3/06_provider_contract_v1.md`（Provider v1 契约）、`bridge_error_contract.h`（错误码：SUCCESS/ERR_DLOPEN_FAILED/ERR_DLSYM_FAILED/ERR_SESSION_CREATE/ERR_SESSION_INIT/ERR_EMBED_CALL/ERR_TIMEOUT/ERR_CANCELLED/ERR_MODEL_NOT_LOADED/ERR_MODEL_INVALID/ERR_SESSION_DESTROYED/ERR_FATAL_FAILURE）、技术债登记 TD-A-005-01~06。生命周期契约变更（进程级单例/配置锁定/close-restart 模型 B）**标注"待 Gate 审批"**。
   - **Day4**（PR #17 当前，分支 `feat/day4-bridge-provider-new`）：
     - C++ Bridge：`cpp-bridge/src/embedding_bridge.cpp`（load_impl/create_session_impl/embed_impl/destroy_session，`fatal_failure_` + `session_destroyed_` 终态标志，dlsym/init_session 失败置不可恢复态）。
     - pybind11：`py_module.cpp`（10+ 类异常映射，含 `BridgeSessionDestroyedError` / `BridgeFatalError`，`session_destroyed` property）。
     - Provider：`memory-service/providers/embedding_provider.py`（进程级单例 `_shared_bridge`、`_lifecycle` 状态机 UNINIT→INIT→READY→CLOSED、so_path 归一化+配置锁定 `ERR_CONFIG_CONFLICT`、`_BRIDGE_ERROR_MAP`）。
     - 测试：CTest 5 项（bridge_errors/so_not_found/malformed/destroyed/failure_recovery）+ pytest 47 项（33+13+1，含 failure_recovery 5 项、interpreter_exit 1 项）。
     - 验证脚本 `scripts/verify_day4_vm.sh`（Step1 原始输出 → `/tmp/day4_step1.log` 合并到 `evidence/l2-kylin-vm/day4_verify_latest.log`）。
     - **第六轮 REWORK 已全绿**：麒麟 VM 最终 L2 FAILURES=0（ctest 5/5、pytest 47 项无 Skip、smoke 11、生命周期 4 路径），index.yaml 绑定 `tested_commit=e62e91b`、`evidence_commit=0b2a629...`、`checksum=3176a8...`；已推送 HEAD=`b29fec5`。

2. **当前卡点 / 未解决冲突**
   - Day4 PR #17 已推送 `b29fec5`，**等待 Reviewer 复审**（第六轮结论 REWORK 已修复，待确认）。
   - Day5 分支 `feat/day5-minimal-vertical-chain`（HEAD `438e91e`）基于 Day4 **旧版**（`5510f94`），尚未 rebase 到 Day4 最新；Day4 合并进 main 后需把 Day5 框架内容放入 main（用户明确"等合并吧"）。
   - 历史分支残留：`backup/day2-*`、`te`、`feat/day2-embedding-smoke-v2`（behind 5）等，勿混淆。
   - 麒麟 VM 需**手动开机**；关机后 SSH（`ssh -p 2222 Lyf@127.0.0.1`）与共享文件夹均不可用。

3. **待办清单**
   - [ ] 等待 Day4 PR #17 Reviewer 复审结果；若有 REWORK 按 `day-pr-review` skill 逐项修复。
   - [ ] Day4 合并后：将 Day5 分支 rebase 到最新 main，删除旧 Day4 内容（只保留 Day5 新增），再提交 Day5 PR。
   - [ ] Day5 若需麒麟 VM 验证：EmbeddingService UDS 链路 + 降级路径真实测试。

---

## 四、核心技术关键信息

1. **系统差异结论（Windows ↔ Ubuntu/WSL）**
   - Windows Agent（Reasonix）经 `\\wsl.localhost\...` 访问 WSL 仓库；**文件写入需注意 UTF-16/CRLF 转换**（PowerShell 重定向会写 UTF-16 → 用 Python 脚本 `open(..., encoding='utf-8')` 写文件绕过）。
   - **PowerShell 不支持 `&&`/`||`/`head`/`grep`**；多行脚本/正则易被转义破坏 → 一律写 `tmp_*.py` 脚本文件执行，用完删除（保持工作区严格干净）。
   - **WSL 与 VM 之间无网络互通**（NAT 模式 localhost 代理不镜像）→ 用 **VirtualBox 共享文件夹**（vboxsf 挂载 `/mnt/shared`）同步代码，VM 内 `sudo mount -t vboxsf -o rw,uid=$(id -u),gid=$(id -g) kylinOS-agent-memory /mnt/shared`。
   - vboxsf **stat 缓存**会导致 git 误报文件修改 → 脚本 Step1 先 `git update-index --refresh`。

2. **可用命令 / 路径规则**
   - 仓库（WSL）：`/home/fff/projects/kylinOS-agent-memory`；UNC：`\\wsl.localhost\Ubuntu\home\fff\projects\kylinOS-agent-memory`；VM 挂载：`/mnt/shared`。
   - 麒麟 SDK 路径：`/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 → 1.0.0`；Runtime `/usr/bin/kylin-ai-runtime`；模型 `ensemble-embd_gte-base_uint8-text`，**维度 768，L2=1.000000**；默认模型目录 `/usr/share/kylin-ai/model-repository/`。
   - VM 运行环境：`source /tmp/day4-venv/bin/activate`（`python3 -m venv` + `pip install pybind11`）；编译 `g++ -std=c++17 -I. -ldl`；CMake `cmake -B build -Dpybind11_DIR=$(python -m pybind11 --cmakedir) && cmake --build build -j2 && ctest --test-dir build`。
   - 麒麟验证入口（唯一标准）：`cd /mnt/shared && git rev-parse HEAD && bash scripts/verify_day4_vm.sh`。
   - 麒麟 pytest：`PYTHONPATH=/mnt/shared/cpp-bridge/build:/mnt/shared/memory-service LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH KYLIN_L2=1 python -m pytest ...`。
   - Windows 侧验证（无 SDK）：`.venv/bin/python -m pytest`（纯 Python 测试）；`python -c "import ast; ast.parse(...)"` 检查语法。

3. **可行 / 不可行方案**
   - ✅ 进程级单例 Bridge（不 dlclose）——麒麟实测通过。
   - ✅ dlsym/init_session 失败 → 不可恢复终态（方案 A，不重试）——Review 认可。
   - ✅ 假 SDK（fake_sdk_malformed.c 等）做 CTest 单元测试；真实 SDK 走麒麟 L2。
   - ❌ dlclose→dlopen 重试（Abort）；destroy→create 重试（挂起）——禁止。
   - ❌ "建议固定 8192 bytes"无证据上限声明——禁止，只写已实测值（约 2170 bytes）。

---

## 五、现有痛点与限制

1. **Windows Agent ↔ Ubuntu 仓库兼容问题**
   - PowerShell 编码（GBK 默认）导致中文输出/正则频繁报错；所有跨平台命令用 Python `subprocess` + `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`。
   - git 输出经 PowerShell 管道被转 UTF-16/乱码；用 `git -C <repo> ...` 直接调用 + Python 解码。
   - `--force-with-lease` 推送前必须 `git fetch`（远端可能被其他成员 merge 更新）；曾遇远端 merge commit 与本地 rebase 分叉，需确认无他人代码丢失后 force push。

2. **对话上下文溢出 / 存储限制**
   - 长会话多次 compaction；用户反复贴同一份 Review 文本触发 stale loop（AutoResearch stale_count 机制）。
   - 处理：**每轮修复后立即提交 + 归档证据**，减少上下文依赖；用 `day-pr-review` skill 自检替代逐条人工核对。

3. **开发环境冲突**
   - 多 PR 并行（day2/day3/day4 均改 `evidence/index.yaml`、`docs/`）→ 合并冲突频繁；规则：**以最新 main 为准重建，只追加本 PR 条目，保留其他轨道（B 轨 VECTOR-CALL-001/002/003）**。
   - VM 需开机 + 手动挂载共享文件夹；关机后所有麒麟测试不可用。

---

## 六、下一阶段开发执行计划

1. **优先执行**
   - 检查 PR #17 复审结论；若 REWORK → 按 `day-pr-review` skill 逐项核对修复 → 麒麟 VM 重跑 `verify_day4_vm.sh` 生成最终 L2 日志 → 回填 index.yaml（tested_commit/evidence_commit/checksum）→ 推送。
   - Day4 合并进 main 后：`git checkout main && git pull` → 建 Day5 新分支（或 rebase 现有 `feat/day5-minimal-vertical-chain`）→ **逐个文件对比 Day5 与 main**，只保留 Day5 新增，删除旧 Day4 残留 → 提交 Day5 PR。

2. **优化 / 排错方向**
   - 所有需麒麟 VM 验证的命令一次性给用户（`cd /mnt/shared && git rev-parse HEAD && bash scripts/verify_day4_vm.sh`），避免逐条粘贴出错。
   - 提交保持原子化（一个小修复一次 commit，前缀 feat/fix/docs/test），提交前 `git diff --check` + rebase main。
   - 新会话优先读 `docs/day4/08_bridge_provider_skeleton.md`、`evidence/index.yaml`、`.reasonix/skills/day-pr-review/SKILL.md` 快速恢复上下文。

---

## 附：提交 / 分支规范（用户强制要求，纳入 skill 自检）

- 主分支禁止直推；分支命名 `feature/X`、`fix/X`；commit 前缀 `feat:`/`fix:`/`docs:`/`style:`/`refactor:`/`perf:`/`test:`/`chore:`，示例 `fix(CardManager)：修复了出牌卡住的bug`。
- **原子化提交**（修一个小 bug 提交一次，便于回退）；提交 PR 前本地 rebase main 解决冲突。
- 没有根据的内容不写；需要用户提供数据时明确列出（哈希/网址/LICENSE/日志）。
- PR 描述按仓库模板（背景/修改范围/明确不修改范围/关联任务与技术债/架构依据/文件清单/测试结果 L0-L3/性能影响/已知限制/回滚方式/Reviewer 结论）。

## 附：证据文件索引（麒麟 VM 已归档）

`evidence/l2-kylin-vm/` 下：`runtime_identity.log`、`embedding_abi_symbols.log`、`minimal_embedding_run.log`、`day2_smoke_run.log`、`day2_smoke_test.cpp`、`day4_bridge_smoke_run.log`（HISTORICAL）、`day4_verify_latest.log`（当前有效，checksum `3176a8f4...`）。
