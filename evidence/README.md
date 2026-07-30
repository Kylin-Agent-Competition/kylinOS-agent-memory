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

## 索引字段规范

`evidence/index.yaml` 从 Schema `1.1` 起使用统一的证据记录结构。
每条 `entries` 记录必须包含：

- `id` — 仓库内唯一的证据记录 ID；
- `task_id` — 关联的施工任务；
- `description` — 证据用途；
- `status` — 能力或运行结论，例如 `HOST_VERIFIED`、`ABI_VERIFIED`
  或 `BLOCKED`；
- `evidence_level` — 当前最高正向证据等级（E0–E5）；
- `source` — 仓库相对路径形式的主要原始证据；
- `date`、`reviewer`、`limitations`；
- `checksum_sha256` — `source` 文件的 SHA-256。

`status` 与 `evidence_level` 必须分开表达。例如真实宿主调用失败可以是
`status: BLOCKED`，同时以 `evidence_level` 记录失败前已正向验证到的最高
等级；不得把失败日志写成宿主成功证据。

可选字段包括对应代码 `commit`、外部源码 `source_commit`、补充报告
`report`、端到端状态 `runtime_result` 和可审计摘要 `details`。新增字段时
必须先更新 `index_contract`，不得在同一索引中继续引入未声明的字段变体。

## 存储策略

- 仓库只放**脱敏、小体积**证据（文本日志、JSON 输出）。
- 大日志、视频、虚拟机快照等大文件放**外部受控存储**，在本目录中保留链接与 SHA-256 校验值。
