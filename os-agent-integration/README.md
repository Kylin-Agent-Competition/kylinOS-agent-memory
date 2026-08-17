# OS Agent Integration

## 模块定位

官方 AI 助手 Hook 集成层，负责拦截、转换官方 AI 助手的 Tool/Turn 调用，通过 MemoryClient 将上下文注入记忆管线，或从记忆服务拉取相关历史。

## 输入与输出

- **输入**：官方 AI 助手的 Tool Call / Turn / Context 事件
- **输出**：增强后的 Context 注入、Tool Result 反馈

## 责任轨道

- **主要**：C、D、E
- **协作**：A（Embedding 语义理解）

## 当前状态

**D3-C 已实现 Qt/C++/JSON v1 候选契约、脱敏示例和本地契约测试；生产 Hook、MemoryClient
接入与真实宿主映射仍未实现。**
当前只有 Pre-Chat、Post-Turn、Tool Result 语义 seams，未找到受支持且符合本模块边界的
生产扩展点，也没有已批准备用路径，故生产接入保持 `BLOCKED`。

- 契约：`contracts/memory_event_contract_v1.h/.cpp`
- 示例：`contracts/examples/*.json`
- 测试：`tests/test_memory_event_contract_v1.cpp`
- 契约文档：`../docs/day3/11_os_agent_event_contract_v1.md`
- Hook 决策：`../docs/day3/12_os_agent_hook_path_decision.md`
- 验证报告：`../docs/day3/13_os_agent_contract_validation_report.md`

当前候选不得表述为最终 `FROZEN` 或 `HOST_VERIFIED`；真实 Context、Tool、Turn 仍受 D2-C
证据和后续 D/E 审查阻断。

C++ `TurnFinalizedEvent` 是宿主元数据事件，不是既有 Python ExtractionProvider 的内容输入。
后续必须通过单独 `TurnExtractionAdapter` 和受控 resolver 获取正文/Tool Result；该 Adapter
当前未实现，本批次不修改 `memory-service`。

## 明确不负责的内容

- 不修改官方 AI 助手源码
- 不直接操作模型推理
- 不替换官方 SDK 能力

## 目录

```
os-agent-integration/
├── contracts/        # D3-C Qt/C++/JSON 候选契约与示例
├── patches/          # 对上游组件的补丁
├── hooks/            # Hook 实现
├── adapters/         # Tool/Turn 适配器
└── tests/
```

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | 公共值对象、JSON、版本、枚举和错误契约测试通过 |
| **L1** | Hook 与 MemoryClient 联调通过 |
| **L2** | 麒麟 VM 中真实 AI 助手 Hook 调用链路完整 |
