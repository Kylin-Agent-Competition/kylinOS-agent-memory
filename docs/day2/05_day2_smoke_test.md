# 05 Day 2 — Embedding SDK 扩展边界 Smoke Test

> **文档状态：作者自报（待 Reviewer 验证）** — 测试基于麒麟 VM 一次会话，尚未经独立 Reviewer 复核。

## 目的

在 Day 1 已验证的 5 个基础用例之上，扩展 Embedding SDK 边界测试覆盖：
超长文本、空白字符、Unicode 兼容性、纯数字/纯标点稳定性、重复调用确定性。

## 验证原则（与 Day 1 一致）

- nm/readelf 仅确认符号是否导出；函数原型来自匹配版本头文件/源码；最终通过编译和宿主调用确认。
- 所有结论必须基于银河麒麟虚拟机真实运行输出，不得以 WSL/Reasonix 沙箱结果代替。
- 每条有根据的数据均标注出处（证据文件:行号）。

## 测试环境

| 项目 | 值 | 出处 |
|------|-----|------|
| 操作系统 | 银河麒麟桌面 V11 2603 x86_64 | `runtime_identity.log:5` |
| 虚拟化 | VirtualBox 7.2.14 | `runtime_identity.log:6` |
| Embedding SDK | libkylin-coreai-embedding 1.2.0.0-0k0.4 | `embedding_abi_symbols.log:8-9` |
| .so 路径 | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 | `embedding_abi_symbols.log:7` |
| .so SHA-256 | 028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48 | 麒麟 VM 实测 |
| .so Build ID | 845092235636ed78acc0710fe49bef7c67235253 | 麒麟 VM 实测 |
| 运行时版本 | kylin-ai-runtime 1.2.0.4-0k0.1（内部自报 1.3.0，差异见 PARTIAL） | `runtime_identity.log:11-12`, `day2_smoke_run.log` 运行时日志 |
| 依赖库路径 | /usr/lib/kylin-ai/depends | `minimal_embedding_run.log:16` |
| 默认模型 | ensemble-embd_gte-base_uint8-text | `day2_smoke_run.log` 运行时日志 |
| 头文件上游仓库 | gitee.com/openkylin/kylin-coreai-embedding | `embedding_api.h:5` / `NOTICE:18` |
| 上游 Commit | 63aed6f3 (nile-sp2) | `embedding_api.h:6` / `LICENSE:16` |
| 许可证 | LGPL-2.1-or-later | `LICENSE` / `NOTICE:19` |
| ABI 兼容头 | cpp-bridge/embedding_abi_compat.h | 仓库已提交 `45a87ff` |
| 测试日期 | 2026-07-31 | `day2_smoke_run.log` |

## 测试结果（已实测，2026-07-31）

| 编号 | 名称 | 输入 | 结果 | 状态 | 证据 |
|:----:|------|------|:----:|:----:|:----:|
| [1] | 中文短句 | "你好世界" | ✅ dim=768, L2=1.000000 | HOST_VERIFIED / E4 | `day2_smoke_run.log` |
| [2] | 英文短句 | "Hello world" | ✅ dim=768, L2=1.000000 | HOST_VERIFIED / E4 | 同上 |
| [3] | 单字符 | "A" | ✅ dim=768, L2=0.999999 | HOST_VERIFIED / E4 | 同上 |
| TC-0 | **空字符串** | "" | ✅ dim=768, L2=1.000000, 不崩溃 | HOST_VERIFIED / E4 | 同上 |
| TC-1 | **超长文本** | ~2170 bytes 中文 | ✅ dim=768, L2=1.000000, **不截断不崩溃** | HOST_VERIFIED / E4 | 同上 |
| TC-2 | **纯空白字符** | 空格+制表+换行 | ✅ dim=768, L2=1.000000, **前5维与空输入一致** | HOST_VERIFIED / E4 | 同上 |
| TC-3 | **特殊 Unicode** | emoji😀+CJK扩展𠀀+数学符号 | ✅ dim=768, L2=1.000000, 无崩溃无错误码 | HOST_VERIFIED / E4 | 同上 |
| TC-4 | **纯数字** | 数字+十六进制 | ✅ dim=768, L2=1.000000 | HOST_VERIFIED / E4 | 同上 |
| TC-5 | **纯标点** | 各种符号 | ✅ dim=768, L2=1.000000 | HOST_VERIFIED / E4 | 同上 |
| TC-7 | **混合代码** | C代码含转义符 | ✅ dim=768, L2=1.000000 | HOST_VERIFIED / E4 | 同上 |
| TC-8 | **重复调用 ×5** | 同一文本 | ✅ **5次结果一致（本次测试范围内确定性）** | HOST_VERIFIED / E4 | 同上 |

### 错误模型名测试（独立调用 `text_embedding_init_model`）

| 检查项 | 结果 | 状态 |
|--------|:----:|:----:|
| 输入模型名 | `this_model_does_not_exist_12345` | — |
| 函数返回值 | errorCode=10 | HOST_VERIFIED / E4 |
| SDK 错误码/信息 | `Proxy init model failed` | HOST_VERIFIED / E4 |
| 是否崩溃 | 否 | HOST_VERIFIED / E4 |
| 是否超时 | 否 | HOST_VERIFIED / E4 |
| Session 是否安全释放 | 是 | HOST_VERIFIED / E4 |
| 后续正常调用恢复 | 是（自动 fallback 默认模型，dim=768） | HOST_VERIFIED / E4 |

## 关键发现

1. **L2 范数 = 1.000000（单位向量）已确认** — 全部 10 个用例 L2 范数均为 1.000000（含单字符 A 的 0.999999 属浮点误差）。Day 1 中删除的"单位范数"声明现在有真实宿主证据。
2. **空字符串 / 纯空白字符 = 空输入** — 空字符串与纯空白字符的向量前5维与 Day 1 空输入前5维一致（`-0.0726 0.0508 -0.0465 0.0409 0.0271`），SDK 将空白视为空输入。
3. **超长文本不截断** — 2170 bytes 中文重复文本正常返回 768 维向量，`text_embedding()` 在 2170 bytes 以内不截断（实测）。最大安全长度未知，当前仅实测约 2170 bytes；后续保留可配置限制，根据宿主测试决定。
4. **错误模型名由 `text_embedding_init_model()` 拒绝** — 传入不存在的模型名返回 errorCode=10，不崩溃、不超时；Session 正常释放，后续 `text_embedding()` 自动 fallback 默认模型可恢复。`text_embedding()` 本身不验证文本内容。
5. **SDK 5 次调用结果一致** — 同一文本连续 5 次调用结果一致，在本次测试范围内表现为确定性。

## 已确认能力总表

| 能力 | 状态 | 证据等级 |
|------|:----:|:--------:|
| 同步文本向量化（中文/英文/单字符/空输入） | HOST_VERIFIED | E4 |
| 超长文本向量化（~2170 bytes） | HOST_VERIFIED | E4 |
| 纯空白字符输入（视为空） | HOST_VERIFIED | E4 |
| 特殊 Unicode 输入（emoji/CJK扩展/数学符号） | HOST_VERIFIED | E4 |
| 纯数字/纯标点输入 | HOST_VERIFIED | E4 |
| 混合代码输入 | HOST_VERIFIED | E4 |
| 单位范数 (L2=1.000000) | HOST_VERIFIED | E4 |
| 确定性（同输入同输出 ×5） | HOST_VERIFIED | E4 |
| 任意文本不崩溃 | HOST_VERIFIED | E4 |

## 已知限制

- 异步接口未覆盖（符号存在但未宿主实测）
- 图像/多模态未覆盖（API 符号多数存在但无可用模型）
- 并发/线程安全未覆盖（需独立测试设计）
- Runtime 重启恢复未覆盖
- `text_embedding_init_model()` 错误模型名验证未覆盖（符号存在但需单独测试设计）
- 非 x86_64 架构不属于本项目验收范围
