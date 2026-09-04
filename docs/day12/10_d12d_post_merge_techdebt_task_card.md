# D12D 合并后技术债跟进任务卡

| 字段 | 内容 |
| --- | --- |
| 任务编号 | D12D-PostMerge-01 |
| 基线 | `main@b70827c`（D12D #131 已合并） |
| 责任范围 | D 轨部署、systemd、KySec 验证环境、UDS 路径与证据归档 |
| 关联项 | `TD-KYSEC-001`、`TD-DEPLOY-001`、`TD-049`、`TD-055` |
| 阶段 | VM L2 故障注入与当前 Commit 证据补齐 |

## 目标

在同一麒麟 VM、同一 `tested_commit` 下，补齐 D12D Path C 未覆盖的部署、KySec、服务恢复和 Socket 隔离验证。故障注入发现 D 轨范围内的问题时，按最小修复原则修复并重跑受影响场景。

## 本批范围

1. `TD-KYSEC-001`：记录实际 KSaf/KySec 内核、模块、服务、工具、TPM-bypass 和单一测试二进制候选。真实 KySec 授权、执行和撤销仅在人工确认实际工具参数与目标二进制后执行。
2. `TD-DEPLOY-001`：核对构建产物、wrapper、unit、依赖、安装前置条件和回退资产；需要实际安装/回退时使用受控快照并记录前后状态。
3. `TD-049`：核对正式 Socket 是否位于 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`、目录为 0700、Socket/数据库为 0600；旧 `/tmp/kylin-memory/embedding.sock` 只作为历史风险搜索目标，不作为生产路径。
4. `TD-055`：验证服务重启后的 active、Socket、UDS `memory.retrieve` 真实空上下文降级；OS 重启与 C→D→B 真实输入作为独立 VM 场景，必须绑定当前 Commit。

## 禁止修改范围

- 不改变 FRZ-IPC、Schema、数据库迁移或错误码；
- 不关闭 KySec/KSaf，不对全局策略写入，不覆盖官方运行库；
- 不把 D12D 旧 Path C 的 `0820036` Runtime 证据写成 `b70827c` 证据；
- 不把 Mock、演示壳或未知方法调用写成 D→C→B 闭环；
- 不代行 A/B/C/E 轨实现。

## 验证与关闭边界

| 项 | 本批最低产出 | 不足以关闭的情况 |
| --- | --- | --- |
| `TD-KYSEC-001` | 当前 KySec 状态、实际 CLI 帮助、候选二进制 SHA-256、日志脱敏检查 | 仅内核模块/服务运行；未完成单二进制授权和撤销 |
| `TD-DEPLOY-001` | 当前 Commit 的 preflight、wrapper/unit、服务状态和回退计划 | 仅引用历史 D11D 安装日志 |
| `TD-049` | 当前路径/权限/旧路径不存在或不可访问的证据 | 仅文件存在性；未验证跨 UID fail-closed |
| `TD-055` | 当前 Commit 服务重启后 active、Socket 与 UDS `memory.retrieve` | 未做 OS 重启或 C 轨真实输入，不能关闭 |

## L2 执行顺序

1. 将当前 `main@b70827c` 部署到可回退的 VM 快照，记录 Commit、用户、内核和时间。
2. 运行 `scripts/verify_d12d_post_merge_techdebt_vm.sh` 的只读模式，保存原始输出。
3. 人工核对 KySec CLI 的真实授权/撤销语法后，对单个测试二进制执行最小验证并立即回退。
4. 在确认服务维护窗口后，运行脚本的 `--service-restart` 模式；OS 重启另行执行并重新运行只读模式。
5. 用 C 轨真实请求完成 D→C→B 路径；若没有该输入，保持 `TD-055` Open。
6. 计算日志 SHA-256，更新 `evidence/index.yaml` 和技术债状态，交由 E 非作者 Reviewer 复核。

## 当前已知限制

- VM 的 KSaf/KySec 已运行，但 TPM-bypass 不等于真实策略授权已经验证。
- D12D #131 Path C 只提供 `0820036` 的阶段性运行证据；本批必须重新绑定 `b70827c` 或其后续修复 Commit。
- `memory.retrieve` 当前可返回真实空上下文降级；这不等于生产级检索或 D→C→B 闭环。
