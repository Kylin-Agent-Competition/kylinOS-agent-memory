# 麒麟 Runtime 知识库版本对照表

> **用途**: Agent 编码时快速确定各仓库源码与 VM 运行环境的对应关系  
> **更新时间**: 2026-08-17（基于环境基线 v2 实测 + memorymap 能力边界定案）  
> **目标环境**: 银河麒麟 V11 2603 x86_64 (VirtualBox，VM `Kylin-desktop-neo`)  

> ⚠️ **版本对照表已更新到新基线 v2**（2026-08-16 实测）。旧基线值见 `docs/baseline/v2-20260816/02_*` 的「旧基线」列。
> 未重新实测源码 Commit 匹配关系的条目，保留旧值并标记「待复核」。

---

## 一、主对照表

| # | 仓库名 (package) | VM 已安装版本 | 基线文档版本 | 本地源码版本 | 本地分支 | 本地 Commit | 匹配 |
|---|---|---|---|---|---|---|---|
| 1 | kylin-ai-runtime | 1.2.0.4-0k0.1 | 1.2.0.4-0k0.1 | 1.1.0.1 | `openkylin/nile-sp2` | c7604d9 | ⚠️ 参考级 |
| 2 | kysdk-ai-common / libkysdk-ai-common | 1.2.0.2-0k1.0 | 1.2.0.2-0k1.0 | 1.1.0.1 | `openkylin/nile-sp2` | 454e412 | ⚠️ 参考级 |
| 3 | kylin-coreai-embedding / libkylin-coreai-embedding | **1.2.0.0-0k0.4** | **1.2.0.0-0k0.4** | 1.2.0.0 | `openkylin/nile-sp2` | 63aed6f3 | ⚠️ 待复核（VM 版本升到 0k0.4） |
| 4 | kylin-ondevice-ai-engine-plugin / libkylin-ondevice-* | 1.2.0.0-0k1.0 | 1.2.0.0-0k1.0 | 1.2.0.0 | `openkylin/nile-sp2` | 748b7d2 | ✅ 匹配级 |
| 5 | libkysdk-vector-engine-client | 1.2.0.0-0k1.1 | 1.2.0.0-0k1.1 | 1.2.0.0 | `openkylin/nile-sp2` | bed675f4 | ✅ 匹配级 |
| 6 | kylin-ai-vector-engine | **1.2.0.1-0k1.0** | **1.2.0.1-0k1.0** | 1.2.0.1 | `openkylin/huanghe` | b95cf43 | ⚠️ 待复核（VM 版本升到 0k1.0） |
| 7 | kylin-aiassistant | **5.0.3 (app)** | **5.0.3** | 3.0.0.0 | `kylin-L3-passed` | cf2ae38 | ❌ 版本跨越（本地源码 3.x，VM 已 5.0.3） |
| 8 | kylin-ai-memorymap | **2.0.23 (app)** | — | — | — | — | ❌ 新增，无本地源码；**已定案：纯 UI 前端（06 报告 §2.4）** |
| 9 | libkyai-assistant / libkyai-assistant0 | **1.2.0.2-0k0.1** | — | — | — | — | ❌ 新增，无本地源码 |

---

## 二、VM 已安装但无公开源码的包

| # | 包名 | VM 版本 | 说明 |
|---|---|---|---|
| 8 | kylin-ai-abstract-models | 1.2.0.1-0k1.0 | 内部 GitLab: `gitlab2.kylin.com/kylinos-src/kylin-ai-abstract-models.git` |
| 9 | kylin-gte-base-model | 1.0.0.1-0k0.9 | Gitee 空仓库，仅有模型文件包 |
| 10 | kytensor-client | 2.49.0.6-ok7k0.14 | 无公开仓库 |
| 11 | kytensor-server | 2.49.0.6-ok7k0.14 | 无公开仓库 |
| 12 | kytensor-python | 2.49.0.6-ok7k0.14 | 无公开仓库 |
| 13 | onnxruntime-backend | 1.0.1-ok6k0.1 | Gitee 空仓库 |
| 14 | kytensor-llm | 2.0.0-ok15k0.11 | 新增，ggml 本地 LLM 推理 |
| 15 | llm-backend | 1.0.1-ok8k0.2 | 新增，kytensor llamacpp backend |
| 16 | gf-arise-llama-ponn | 02.00.08-1 | 新增，本地 LLM 推理 |
| 17 | kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | 新增，官方知识库服务 |
| 18 | kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | 新增，文档问答服务 |
| 19 | kylin-ai-document-service | 1.2.0.0-0k0.6 | 新增，文档服务 |
| 20 | kylin-ai-recollect-service | 1.0.0.0-0k1.0 | 新增；**已定案：memorymap 记忆内核（截图+OCR+CLIP+Milvus+SQLite，06 报告 §2.4）** |
| 21 | kyai-data-management-service | 1.2.0.0-0k1.10 | 新增，数据管理业务服务 |
| 22 | kylin-ai-parser-extension | 1.2.0.0-0k0.4 | 新增 |
| 23 | kylin-ai-python-env | 1.2.0.3-0k0.2 | 新增 |
| 24 | ai-kylin-qwen-plus-cloud-model | 1.0.0.0-0k0.2 | 新增，云模型 |

---

## 三、VM 已安装的全部 AI Runtime 包

| # | 包名 | VM 版本 | 架构 | 源码可用 |
|---|---|---|---|---|
| 1 | kylin-ai-runtime | 1.2.0.4-0k0.1 | amd64 | ⚠️ 1.1.x |
| 2 | libkysdk-ai-common | 1.2.0.2-0k1.0 | amd64 | ⚠️ 1.1.x |
| 3 | libkylin-coreai-embedding | **1.2.0.0-0k0.4** | amd64 | ✅ |
| 4 | libkylin-ondevice-embedding-engine | 1.2.0.0-0k1.0 | amd64 | ✅ |
| 5 | libkylin-ondevice-traditional-ai-engine-plugin | 1.2.0.0-0k1.0 | amd64 | ✅ |
| 6 | kylin-ai-abstract-models | 1.2.0.1-0k1.0 | amd64 | ❌ |
| 7 | kylin-gte-base-model | 1.0.0.1-0k0.9 | all | ❌ |
| 8 | kytensor-client | 2.49.0.6-ok7k0.14 | amd64 | ❌ |
| 9 | kytensor-server | 2.49.0.6-ok7k0.14 | amd64 | ❌ |
| 10 | kytensor-python | 2.49.0.6-ok7k0.14 | amd64 | ❌ |
| 11 | onnxruntime-backend | 1.0.1-ok6k0.1 | amd64 | ❌ |
| 12 | libkysdk-vector-engine-client | 1.2.0.0-0k1.1 | amd64 | ✅ |
| 13 | kylin-ai-vector-engine | **1.2.0.1-0k1.0** | amd64 | ✅ |
| 14 | kylin-ai-subsystem | **1.3.0.1-0k0.1** | amd64 | ✅ (meta) |
| 15 | libkyai-assistant0 | 1.2.0.2-0k0.1 | amd64 | ❌ |
| 16 | libkyai-config0 | 1.2.0.1-0k0.2 | amd64 | ❌ |
| 17 | libkyai-business-framework | 1.2.0.0-0k0.6 | amd64 | ❌ |
| 18 | libkyai-data-management-client | 1.2.0.0-0k0.3 | amd64 | ❌ |
| 19 | kylin-ai-subsystem-modelconfig | 1.2.0.1-0k1.1 | amd64 | ❌ |
| 20 | kylin-ai-subsystem-plugin | 1.1.0.1-0k1.0 | amd64 | ❌ |
| 21 | kytensor-llm | 2.0.0-ok15k0.11 | amd64 | ❌ |
| 22 | llm-backend | 1.0.1-ok8k0.2 | amd64 | ❌ |
| 23 | gf-arise-llama-ponn | 02.00.08-1 | amd64 | ❌ |
| 24 | kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | amd64 | ❌ |
| 25 | kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | amd64 | ❌ |
| 26 | kylin-ai-document-service | 1.2.0.0-0k0.6 | amd64 | ❌ |
| 27 | kylin-ai-recollect-service | 1.0.0.0-0k1.0 | amd64 | ❌ |
| 28 | kylin-ai-parser-extension | 1.2.0.0-0k0.4 | amd64 | ❌ |
| 29 | kylin-ai-python-env | 1.2.0.3-0k0.2 | amd64 | ❌ |
| 30 | kylin-ai-engine-plugins | 1.1.0.1-0k2.1 | amd64 | ❌ (meta) |
| 31 | kyai-data-management-service | 1.2.0.0-0k1.10 | amd64 | ❌ |
| 32 | libonnxruntime | 1.20.1+dfsg-ok1.1 | amd64 | ❌ |

---

## 四、本地仓库速查

| 本地目录 | Gitee 仓库 | 本地分支 | 源码用途 |
|---|---|---|---|
| `kylin-ai-runtime/` | openkylin/kylin-ai-runtime | openkylin/nile-sp2 | 运行时架构、Socket 服务、Embedding 调用链参考 |
| `kysdk-ai-common/` | openkylin/kysdk-ai-common | openkylin/nile-sp2 | 公共 API 头文件、错误码枚举、`is_ai_subsystem_inited()` |
| `kylin-coreai-embedding/` | openkylin/kylin-coreai-embedding | openkylin/nile-sp2 | Embedding SDK C API 头文件 (Commit 精确匹配) |
| `kylin-ondevice-ai-engine-plugin/` | openkylin/kylin-ondevice-ai-engine-plugin | openkylin/nile-sp2 | 本地 Embedding Engine 插件 |
| `libkysdk-vector-engine-client/` | openkylin/libkysdk-vector-engine-client | openkylin/nile-sp2 | Vector Engine C++/gRPC 客户端 (Commit 精确匹配) |
| `kylin-ai-vector-engine/` | openkylin/kylin-ai-vector-engine | openkylin/huanghe | Vector Engine 用户级服务源码 |
| `kylin-aiassistant/` | openkylin/kylin-aiassistant | **kylin-L3-passed** | 麒灵 AI 助手 L3 测试通过版 (v6.0.0-beta, 2603 平台)；**⚠️ VM 已升到 5.0.3，本地源码仍 3.x，需重新拉取对应版本** |
| `kylin-ai-model-manager/` | openkylin/kylin-ai-model-manager | openkylin/nile | ⚠️ 与 VM 的 kylin-ai-abstract-models 是不同仓库 |
| `kylin-ai-subsystem/` | openkylin/kylin-ai-subsystem | openkylin/nile-sp2 | AI 子系统构建脚本与仓库清单 |
| `kylin-gte-base-model/` | openkylin/kylin-gte-base-model | — | ❌ 空仓库 |
| `onnxruntime-backend/` | openkylin/onnxruntime-backend | — | ❌ 空仓库 |

---

## 五、关键路径与接口 (VM 运行时)

### 5.1 kylin-ai-runtime Socket 服务 (Unix Domain Socket)

| Socket 路径 | 用途 |
|---|---|
| `/tmp/.kylin-ai-runtime-unix/<uid>/assistant.sock` | AI 助手服务 |
| `/tmp/.kylin-ai-runtime-unix/<uid>/config.sock` | 配置服务 |
| `/tmp/.kylin-ai-runtime-unix/<uid>/core-textembedding.sock` | 文本 Embedding |
| `/tmp/.kylin-ai-runtime-unix/<uid>/core-imageembedding.sock` | 图像 Embedding |
| `/tmp/.kylin-ai-runtime-unix/<uid>/core-vision.sock` | 视觉服务 |
| `/tmp/.kylin-ai-runtime-unix/<uid>/core-speech.sock` | 语音服务 |
| `/tmp/.kylin-ai-runtime-unix/<uid>/genai-nlp.sock` | GenAI NLP |
| `/tmp/.kylin-ai-runtime-unix/<uid>/genai-vision.sock` | GenAI Vision |

### 5.2 动态库位置

| 库 | 路径 |
|---|---|
| libkysdk-coreai-embedding | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` |
| libkysdk-vector-engine-client | `/usr/lib/x86_64-linux-gnu/libkysdk-vector-engine-client.so.1` |
| libkysdk-ai-common | `/usr/lib/x86_64-linux-gnu/libkysdk-ai-common.so.1` |
| libkyai-assistant | `/usr/lib/x86_64-linux-gnu/libkyai-assistant.so.1.0.0` |
| kylin-ai-runtime depends | `/usr/lib/kylin-ai/depends/libcurl.so.4` |
| kytensor-llm ggml | `/usr/lib/x86_64-linux-gnu/libggml-base.so` 等 |
| llm-backend | `/usr/lib/kytensor/backends/llamacpp/libtriton_llamacpp.so` |

### 5.3 模型与数据路径

| 路径 | 用途 |
|---|---|
| `/usr/share/kylin-ai/model-repository` | 系统模型仓库（30 目录：Embedding/ASR/TTS/视觉/标点） |
| `/opt/appdata/kylin-ai/model-repository` | 应用模型仓库 |
| `/usr/share/kylin-ai-runtime/knowledge-base/` | Runtime 知识库 (SQLite + Vector) |
| `/usr/share/kylin-ai-runtime/intent-recognition/` | 意图识别数据库 |
| `/etc/kylin-ai/engines/ai-engines/` | 多厂商引擎配置（9 厂商 + ondevice 本地 LLM） |
| `/usr/share/kylin-ai/kyai-business-framework/` | 知识库/数据管理业务框架配置 |

### 5.5 本地 LLM 引擎（新增）

| 属性 | 值 |
|---|---|
| 默认本地 LLM | `llm_Qwen-2.5-3b_1.0`（`model_bank/default_model.yaml`） |
| 本地引擎 | Qwen-2.5-3b、Qwen-3-8b-0、Qwen-3-8b-1 |
| 推理后端 | kytensor-llm（ggml）+ gf-arise-llama-ponn + llm-backend |

### 5.4 Kytensor 服务

| 属性 | 值 |
|---|---|
| HTTP 端口 | 127.0.0.1:8000 |
| gRPC 端口 | 127.0.0.1:8001 |
| systemd 服务 | `kytensor.service` |
| 模型控制模式 | explicit |

---

## 六、Agent 使用规则

1. **匹配级仓库**（✅）：源码版本与 VM 二进制一致，可放心作为最终实现参考
2. **参考级仓库**（⚠️）：源码为较低版本 (1.1.x)，但核心接口未变，可用于理解架构和 API 结构，实现时需与 VM 实际 ABI 验证
3. **缺省级包**（❌）：无源码，实现时必须以 VM 二进制 `.so` 的 `nm -D` 导出符号为准
4. 所有结论的最终证据必须是 VM 的实际运行结果，不可用源码推测代替
