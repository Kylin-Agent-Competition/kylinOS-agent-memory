# D6B Collection Schema 与组合过滤宿主验证

- 任务：D6B — Collection Schema、用户/场景过滤、异常输入验证与删除门禁
- 结论：`HOST_VERIFIED / E4`（仅限下表所列未提交工作树）
- 日期：2026-08-26
- 基线：`origin/main` `a06f8badb7f97b81e5828e7b1e33e15fa16ad2ca`
- 被测代码状态：`a493a3fc4ab8240b09d7d59b5fff40eb0684bcff` 之上的**未提交工作树**。本报告不声明 `tested_commit`，不构成合并资格或 Review 结论。

## 范围与运行环境

在隔离的 VirtualBox 链接克隆 `Kylin-V11-2603-D6B-Test` 执行，基础虚拟机未改动。

- OS：Kylin V11，x86_64，kernel `6.6.0-63-generic`
- Vector Engine：`kylin-ai-vector-engine 1.2.0.1-0k0.11`
- Client SDK：`libkysdk-vector-engine-client 1.2.0.0-0k0.7`
- 使用测试帐户目录中的 `0k0.7` ABI 兼容构建脚本；未修改系统包或服务配置。
- 实际调用 `vector_bridge_cli_d6b` 和真实创建/删除 Collection 均成功。当前 KySec 未再显示授权弹窗，表明该测试二进制已有执行许可。

## 被测工作树指纹

| 文件 | SHA-256 |
|---|---|
| `tests/vector-engine/vector_bridge_cli.cpp` | `71aa7f76d720b6473e19ab3f1130067b058ccb8feda3ed12c5c8e773d2af238e` |
| `tests/vector-engine/run_d6_vector_schema_filter_l2.sh` | `54fdd37e34b46e1225d2e2dc97d6559d03198469047ffac3f551fa5f8fdf06bb` |
| `memory-service/retrieval/real_vector_provider.py` | `106d9faaa628ba96bc43e3a2dbe2e8ee7eb1c6f428914b134899ccd4b2264770` |
| `memory-service/tests/retrieval/run_d6_real_vector_provider_l2.py` | `b7d16818ec33042878ed37eefd926eabcf1cab31e39c51d84a1b09feff0d87a2` |
| `~/.local/d6b-sdk/bin/vector_bridge_cli_d6b` | `69035aa20e520889ef604ec3008229582ca31ba9aaba2c6a86d38affafa8d20d` |

## 执行命令与结果

1. `~/.local/d6b-sdk/build_bridge_legacy.sh`：`BRIDGE_LEGACY_BUILD=PASS`。
2. `bash tests/vector-engine/run_d6_vector_schema_filter_l2.sh --binary ~/.local/d6b-sdk/bin/vector_bridge_cli_d6b`：全部通过。覆盖带可过滤元数据写入、用户隔离、场景/未设场景、生命周期、删除不可绕过、空用户拒绝及未知过滤键拒绝。
3. `PYTHONPATH=~/.local/d6b-python python3 tests/retrieval/run_d6_real_vector_provider_l2.py --cli ~/.local/d6b-sdk/bin/vector_bridge_cli_d6b`：全部通过。覆盖 typed filter 转发、跨用户隔离、inactive 过滤、空向量和 filter-user 不匹配的失败关闭。
4. 两个 runner 均使用唯一的 `d6b_` Collection；CLI runner 在退出时清理，Provider runner 明确显示 `cleanup=complete`。

完整的脱敏输出见 [d6b_vector_schema_filter_20260826.log](d6b_vector_schema_filter_20260826.log)。

## 版本语义

`version_id` 作为 Vector 命中元数据返回；当前/陈旧版本的判定仍由 SQLite 真相源在回查阶段完成，D6B 不复制版本真相到 Vector filter。

## 限制与后续门禁

- 这是单一 Kylin 克隆和 SDK `0k0.7` 兼容路径的 E4 证据；不覆盖并发、性能、重启恢复或 Hybrid/RRF。
- 报告绑定工作树内容哈希而非提交；被测文件在提交前若再变更，必须重跑。
- 本机已通过 D6B 相关检索测试组 `205 passed`；完整跨平台测试不作为本项 Windows 验收结论。
- Reviewer：待审；`merge_qualified=false`。技术通过不替代独立 Reviewer 审批。
