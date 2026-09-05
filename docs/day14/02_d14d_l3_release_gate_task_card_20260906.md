# D14D 任务卡：L3 干净快照发布 Gate、回退与证据闭环

## 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | D14D |
| 任务标题 | L3 干净快照发布 Gate、安装生命周期、回退与证据闭环 |
| 责任轨道 | D |
| 创建日期 | 2026-09-06 |
| 初始状态 | `PREPARED` |
| 工作类型 | `release/test-infrastructure`；不修改业务、IPC、Schema、数据库或 SDK ABI |
| 关联任务 | D13D 环境冻结、D13E 正式封存、D14A 发布包、D14B L3 检索/索引回归 |

## 目标

在指定银河麒麟 V11 x86_64 VirtualBox 干净快照中，对一个唯一、可追溯的集成提交和
一个唯一的 D14A 发布包执行完整发布生命周期：预检、安装、真实 SDK 冒烟、服务重启、OS
重启、升级、卸载、回退以及状态复核。D14D 仅在所有 Gate 通过且证据包校验完整时，才能
为 D14B 提供 `L3_READY` 的干净快照和发布包输入。

本任务不以 D14A 当前分支的局部 L3 冒烟替代正式干净快照验证，也不以 D13D 的隔离
`--no-outbox` 预检替代正式冻结或发布验收。

## 当前事实与开工边界

| 项目 | 当前事实 | D14D 处理 |
| --- | --- | --- |
| D13D | `68c678c` 已记录 VM 固定 Trust Root 为 `PREPARED`；Review Seal、Execution Seal、四类真实 raw JSONL 仍未完成 | D14D 可以准备；正式 `L3_READY` 必须等 D13D `FROZEN` |
| D14A | `release/D14A-clean-vm-package@e3d4b9d` 有 package-only SDK 冒烟；其冻结合同的 source commit 为 `5424d28` | 必须在最终集成提交上重建包并重新计算 manifest/SHA256，不可复用该分支的包作为正式产物 |
| D13E 主线 | `kylin-mem/main@4a32e5c` 含 D13E 正式 Runner 门禁 | 最终 D14D 被测提交必须包含该主线，且与 D13D/D14B 完全相同 |
| D14B | 工作清单已存在但 0/8 VM 项待开始 | 仅消费 D14D 的 `L3_READY` 输出，不由 D14D 替代检索/索引业务回归 |

2026-09-06 已创建本地发布代码候选提交
`336125d7749b889f0275f0df05f9a3115f0249db`（分支 `chore/d14d-integration-candidate`）：它包含
`4a32e5c`、D14A release 分支、P1 修复的 cherry-pick `df5f4af`/`13c43f8`，以及安装失败清理和
替换 unit 所有权、替换服务与受管路径保护。该提交仅为
`SELECTED_CANDIDATE`，尚未完成评审、D13D `FROZEN` 或任何 D14D L3 Gate，不能写入正式
`tested_commit` 字段。

`e3d4b9d` 不包含 `4a32e5c`，所以这两个提交都不是 D14D 的正式被测基线。D14D 的
`tested_commit` 只能在 D13D 冻结输入和 D14A 发布包改动完成集成、审查后，由 D 主审
记录为完整 40 位 SHA。

## 批准范围

允许：

- 新增或修改 D14D 文档、只读采集脚本、发布预检脚本、证据清单、SHA-256 清单和
  `evidence/index.yaml` 的 D14D 条目；
- 从已确认的 VM 快照创建新的 D14D 专用干净快照，且不覆盖旧快照；
- 在 D14D 专用用户数据与服务命名空间中安装、验证、升级、卸载及回退最终发布包；
- 执行只读系统/SDK/version 采集和任务规定的 user-level systemd 操作。

禁止：

- 修改 FRZ-IPC、Pydantic/JSON Schema、SQLite/Alembic、错误码、D13E Dataset/Gold/
  Threshold，或为通过 Gate 改动检索、Embedding、Vector 生产逻辑；
- 覆盖 `/usr` 下系统库、官方模型目录、系统 SDK 或既有 VM 快照；
- 使用个人源码 checkout、个人 venv、历史包、开发集或旧 VM 日志宣称正式 L3 结果；
- 记录私钥、sudo 密码、Token、封存样本正文、用户原文或可识别敏感数据；
- 覆盖已有 D13D/D14A/D14B evidence root。每次运行必须新建目录。

## 冻结输入/输出契约

### 输入

| 字段 | 要求 | 缺失时结果 |
| --- | --- | --- |
| `tested_commit` | 审核后、包含 D13E 和 D14A 的完整 40 位 SHA；VM HEAD、包 manifest、D13D manifest 一致 | `BLOCKED` |
| `package_tar_sha256` | 在被测提交的 clean worktree 重新构建的 D14A tar 包 SHA-256 | `BLOCKED` |
| `package_manifest_sha256` | 包内 `manifest.json` SHA-256；文件清单逐项验签 | `BLOCKED` |
| `d13d_freeze_reference` | `FROZEN` 的环境记录、Seal 验签结果及同一 `tested_commit` | `BLOCKED` |
| `vm_identity` | VM 名称、UUID、OS/kernel/架构、CPU/RAM/磁盘、源快照和新快照 | `BLOCKED` |
| `install_inputs` | SDK/runtime/model 包版本、动态库实际路径/SHA-256、安装 prefix、unit 内容 | `BLOCKED` |
| `upgrade_package_tar_sha256` | 升级场景的第二个经审查 package；若无批准升级包，升级 Gate 标 `NOT_RUN`，不能标 PASS | `NOT_RUN` |

### 输出

每次运行使用唯一目录 `evidence/l3-kylin-vm/d14d_<UTC_RUN_ID>/`：

```text
environment.json
release_identity.json
package_audit.txt
install.log
verify_after_install.json
verify_after_service_restart.json
verify_after_os_reboot.json
upgrade.log
uninstall.log
rollback.log
commands.log
SHA256SUMS
README.md
```

`release_identity.json` 至少包含 `tested_commit`、`package_tar_sha256`、
`package_manifest_sha256`、`d13d_freeze_reference`、VM identity、所有 Gate 的
退出码和 `release_status`。`release_status` 只能是 `PREPARED`、`BLOCKED`、
`L3_READY` 或 `INVALIDATED`。

## Gate 与执行顺序

| Gate | 动作 | 通过条件 | 失败处理 |
| --- | --- | --- | --- |
| G0 基线 | 记录并核对最终 SHA、D13D 冻结、包 hash 和 VM 快照 | 所有输入完整且 SHA 一致 | 停止，`BLOCKED` |
| G1 快照 | 从可回退源创建新 D14D 快照；记录 UUID/资源 | 新快照唯一，历史快照未覆盖 | 停止，保留诊断 |
| G2 包审计 | 验证 `SHA256SUMS`、manifest、`ldd`、RPATH、开发路径 | 无 hash 漂移、无 `not found`、无个人路径 | 停止，重建包 |
| G3 安装 | clean VM package-only install，启动 user service | unit active、socket 与 MainPID 一致 | 回退并记录 |
| G4 真 SDK | 采集 `/proc/<PID>/maps`，调用真实 `memory.embed` | SDK hash 匹配、`fake=false`、dimension=768 | 回退并记录 |
| G5 服务重启 | `systemctl --user restart kylin-memory` 后重验 G3/G4 | 新 socket、单服务实例、SDK 重载成功 | 回退并记录 |
| G6 OS 重启 | OS reboot 后服务自启，重验 G3/G4 | active、socket/health/SDK 正常 | 回退并记录 |
| G7 升级 | 仅有经批准的第二包时执行安装前后数据/配置兼容性验证 | package identity、数据策略、服务状态均符合批准方案 | 标 `NOT_RUN` 或回退；不得临时制造升级包 |
| G8 卸载/回退 | 卸载 D14D 包，复验计划中的保留/清除策略；恢复此前状态 | 无残留 unit/process/socket，或按记录恢复 | `INVALIDATED` 并保留日志 |
| G9 证据 | 生成 SHA256SUMS，登记 evidence index，交接 D14B | 全文件可校验，证据无敏感数据 | `BLOCKED` |

G7 不可用“同一包重复安装”冒充升级。升级包及数据保留/清除策略缺失时，D14D 可以完成
G0--G6、G8--G9 的准备或部分验证，但不得声明完整 `L3_READY`。

## 验收标准

1. 一个完整 `tested_commit` 同时绑定 D13D、D14A package、D14D evidence 和 D14B 输入。
2. 发布包可在干净 VM 上安装，运行不依赖源码 checkout、个人 venv 或开发者 HOME。
3. 实际加载 SDK 及真实 Embedding 结果与包合同相符；宿主日志而非 L0/L1 是此项证据。
4. 服务与 OS 重启后，systemd、socket、health、SDK 和数据策略均按记录通过。
5. 经批准的升级、卸载和回退路径均有实际日志；缺失升级输入时明确 `NOT_RUN`，不伪造 PASS。
6. 证据根校验通过并登记，且无密钥、凭据、封存原文或用户原文。
7. D14B 仅在 D14D `L3_READY` 且 D13D `FROZEN` 后开始正式业务回归。

## 分阶段计划

1. **P0，已完成**：已建立本任务卡，核实 D13D/D14A/D14B 提交关系，列出唯一基线选择条件。
2. **P1，进行中**：已完成 D14A 静态审计并新增只读 G0/G2 preflight collector。P1-01 至 P1-04
   已在 `fix/d14a-release-lifecycle@9536746` 完成修复候选和 L0 守卫测试，并进入本地发布代码候选；
   仍待独立审查、最终基线选择和 VM 复核；
   P1-05（升级输入/策略）与 P1-06（最终集成提交）仍是进入 VM 生命周期验证的前置条件。
3. **P2**：在 VM 创建 D14D 新快照，执行 G0--G2，生成 `PREPARED` evidence root。
4. **P3**：在 D13D `FROZEN` 后执行 G3--G6；有批准升级包后执行 G7；最后执行 G8--G9。
5. **P4**：向 D14B 交接 `L3_READY` evidence reference、commit、package hash、snapshot 与限制；D14B 独立执行检索/索引回归。

## 测试边界

- WSL/L0：shell 语法、manifest/SHA256 格式、安装/验证脚本的 fail-closed 静态路径；不作为 L3 成功证据。
- 麒麟 L3：G1--G9 的唯一可接受成品证据环境。SDK ABI、实际加载、Embedding、systemd、socket、OS reboot 和回退均必须在 VM 实测。

## 风险与回滚

- 任一 commit、包、依赖、D13D Freeze、VM 快照或配置变化会使该 run `INVALIDATED`；创建新目录，不覆盖旧目录。
- 安装、重启、升级或验证失败时，停止后续 Gate，使用安装前记录的 user-service/工作树状态回退并复验；不修改系统 SDK 或官方模型。
- D14D 不解除 D13D Seal/raw 阻塞，也不替代 D14B 的检索、删除、重建与性能验证。

## 技术债

- 无新增技术债。D13A 的既有测试维护问题是并行事项，不能通过跳过测试或弱化 D14D Gate 处理。

*编制依据：D13D 任务卡与 2026-09-06 Trust Root 续办记录、D14A release package contract、D14B L3 worklist、`Kylin-runtime-knowledge/VERSION_MAP.md`（2026-09-01）。*
