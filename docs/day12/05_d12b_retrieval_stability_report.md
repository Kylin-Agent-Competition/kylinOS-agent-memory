# D12B 检索稳定性与索引一致性报告

> 状态：待独立审查；本报告不代表 PR 已合并，也不以 L1 替代麒麟 VM Runtime 证据。
>
> 基线：`origin/main@a929436f696e11316d221ed5f23cf947ee61b4f7`

## 任务范围与完成定义

台账 D12-B 要求：分析失败查询、删除残留和索引恢复问题；修复性能或过滤错误；回归 FTS5、Vector 与应用层 RRF 全链。完成定义为 B 轨检索与索引的 Critical/High 问题清零，且不新增未经验证的路径。

本批仅修改 B 轨融合层的公共故障信息边界、对应回归测试和 TD-029 登记；不修改 Vector bridge、SQLite 索引账本、D 轨部署或 C 轨客户端。

## 审查、问题与修复

预提交双轴审查发现 `TD-029`：`retrieve_graceful()` 将 Provider 异常原文写入公共 `RetrievalOutcome.degraded_channels`。异常可包含 URI、文件路径或凭据，违反降级诊断的公开边界。

修复后：

- 公共 `degraded_channels` 仅返回稳定错误码 `provider_unavailable`；
- 内部 warning 仅记录通道和异常类型，不写入异常原文；
- 回归覆盖 FTS5/Vector 两通道、URI（含凭据）与路径两类敏感样例；有正常候选时，公共结果、候选 explanation 和日志均断言不包含样例原文。

该修复不改变召回、重排、删除、重建或索引状态的业务语义，只收紧可观察故障信息。

## 验证结果

| 验证 | 结果 | 覆盖范围 |
| --- | ---: | --- |
| `test_retrieve_graceful_redacts_provider_exception_details` | 4 passed | FTS5/Vector × URI/路径；公共结果、候选 explanation、日志脱敏 |
| `tests/retrieval` + `test_d9_retrieval_gold_spec.py` | 384 passed | FTS5、Vector、RRF/weighted-RRF、过滤、SQLite Provider、评测契约 |
| SQLite 删除/重建/重启恢复定向回归 | 9 passed | 精确删除、重放、失败关闭、代次切换、失败保旧、Provider 重启恢复、残留率度量 |
| `py_compile` 与 `git diff --check` | passed | Python 语法与空白检查 |

历史真实 Vector 删除 L2 证据位于 `evidence/l2-kylin-vm/d11b_vm_retrieval_validation_20260901.md`：目标麒麟 VM 的删除运行器 15/15 通过。该证据绑定的是 D11B 的历史提交，且本批未修改 bridge/运行器；不得将它表述为当前 D12B 提交的 L2 验证。

## Critical/High 与未验证边界

截至本报告基线，技术债总账中没有由 B 轨负责且状态为 Open/In Progress 的 Critical/High 检索或索引项。TD-029 已由本批测试关闭。

以下项目保持跨轨依赖或未验证状态，且不在本批伪装为完成：

- `TD-055` 的 `kylin-memory.service` 重启、OS 重启和 C→D→B 端到端检索，依赖 D 轨部署/systemd 与 C 轨真实输入；
- 当前 D12B 提交未在麒麟 VM 执行新的 Runtime 回归；L1 结果不得升级为 L2；
- TD-027、TD-032 至 TD-038、TD-054 仍按总账的责任、Gate 与关闭条件追踪，不因本批过滤修复而改变。

## PR 审查要点与回滚

独立 Reviewer 应确认：异常原文不会跨越公共结果或日志边界；单路故障仍保留另一通道候选；本批不夸大 D11B 历史 L2 为当前 Runtime 证据。

回滚本批提交即可恢复原有公共降级文本；不涉及 SQLite 真源、Vector Collection 或 VM 文件。
