# 贡献指南

## 分支策略

- **禁止直接提交 main。**
- 分支按任务建立，不建立永久个人分支。
- 任务完成后分支合并后删除。

### 分支命名规范

```
feat/A-embedding-bridge      # A 轨道功能
feat/B-hybrid-retrieval      # B 轨道功能
feat/C-memory-client         # C 轨道功能
feat/D-memory-gateway        # D 轨道功能
feat/E-preference-domain     # E 轨道功能
fix/<module>-<issue>         # 问题修复
docs/<topic>                 # 文档更新
test/<module>-<scenario>     # 测试补充
```

## Commit 规范

Commit 信息使用中文，前缀仅采用以下类型：

- `feat:` — 新增功能
- `fix:` — 问题修复
- `docs:` — 文档变更
- `test:` — 测试变更
- `refactor:` — 重构
- `chore:` — 构建、CI、工具等杂项

## Review 规则

- 作者不得自审、不得批准自己的代码。
- **D（周子腾）** 与 **E（谢嘉然）** 为指定 Reviewer；作者本人不得作为自己作品的 Reviewer。
- 每个 PR 必须获得至少一位非作者 Reviewer 批准方可合并。

## PR 要求

每个 Pull Request 必须附带：

1. 任务卡引用
2. 修改范围说明
3. 明确不修改的范围
4. L0 测试结果
5. L1（如涉及组件集成）
6. 安全与假实现审查（不得以 Mock 冒充 Runtime Test）
7. L2 麒麟虚拟机证据（如涉及 Runtime）
8. 性能影响评估
9. 已知限制
10. 技术债引用（如有）
11. 回滚方式

### 进度顺序

```
已完成 → 已审查 → 已合并
```

未经审查的 PR 不得合并。

## 静态检查与 Runtime Test

- 静态检查（lint、type-check、bash -n）不得冒充 Runtime Test（L2/L3）。
- L2/L3 必须在银河麒麟虚拟机中执行并附截图/日志证据。
