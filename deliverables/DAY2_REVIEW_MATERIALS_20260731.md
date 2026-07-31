# Day 2 PR 复审材料

## Commit 信息

- **受测 Commit**：`63b899b`（麒麟 VM 实际执行测试时的 Commit）
- **材料创建前 HEAD**：`57a99fd`（本材料撰写时的分支 HEAD）
- **最终 PR HEAD**：以 PR 页面或 `git rev-parse HEAD` 为准

## origin/main...HEAD 文件列表

| 文件 | 状态 |
|------|:----:|
| `docs/day2/05_day2_smoke_test.md` | 新增 |
| `evidence/index.yaml` | 修改 |
| `evidence/l2-kylin-vm/day2_smoke_run.log` | 新增 |
| `evidence/l2-kylin-vm/day2_smoke_test.cpp` | 新增 |

仅 4 个 Day2 专属文件，**无 Day1 重复**。

## 分支清理说明

- 原 `feat/day2-embedding-smoke` 分支重复包含已合并的 Day1 20 个 commit
- 已基于最新 `origin/main` 重建 `feat/day2-embedding-smoke-v2`
- 通过 cherry-pick 保留 Day2 专属 6 个 commit，未强推覆盖他人历史

## 测试源码

`evidence/l2-kylin-vm/day2_smoke_test.cpp`
- 基线：中文短句 / 英文短句 / 单字符
- 空字符串 `""`（TC-0，新增）
- 超长文本（~2170 bytes）
- 纯空白字符串（空格+制表+换行）
- 特殊 Unicode（emoji/CJK 扩展/数学符号）
- 纯数字 / 纯标点 / 混合代码
- 错误模型名（独立调用 `text_embedding_init_model`，新增）
- 重复调用稳定性 ×5

## 编译日志

```
$ g++ -std=c++17 evidence/l2-kylin-vm/day2_smoke_test.cpp -ldl -o /tmp/day2_smoke_v2
→ 编译成功，无错误
```

## Runtime 日志

完整输出见 `evidence/l2-kylin-vm/day2_smoke_run.log`（麒麟 VM 2026-07-31 实测）

## 结果摘要

| 用例 | 结果 |
|------|:----:|
| 中文/英文/单字符 | ✅ dim=768 |
| 空字符串 `""` | ✅ dim=768, L2=1.000000 |
| 超长文本(2170 bytes) | ✅ dim=768, 不截断 |
| 纯空白字符 | ✅ dim=768 |
| 特殊 Unicode | ✅ dim=768 |
| 纯数字/纯标点/混合代码 | ✅ dim=768 |
| **错误模型名** | ✅ errorCode=10, 不崩溃不超时, Session 安全释放, 后续恢复 dim=768 |
| 重复调用 ×5 | ✅ 5 次一致 |
| **总计** | **通过 10 / 失败 0 / EXIT_CODE=0** |

### 错误模型测试 7 项记录

| 检查项 | 结果 |
|--------|:----:|
| 输入模型名 | `this_model_does_not_exist_12345` |
| 函数返回值 | 10 |
| SDK 错误码/信息 | errorCode=10, `Proxy init model failed` |
| 是否崩溃 | 否 |
| 是否超时 | 否 |
| Session 是否安全释放 | 是 |
| 后续正常调用是否恢复 | 是（fallback 默认模型，dim=768） |

## ABI/ldd/nm 证据

- `text_embedding_init_model` 符号已在 `evidence/l2-kylin-vm/embedding_abi_symbols.log` 确认导出
- .so SHA-256: `028e7099...`
- Build ID: `845092235636ed78acc0710fe49bef7c67235253`

## 更新后的 evidence/index.yaml

新增 `EMBED-CALL-002` 条目（schema 1.1 格式）：
- status: HOST_VERIFIED
- commit: `63b899b963bc22bcf048b64e6c7399a37d99cfd9`（真实 commit）
- checksum_sha256: `ef466ec53c300f25bd754f6d814ee5341464a8159737ea6920b00f4d1b7c15e7`

## 已知限制

- 异步接口未覆盖（符号存在但未宿主实测）
- 图像/多模态未覆盖（API 符号多数存在但无可用模型）
- 并发/线程安全未覆盖（需独立测试设计）
- Runtime 重启恢复未覆盖
- 非 x86_64 架构不属于本项目验收范围

## 未测试能力列表

- text_embedding_async 异步路径
- 批量 embed_batch（SDK 无原生批量接口，应用层批处理未实现）
- 多线程并发（单线程已验证，多线程未测）
- Runtime 永久停用场景
- 图像/多模态 embedding
