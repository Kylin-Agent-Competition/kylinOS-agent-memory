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

**仅建立目录和职责边界，尚无生产实现。**

## 明确不负责的内容

- 不修改官方 AI 助手源码
- 不直接操作模型推理
- 不替换官方 SDK 能力

## 未来主要目录

```
os-agent-integration/
├── patches/          # 对上游组件的补丁
├── hooks/            # Hook 实现
├── adapters/         # Tool/Turn 适配器
└── tests/
```

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | Mock Hook 调用测试 |
| **L1** | Hook 与 MemoryClient 联调通过 |
| **L2** | 麒麟 VM 中真实 AI 助手 Hook 调用链路完整 |
