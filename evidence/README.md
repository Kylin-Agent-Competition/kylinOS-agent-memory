# Evidence

证据目录，存放 Gate 0–L3 各阶段的验收证据包。

## 目录结构

```
evidence/
├── gate0/              # Gate 0 认证证据
├── l0/                 # L0 测试证据
├── l1/                 # L1 集成测试证据
├── l2-kylin-vm/        # L2 麒麟虚拟机 Runtime 证据
├── l3-clean-snapshot/  # L3 干净快照验收证据
└── release/            # 发布前最终证据
```

## 证据包要求

每个证据包至少记录：

- `task_id` — 关联任务编号
- `commit` — 对应提交哈希
- `os` — 操作系统与架构
- `virtualization` — 虚拟化环境（如 VirtualBox 7.x）
- `command` — 执行的验证命令
- `result` — 命令输出摘要或截图链接
- `reviewer` — 审查人（D/E）
- `limitations` — 已知限制
- `checksum` — 文件校验和（SHA-256）

## 存储策略

- 仓库只放**脱敏、小体积**证据（文本日志、JSON 输出）。
- 大日志、视频、虚拟机快照等大文件放**外部受控存储**，在本目录中保留链接与 SHA-256 校验值。
