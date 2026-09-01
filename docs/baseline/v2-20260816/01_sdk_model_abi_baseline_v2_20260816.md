# 01 SDK / 模型 / ABI 基线清单（v2 · 2026-08-16）

> **版本对照索引（Agent 速查入口）**：`Kylin-runtime-knowledge/VERSION_MAP.md`（2026-08-17，VM 运行时接口版本对照表）；VM 实际版本/ABI 仍以本基线及 L2/L3 evidence 为最终事实依据。
> **版本**：v2，基于 `02_kylin_vm_environment_baseline_20260816.md`（环境基线 v2 实测）与
> `05_capability_boundary_reevaluation_20260816.md`（能力边界重评估 v1.2）更新。
> **证据性质**：本文件为 **ABI / 包 / Schema 级** 结论（nm -D、dpkg、readelf、sha256sum、sqlite .schema、路径探查），
> **未做运行时功能测试**。
> **证据诚实约束**：凡标注「待复测 / 待重新调查」的项，表示旧基线 HOST_VERIFIED 结论因组件版本变化已降级，
> 一律不得在代码或文档中写成「已支持 / 已验证」。
> 旧基线 `docs/baseline/01_sdk_model_abi_baseline.md` 保持不变，本文件是对其的修订与增补。

---

## 系统信息

| 项目     | 值（v2 实测）                         | 旧基线                | 变化     |
| -------- | ------------------------------------- | --------------------- | -------- |
| 操作系统 | 银河麒麟桌面 V11 2603 x86_64          | 同                    | —        |
| 内核     | 6.6.0-76-generic #86r2-KYLINOS        | 6.6.0-63-generic      | 升级     |
| 虚拟化   | VirtualBox（VM `Kylin-desktop-neo`）  | kylin-desktop-v11.vhd | VM 已更换 |
| Python   | 3.12.3                                | 3.12.3                | —        |
| GCC      | 12.3.0                                | 12.3.0                | —        |
| cmake    | **未安装**（`which cmake` 退出码 127） | 3.28.3                | 回退     |

> cmake 缺失直接阻塞 C++ Bridge 编译，最小调用验证前需先重装，并回填本基线。

---

## Embedding SDK

| 属性          | 值                                                           |
| ------------- | ------------------------------------------------------------ |
| 包名          | libkylin-coreai-embedding                                    |
| .so 文件      | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0（366624 字节） |
| 版本          | **1.2.0.0-0k0.4**（旧基线 0k0.3，已升级）                   |
| Build ID      | `845092235636ed78acc0710fe49bef7c67235253`                   |
| SHA-256       | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| 通信          | D-Bus/Unix Socket → kylin-ai-runtime                         |
| 头文件来源    | gitee/openkylin/kylin-coreai-embedding (nile-sp2)            |
| 头文件 commit | 63aed6f3                                                     |
| 本地路径      | `third_party/kylin-coreai-embedding/reference/embedding_api.h` |
| ABI 兼容声明  | `cpp-bridge/embedding_abi_compat.h`（每接口标记验证状态）     |

### 已验证 C API (nm -D)

| 函数                                        | 状态 | 备注                                     |
| ------------------------------------------- | :--: | ---------------------------------------- |
| `text_embedding_create_session`             |  ✅  |                                          |
| `text_embedding_init_session`               |  ✅  |                                          |
| `text_embedding_enable_internal_event_loop` |  ✅  | 头文件有                                 |
| `text_embedding`                            |  ✅  |                                          |
| `text_embedding_async`                      |  ✅  |                                          |
| `text_embedding_destroy_session`            |  ✅  |                                          |
| `text_embedding_get_model_info`             |  ✅  | nm 确认，头文件未包含                    |
| `embedding_result_get_vector_data`          |  ✅  |                                          |
| `embedding_result_get_vector_length`        |  ✅  |                                          |
| `embedding_result_get_error_code`           |  ✅  |                                          |
| `embedding_result_get_error_message`        |  ✅  |                                          |
| `embedding_result_destroy`                  |  ✅  |                                          |
| `embedding_model_list_get_count`            |  ✅  | 头文件有                                 |
| `embedding_model_list_get_model`            |  ✅  | 头文件有                                 |
| `embedding_model_info_get_model_name`       |  ✅  | 头文件有                                 |
| `embedding_model_info_get_model_dim`        |  ✅  | 头文件有                                 |
| `text_embedding_init_model`                 |  ⬜  | nm 确认符号存在（v2 已导出），参数/返回类型由头文件推断，**待运行时验证** |
| `text_embedding_get_model_list`             |  ⬜  | v2 已导出，原标禁调，**待运行时验证**     |
| `text_embedding_by_image_model`             |  ⬜  | **新增（v2）**，图像嵌入同步接口，ABI 已就绪，待运行时验证 |
| `text_embedding_by_image_model_async`       |  ⬜  | **新增（v2）**，图像嵌入异步接口，ABI 已就绪，待运行时验证 |
| `ai_runtime_core_image_embedding_*` 系列    |  ⬜  | **新增（v2）**，图像嵌入底层符号，待运行时验证 |

> 相比旧基线（曾记录宿主缺 10 个符号），当前 .so 已导出 `text_embedding_init_model`、`text_embedding_get_model_list`
> 及图像嵌入系列，ABI 已扩展，需在 `cpp-bridge/embedding_abi_compat.h` 重新做 ABI 兼容声明验证。

### 内部 C++ 类 (nm -D, mangled)

| 类                            | 关键方法                                                       |
| ----------------------------- | -------------------------------------------------------------- |
| `TextEmbeddingServer`         | getInstance, createProxy, getConnection                        |
| `TextEmbeddingProcessorProxy` | connect, init_v2, initEngine, embeddingText, reconnectAndRetry |
| `_TextEmbeddingSession`       | connect, init, embeddingText, getModelInfo                     |

### ABI 风险

| 风险                                                                 | 缓解                                                                     |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `text_embedding_get_model_info` 等符号 nm 确认存在但头文件未全部收录 | nm/readelf 仅确认符号是否导出；函数原型来自匹配版本头文件/源码；最终通过编译和宿主调用确认。接口状态见 `cpp-bridge/embedding_abi_compat.h` |
| `text_embedding_init_model` / `get_model_list` / 图像嵌入系列已导出但未运行时验证 | v2 仅 nm -D 确认符号存在，参数/返回类型由头文件推断，**未做宿主调用实测**；不得标 HOST_VERIFIED |
| Embedding 包 0k0.3 → 0k0.4 升级，旧同步向量化结论（768 维/范数/确定性）需复测 | 以 `05` §2.1 为准：EMB-001 降级「待复测」；EMB-002/EMB-004 上调 ABI_VERIFIED（模型已就位） |
| 包版本(1.2.0.4) vs 内部 runtime(1.3.0) 不一致                        | PARTIAL：同时记录包版本与内部版本；环境复现以包版本、文件路径、SHA-256、Build ID 为准；功能结论以 Runtime Test 为准 |
| init_session 实际走 init_v2 内部路径                                 | 旧基线已确认 embed 调用正常；v2 未重测，需复测确认                       |
| Vector Client 与服务端版本耦合（客户端 0k1.1 未变，服务端 0k0.11→0k1.0） | 保持版本栈不变；服务端升级需重跑 CRUD/持久化回归后再固化结论             |

---

## 麒灵 AI 助手（5.0.3，v2 新增评估对象）

> 旧基线助手为 3.0.67；v2 实测升级至 **5.0.3**，是本次变化最大的组件。以下为 ABI 级结论，运行时语义待复测。

| 属性              | 值                                                           |
| ----------------- | ------------------------------------------------------------ |
| 应用包            | cn.kylin.kylin-aiassistant **5.0.3**（旧 3.0.67，大幅升级）  |
| 安装路径          | /opt/kaiming/layers/stable/x86_64/app/<id>/binary/5.0.3/（自 /opt/apps 迁移） |
| 主二进制          | .../5.0.3/files/bin/kylin-aiassistant（25442632 字节）       |
| Build ID          | `9acaa2de9d94a3d99a2fb510068a31910d47d492`                   |
| SHA-256           | `6a13dd3aee2f30a963a49f701031df88c03a930d0a9db416b59ee11199874ebd` |
| 核心库            | libkyai-assistant0 1.2.0.2-0k0.1（libkyai-assistant.so.1.0.0，Build ID `0ffedd8f74c6cec8d0096c9a924d67104ca9b222`） |

### 聊天核心 ABI（nm -D 确认，5.0.3）

| 符号 | 状态 | 备注 |
| --- | :--: | --- |
| `kyai::assistant::OsAssistant::chatAsync` | ✅ | 已导出，命名空间自旧基线变化 |
| `kyai::assistant::OsAssistant::initWithChatHistory` | ✅ | 已导出 |
| `kyai::assistant::OsAssistant::setChatAsyncCallback` | ✅ | 已导出 |
| `kyai::assistant::OsAssistant::stopChat` | ✅ | 已导出 |
| `kyai::assistant::OsAssistant::clearContext` | ✅ | 已导出 |

> **结论（引用 05 §1）**：聊天核心 ABI 方向延续，但 Build ID、精确源码行、Hook 语义必须在 5.0.3 ELF 上
> 重新取证，不能直接复用 3.0.67 的结论。AGT-001 标 ABI_VERIFIED（需 5.0.3 重新取证 Build ID）；
> AGT-002 普通聊天流式完成、AGT-003 聊天 DB 落库降级「待复测」。

### 聊天数据库 Schema 变化（sqlite .schema 实测，引用 05 §2.3）

| 变化 | 内容 | 评估意义 |
| --- | --- | --- |
| `RECORD` 新增字段 | `chat_type` INT DEFAULT 0 | 区分聊天类型（普通/会议/文档等） |
| `RECORD` 新增字段 | `is_collect` INT DEFAULT 0 | 疑似「收藏/记忆」标记，与记忆相关 |
| `RECORD` 新增字段 | `request_data` TEXT DEFAULT NULL | **潜在模型请求侧数据字段**，可能是原文隔离突破口 |
| `RECORD` 新增字段 | `mode_type` INT DEFAULT 0 | 模式类型 |
| `RECORD` 新增字段 | `session_uuid` VARCHAR(64) | 会话 UUID（区别于 sessionID） |
| `RECORD` 新增字段 | `has_unread` INTEGER | 未读标记 |
| 新增表 | `DOCUMENT_REFERENCE` | 文档问答引用 |
| 新增独立库 | `knowledgebase_database.db`（含 `KNOWLEDGEBASE` 表） | 官方知识库 |

> 聊天 DB 路径仍为 `~/.config/kylin-aiassistant/kylin_aiassistant_database.db`（不变）。
> 旧基线「聊天 Schema 无原始用户文本与模型增强文本分离字段」的结论已被部分推翻：`request_data` 可能承载
> 模型请求侧数据，需进一步验证其是否可用于 Memory Context 注入且不污染 `message` 原文（AGT-005，待重验）。

---

## AI Runtime

| 属性              | 值                                                       |
| ----------------- | -------------------------------------------------------- |
| kylin-ai-runtime  | 1.2.0.4-0k0.1（与旧基线一致，二进制未变化）              |
| 内部 runtime 版本 | 1.3.0（⚠️ 与包版本不一致，见下方 PARTIAL 说明）            |
| kylin-ai-subsystem（元包） | **1.3.0.1-0k0.1**（旧 1.2.0.0-0k0.3，升级）      |
| kylin-ai-subsystem-modelconfig | 1.2.0.1-0k1.1（新增）                       |
| kylin-ai-subsystem-plugin | 1.1.0.1-0k1.0（新增）                            |
| libkyai-assistant0 | 1.2.0.2-0k0.1（新增，助手核心库）                        |
| libkyai-config0    | 1.2.0.1-0k0.2（新增）                                    |
| libkyai-business-framework | 1.2.0.0-0k0.6（新增）                          |
| libkyai-data-management-client | 1.2.0.0-0k0.3（新增）                      |
| libkyai-depends    | 1.2.0.0-0k0.1（新增）                                    |
| libkysdk-ai-common | 1.2.0.2-0k1.0                                          |
| 依赖库路径        | /usr/lib/kylin-ai/depends                                |
| LD_LIBRARY_PATH   | 已配置                                                   |
| Unix Socket       | /tmp/.kylin-ai-runtime-unix/<uid>/（现含 8 个 socket，见下） |
| 二进制路径        | /usr/bin/kylin-ai-runtime                                 |
| SHA-256           | b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225 |
| Build ID          | d3201935767c5f4a3a89fc00b7223d8c4770313b                  |

> **Runtime Unix Socket（8 个，v2 实测）**：`assistant.sock`、`config.sock`、`core-textembedding.sock`、
> `core-imageembedding.sock`、`core-speech.sock`、`core-vision.sock`、`genai-nlp.sock`、`genai-vision.sock`。
> 对比旧基线新增 imageembedding、speech、vision、genai-nlp、genai-vision，与多模态引擎一致。
> `kylin-ai-runtime` 的 Build ID / SHA-256 与旧基线完全一致，说明 runtime 二进制未变化，仅周边组件升级。

---

## 模型仓库

| 属性     | 值                                   |
| -------- | ------------------------------------ |
| 模型包   | kylin-gte-base-model 1.0.0.1-0k0.9   |
| 模型仓库 | /usr/share/kylin-ai/model-repository |
| 目录总数 | **30 个**（旧基线 15 个，大幅扩充）   |
| 默认模型 | ensemble-embd_gte-base_uint8-text    |
| 主模型   | embd_gte-base_uint8-text             |
| 分词器   | tokenizer_gte-base_uint8-text        |

完整目录清单（v2 实测）：

- **Embedding（7）**：`embd_gte-base_uint8-text`、`ensemble-embd_gte-base_uint8-text`、`tokenizer_gte-base_uint8-text`、`embd_cn-clip_512-uint8-image`、`embd_cn-clip_512-uint8-text`、`ensemble-embd_cn-clip_512-uint8-text`、`tokenizer_cn-clip_512-uint8-text`
- **ASR（12）**：`asr_encoder_streaming`、`asr_encoder_nonstreaming`、`asr_decoder_streaming`、`asr_feature-extractor_streaming`、`asr_feature-extractor_nonstreaming`、`asr_fsmn-vad_streaming`、`asr_lfr-cmvn-pe_streaming`、`asr_scoring_nonstreaming`、`asr_cif-search_streaming`、`ensemble-asr_paraformer_streaming`、`ensemble-asr_paraformer_nonstreaming`、`ensemble-asr_fsmn-vad_streaming`
- **TTS（2）**：`tts_melo`、`ensemble-tts_melo`
- **视觉（6）**：`ocr_ppocr`、`matting_portrait`、`matting_universal`、`seg_sam`、`seg_sam-encoder`、`seg_sam-decoder`
- **标点/其他（3）**：`punc_ct-transformer_nonstreaming`、`ensemble-punc_ct-transformer_nonstreaming`、`model_bank`

> `model_bank/1/` 内含 `default_model.yaml`（默认模型绑定：ocr/llm/matting 等）、`libtriton_model_bank.so`、`modeldevicebinding.json`。

---

## Kytensor

| 属性 | 值                |
| ---- | ----------------- |
| 版本 | 2.49.0.6-ok7k0.14 |
| HTTP | 127.0.0.1:8000    |
| gRPC | 127.0.0.1:8001    |

### 推理后端（v2 新增）

| 软件包 | 版本 | 说明 |
| --- | --- | --- |
| kytensor-llm | 2.0.0-ok15k0.11 | LLaMA 纯 C/C++ 推理（ggml），新增 |
| llm-backend | 1.0.1-ok8k0.2 | `/usr/lib/kytensor/backends/llamacpp/libtriton_llamacpp.so`，新增 |
| gf-arise-llama-ponn | 02.00.08-1 | 本地 LLM 推理（libarisenn.so 等），新增 |
| onnxruntime-backend | 1.0.1-ok6k0.1 | 同旧基线 |
| libonnxruntime | 1.20.1+dfsg-ok1.1 | 新增 |

> 本地 LLM 引擎配置位于 `/etc/kylin-ai/engines/ai-engines/ondevice/`：`llm_Qwen-2.5-3b_1.0`、`llm_Qwen-3-8b-0_1.0`、`llm_Qwen-3-8b-1_1.0`。
> `model_bank/default_model.yaml` 中 `llm: llm_Qwen-2.5-3b_1.0` 为默认本地 LLM。

---

## Vector Engine

| 属性   | 值                  |
| ------ | ------------------- |
| 客户端 | 1.2.0.0-0k1.1（未变） |
| 服务端 | **1.2.0.1-0k1.0**（旧 0k0.11，升级） |
| 二进制 | /usr/bin/kylin-ai-vector-engine，Build ID `92285a25f3f4e85b354c8192b2cbbc8fe02f5dde`，SHA-256 `c8df2a554453e730392bb9ae43725c6b618eb8a8517aeb7c4364b430e7f3177a` |
| 客户端库 | libkysdk-vector-engine-client.so.1，Build ID `b39567d054c1d7cbb57ee52c054aa1db32708bfa` |

> 服务端版本升级（0k0.11→0k1.0），VEC-001 CRUD、VEC-002 标量过滤、VEC-003/004 重启持久化/重建均降级「待复测」；
> 客户端 0k1.1 未变，VEC-005 Hybrid/RRF 维持 SOURCE_VERIFIED、VEC-T07 客户端缺陷防御维持 SOURCE_VERIFIED（引用 05 §2.2）。

---

## 新增业务服务（v2，旧基线完全没有）

| 软件包 | 实测版本 | 二进制 / unit |
| --- | --- | --- |
| kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | /usr/bin/kylin-ai-knowledge-base-service；systemd user unit `kylin-ai-knowledgebase-service.service` |
| kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | — |
| kylin-ai-document-service | 1.2.0.0-0k0.6 | — |
| kylin-ai-parser-extension | 1.2.0.0-0k0.4 | — |
| kylin-ai-python-env | 1.2.0.3-0k0.2 | /usr/share/kylin-ai-python-env/python-env |
| kylin-ai-recollect-service | 1.0.0.0-0k1.0 | /usr/bin/kylin-ai-recollect-service；systemd user unit `kylin-ai-recollect-service.service` |
| libkylin-ai-recollect-client | 1.0.0.0-0k1.0 | — |
| kylin-ai-abstract-models | 1.2.0.1-0k1.0 | — |
| kylin-ai-engine-plugins（元包） | 1.1.0.1-0k2.1 | — |
| kyai-data-management-service | 1.2.0.0-0k1.10 | — |

### 与「记忆」直接相关的官方组件（引用 05 §2.4）

| 组件 | 版本 | 与「记忆」的潜在关系 |
| --- | --- | --- |
| kylin-ai-memorymap（记忆地图） | 2.0.23 | **已定案（06 报告 §2.4）**：纯 UI 前端，记忆内核在 recollect-service |
| kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | 官方知识库服务，`KNOWLEDGEBASE` 表已落地 |
| kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | 文档问答（DOCUMENT_REFERENCE 表） |
| kylin-ai-document-service | 1.2.0.0-0k0.6 | 文档解析服务 |
| kylin-ai-parser-extension | 1.2.0.0-0k0.4 | 解析扩展 |
| kyai-data-management-service | 1.2.0.0-0k1.10 | 数据管理业务服务（含 client 0k0.3） |
| kylin-ai-recollect-service | 1.0.0.0-0k1.0 | **已定案（06 报告 §2.4）**：memorymap 记忆内核（截图+OCR+CLIP+Milvus+SQLite） |

> **关键（引用 05 §2.4 + 06 报告 §3.2，2026-08-17 定案）**：memorymap + recollect-service 已定案为「屏幕视觉记忆」
> （纯 UI 前端 + 后台记忆内核），MEM-001 / MEM-002 **维持 NOT_FOUND**，新增 MEM-003（官方视觉记忆组件，
> ABI_VERIFIED，条件数据源）；知识库 / 文档 / 数据管理服务功能边界仍未知，**继续列为 P0 重新调查项**（R-NEW-1）。

### 业务框架配置（`/usr/share/kylin-ai/kyai-business-framework/`）

| 文件 | 关键内容 |
| --- | --- |
| `KnowledgeBase.json` | `support_chunk_count: 30`、`document_chunk_size: 800` |
| `DataManagement.json` | `chunk_size: 512`、`extract_tag_nlp_model_name: llm_Qwen-2.5-3b_1.0`、`extract_tag_nlp_model_deploy_type: OnDevice`、`extract_tag_nums: 6`、`ai_index_task_type: [1,2,3]` |
| `knowledgebaseservice.json` | 知识库服务配置 |

> 官方「数据管理」业务服务已用**本地 Qwen-2.5-3b**做标签提取与摘要（OnDevice），本地 LLM 推理已进入官方业务链，
> 与本项目「端侧轻量」目标形成直接参照/竞争关系。

---

## 多厂商引擎插件（v2 新增）

引擎配置目录 `/etc/kylin-ai/engines/ai-engines/` 实测包含 **9 个厂商**：`baichuan`、`baidu`、`custom`、`deepseek`、
`freetrial`、`ondevice`、`qwen`、`sensetime`、`xunfei`。

| 厂商 | 模型/引擎 | 类型 |
| --- | --- | --- |
| baichuan | baichuan3-turbo | 云 |
| baidu | ernie-4.0-8k | 云 |
| deepseek | deepseek-chat、deepseek-reasoner | 云 |
| qwen | qwen-plus | 云 |
| xunfei | generalv3.5 | 云 |
| sensetime | SenseChat-5 | 云 |
| freetrial | deepseek-r1、deepseek-v3、qwen-max、qwen-plus、qwq-32b | 云（试用） |
| custom | custom（自定义） | 云 |
| ondevice | llm_Qwen-2.5-3b_1.0、llm_Qwen-3-8b-0_1.0、llm_Qwen-3-8b-1_1.0 | **本地** |

> 每个厂商目录下含 `prompt.json` + `<model>/prompts/`（default-chit-chat、text-polishing、text-summary、
> file-question-answering、meeting-information-extraction、weekly-report-generation 等），Prompt/Skill 体系已覆盖
> 文档问答、会议信息抽取等场景，需在能力边界中重新评估「官方已有能力」清单。

---

## 服务状态

| 服务 | 状态 |
| --- | --- |
| kytensor.service | active running（8000 HTTP / 8001 gRPC 均监听） |
| ssh | active |
| 麒灵助手 D-Bus | `org.ukui.kylin_aiassistant.service`、`org.ukui.voice_assistant.service` |

---

## 与旧基线不一致项（需跟进）

| # | 项目 | 旧基线 | 实测 | 建议 |
| --- | --- | --- | --- | --- |
| 1 | 麒灵助手版本 | 3.0.67 | 5.0.3 | 重新评估 Hook/注入点 |
| 2 | Embedding 包版本 | 0k0.3 | 0k0.4 | 以实测为准 |
| 3 | Vector Engine 服务端 | 0k0.11 | 0k1.0 | 以实测为准 |
| 4 | cmake | 3.28.3 | 未安装 | 需重装后重新采集 |
| 5 | VM 镜像 | kylin-desktop-v11.vhd | Kylin-desktop-neo（kylin-desktop-new.vhd） | 更新快照锚点记录 |
| 6 | 新增记忆地图/知识库/文档/Recollect/多模态 | 无 | 大量新增 | 纳入能力边界文档重新评估 |

---

## 证据诚实声明与下一步

本文件所有「✅」仅代表 ABI / 包 / Schema 级确认（符号导出、包安装、字段存在），不代表运行时功能已验证。
所有 HOST_VERIFIED 结论需待麒麟 VM 运行时复测后方可恢复。下一步动作见 `05_capability_boundary_reevaluation_20260816.md` §5。

- 官方记忆能力边界调查（最高优先）
- request_data 字段读写语义实验
- 5.0.3 重新取证（Build ID、libkyai-assistant.so 导入表、Hook 位置、/opt/kaiming/layers 重打包路径）
- Embedding/Vector 版本变化回归
- 重装 cmake 并更新 v2 基线
