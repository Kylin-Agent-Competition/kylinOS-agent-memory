# D6B Collection Schema 与组合过滤最终宿主验证

- 任务：D6B — Collection Schema、用户/场景过滤、异常输入验证与删除门禁
- 结论：`HOST_VERIFIED / E4`
- 日期：2026-08-28
- `tested_commit`：`aef8d52ad602b2e73e0336f7fb0dd0167b4043e6`
- 分支：`feature/d6-b-vector-schema-filter-main`
- 远端校验：`refs/heads/feature/d6-b-vector-schema-filter-main` 与 `tested_commit` 一致
- Review：`PENDING`；`merge_qualified=false`。Runtime 通过不替代独立 Reviewer 审批。

## 环境与构建

在隔离的 VirtualBox 链接克隆 `Kylin-V11-2603-D6B-Test` 中，以干净 checkout 运行；未修改系统包、系统服务或正式 Collection。

- OS：Kylin V11，`Linux 6.6.0-63-generic x86_64`，glibc 2.38
- Vector Engine：`kylin-ai-vector-engine=1.2.0.1-0k0.11`
- Client SDK：`libkysdk-vector-engine-client=1.2.0.0-0k0.7`
- CLI 从该 checkout 的 `tests/vector-engine/vector_bridge_cli.cpp` 以 `g++ -std=c++17 -DKYLIN_VECTOR_LEGACY_0K0_7` 构建并链接系统 `libkysdk-vector-engine-client.so.1`；使用 SDK `0k0.7` 兼容头文件路径。Provider 仅使用测试帐户目录中已有的 Pydantic 依赖，不改系统 Python 包。

## 证据绑定

| 项目 | SHA-256 / 值 |
|---|---|
| CLI binary | `7e6f41aa95e6b0647bf1814e886761803173f234174806626e39e97abd473e50` |
| `vector_bridge_cli.cpp` | `28ca63509d1c4f6af2ef410bf3a9e1a4cb05236e2514e5d6885f1597f3c3b281` |
| CLI L2 runner | `af0949a4ef1f5e9997525d5b8ccb53d5db4881a77e45f1a7377c27ccafacde7b` |
| Provider L2 runner | `e0fe1b69364c47acb103ad9fdc2aac4c987e3dc49627b7cd32b11941c5a713cc` |
| Provider source | `e67f97b919ce1e84a541c39ff0fbc7d188feedb656cf8d60dcfb6ba16b195aee` |
| outer evidence runner | `83bfec9f7a1dfcbcf7b843ac8df84b4eda30333b3bc9649be2fe769ef8694669` |

外层 runner 在执行前确认：工作树 clean、`HEAD == --tested-commit`、当前分支已 checkout，且 `git ls-remote origin refs/heads/<branch>` 精确返回同一 SHA。

## 执行与结果

外层 evidence runner 使用 `--binary /tmp/d6b_final_aef8d52_cli`、`--python /usr/bin/python3`、`--tested-commit aef8d52...` 与 `--collection-prefix d6b_final_aef8d52` 运行。

- 外层 runner：PASS；CLI runner exit code `0`；Provider runner exit code `0`。
- CLI L2：metadata 写入、用户/场景/状态过滤、删除态不可绕过、跨用户隔离、空 user 与未知 filter key fail-closed 全部 PASS。
- D/E 方案 B：`allowed_scene_ids=[] + include_unscoped=false` 为零命中；`[] + true` 仅返回 unscoped `105:v5`，均 PASS。
- Provider L2：typed filter 转发、相同两种空 allowlist 组合、跨用户隔离、inactive 过滤、空向量/维度错误/filter-user 不匹配 fail-closed 全部 PASS；`[] + true` 仅返回 unscoped `205:v5`。
- 两个测试 Collection 均 `cleanup=PASS`。

完整脱敏输出见 [d6b_vector_schema_filter_20260828.log](d6b_vector_schema_filter_20260828.log)。

## 限制

- 仅覆盖一个 Kylin V11 链接克隆与 SDK `0k0.7` ABI 兼容路径。
- 不覆盖并发、性能、重启恢复或 Hybrid/RRF。
- Runtime 证据证明 `tested_commit` 的行为，不代表 PR 已获 Reviewer 批准。
