# D3-C OS Agent 宿主事件契约 v1

Status: resolved

## 授权与责任边界

- 负责人：高翌哲临时接手 C 轨 D3-C；该授权仅覆盖 D3-C，不改变其 B 轨长期责任。
- 当前基线：`origin/main` @ `d37fb95eca9083eb480491cda2464ebe8515477d`（含 PR #19 的 D2-C squash 合并）；独立 worktree 已经用户授权 fast-forward 到该提交。
- 分支：`feat/C-d3-host-contract-v1`。
- Reviewer：D 主审；用户交互与安全影响由 E 补审。
- 工作时间：2026-08-14 12:46（Asia/Shanghai）开始，停止时间由用户另行通知。

## 目标

在不修改官方 AI 助手生产 Hook、不扩张到 B/D/E 轨实现的前提下，为下列 C 侧公共对象建立可审查、可序列化、可测试的 v1 候选契约：

1. `MemoryQuery`
2. `MemoryContext`
3. `TurnFinalizedEvent`
4. `ToolExecutionEvent`

同时记录合规生产 Hook 路径是否存在、备用候选、禁止路径及其证据等级。证据不足的内容必须保持 `UNVERIFIED`、`PENDING_*` 或 `BLOCKED`，不得为了完成 D3-C 宣称最终冻结。

## 正式交付物

- `docs/day3/10_os_agent_contract_start_gate.md`：输入证据、依赖和冻结门禁矩阵。
- `docs/day3/11_os_agent_event_contract_v1.md`：C++/JSON 字段、约束、版本兼容和错误语义。
- `docs/day3/12_os_agent_hook_path_decision.md`：合规生产路径条件、备用路径、禁止路径及证据状态。
- `docs/day3/13_os_agent_contract_validation_report.md`：本地 TDD、构建、数据检查和宿主阻断交接。
- `os-agent-integration/contracts/memory_event_contract_v1.h/.cpp`：Qt/C++ 公共契约与 JSON 转换接口。
- `os-agent-integration/contracts/examples/*.json`：独立的已知良好示例 Payload。
- `os-agent-integration/tests/test_memory_event_contract_v1.cpp`：面向公共接口的 Qt 契约测试。
- 必要的 `os-agent-integration/CMakeLists.txt`：只建立本契约与测试的构建入口，不实现生产 Hook。

## 明确不在范围内

- B 轨 Vector、FTS5、RRF、检索、索引、删除/重建一致性及检索评测。
- 补做 D2-C 的真实 Context/Tool/Turn、Gateway Audit 或超时降级宿主实验。
- 修改官方 AI 助手源码、QML 页面或真实 Hook 生产逻辑；这些属于后续 D4/D5 落地。
- 冻结 D 轨 UDS 帧格式、ID 生成、KYSEC、部署、回退或持久化实现。
- 改写 E 轨业务 Schema、安全红线或业务枚举。
- commit、push、创建 PR、Ready、merge；分别等待用户授权。

## 输入来源优先级

1. `origin/main` 已合并文档与代码。
2. 团队正式基线资料：15 天施工台账、SOP v1.1、官方 SDK 能力边界。
3. 麒麟 VM 当前 Commit 的可复核宿主证据。
4. 其余源码推断或设计稿只能作为候选，不得升级为宿主事实。

D2-C 只采用 `origin/main@d37fb95` 中已经 squash 合并的内容；不得再以来源分支
`docs/C-d2-osagent-runtime` 或其独立提交历史作为实现基线。

## 依赖与冻结门槛

- `MemoryContext`：D2-C 已合并部分观察与 PreChat 豁免记录，但真实请求前注入仍未技术证明；跨 Turn 复用、`context_version` 和真实注入结构依赖 C/D 证据。
- `ToolExecutionEvent`：D2-C 已合并的正式状态仍为 `NOT_VERIFIED`；真实 Tool 结构和状态语义缺少完整 C 轨宿主取证，最终冻结受阻。
- `TurnFinalizedEvent`：D2-C 有诊断性 `is_end=true` 观察，但证据索引仍为 `BLOCKED/E2`；重试、停止原因和完整 Gate 证据尚未闭合。
- UDS/IPC：只引用 D 轨已合并事实；不得由 C 轨单方面冻结。
- 若上述证据在本任务范围外仍未满足，交付状态只能是 `CANDIDATE`/`BLOCKED`，不能标记 `FROZEN`/`HOST_VERIFIED`。

## 拟确认的公共测试 seams

写首个测试前须由用户确认：

1. **C++ 值对象 seam**：调用者构造四类对象，并通过公开验证接口获得结构化成功或错误结果。
2. **JSON 契约 seam**：调用者只通过公开 `toJson`/`fromJson` 接口验证已知 Payload 的往返、缺失必填字段、未知字段兼容和版本拒绝。
3. **枚举/错误 seam**：调用者通过公开解析接口验证状态枚举与安全错误，不检查 private helper 或内部调用次数。

测试不 mock 自有类，不访问 private 方法，不以实现算法重算 expected；示例 JSON 使用人工审定的固定字面值。

## 完成定义

- 四个对象的字段、必填性、来源、禁止模型生成字段、枚举和兼容规则可追溯到输入来源。
- C++/JSON 示例一致，Qt 测试覆盖认可的公共 seams，并严格经历 red → green。
- 合规生产/备用/禁止 Hook 路径均有证据等级；真实 Tool/Turn 未验证时如实保持阻塞。
- 本地可运行检查全部记录；麒麟 L2 无法执行时列出命令、环境和待补证据。
- 提供修改文件、Diff、测试、风险、未完成项及建议提交信息，停止等待人工审核。
