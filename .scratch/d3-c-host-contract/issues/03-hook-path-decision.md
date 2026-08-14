# D3-C Hook 主路径与备用路径结论

Type: task
Status: resolved
Blocked by: 01

## Outcome

生成 `docs/day3/12_os_agent_hook_path_decision.md`，冻结能够由现有证据支持的主路径，并把备用/禁止路径的批准状态写清楚。

## Required decisions

- Pre-Chat：`SystemChat::sendMessageImpl` 中 `chatAsync` 前的请求构造边界。
- Post-Turn：`CMsgPane` 最终 `is_end=true`、完整回答仍可取得且缓冲清理前的边界。
- Tool：`sendToolMessage`/真实 Tool 结果回调只能按证据标为候选；不得把 Prompt Skill 当 Tool。
- 备用路径：只有已批准且具备来源的路径才能写“批准”；否则标 `PENDING_APPROVAL`。
- 禁止路径：污染 `RECORD.message`、阻塞 UI 线程、模型自述冒充 Tool、在 C 轨冻结 D 轨 IPC。

## Acceptance

- 每条路径含修改语义、失败降级、证据等级、L2 验证项和回退边界。
- 不修改生产 Hook 源码。

## Comments

- 2026-08-14：主路径选择为官方 AI 助手当前受支持源码上的最小 source-level Hook；精确位置仍按语义和当前源码重新核对。
- 2026-08-14：未找到已批准备用；独立 Qt 演示壳与结构化执行 Adapter 仅列为 `PENDING_D_E_APPROVAL` 候选。

## Answer

- 已生成 `docs/day3/12_os_agent_hook_path_decision.md`。
- 当前决策：`PRIMARY_PATH_SELECTED / NO_APPROVED_BACKUP / BLOCKED_FOR_PRODUCTION`。
- 未修改官方 AI 助手或其他生产 Hook 源码。
