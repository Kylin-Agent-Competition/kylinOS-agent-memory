# 02 麒麟虚拟机实际环境基线（v2 · 2026-08-16 实测）

> **用途**：记录当前麒麟 VM 的真实运行环境，取代旧基线中已过时的组件版本。
> **采集方式**：VirtualBox guestcontrol（VM 名 `Kylin-desktop-neo`）· 用户 `kylin-agent`。
> **采集时间**：2026-08-16。
> **说明**：本文档只陈述实测事实，不做能力结论；旧基线内容仍保留在 `reviewDocuments/` 与 `docs/baseline/01_*.md`、`03_*.md`，本文件是对其的修订与增补。

---

## 1 系统层基线

| 项目 | 实测值 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| 操作系统 | 银河麒麟桌面 V11 2603 x86_64（`KYLIN_RELEASE_ID=2603`，`ID_LIKE=openKylin`） | 同 | — |
| 内核 | `6.6.0-76-generic #86r2-KYLINOS`（2026-08-04 构建） | 6.6.0-63-generic | 升级 |
| Python | 3.12.3 | 文档写 3.10 / 实测 3.12.3 | 以实测为准 |
| g++ / gcc | 12.3.0（openKylin 12.3.0-1ok3k0.1） | 12.3.0 | — |
| systemd | 255（255.2-ok1.9k1.42） | 255 | — |
| cmake | **未安装**（`which cmake` 无结果，退出码 127） | 3.28.3 | 回退（需重新安装） |
| make | /usr/bin/make 可用 | — | — |
| 磁盘 | 93G 总 / 36G 已用 / 53G 可用（41%） | — | — |
| 内存 | 7.7Gi 总 / 4.6Gi 已用 / 3.1Gi 可用 | — | — |
| GPU | NVIDIA driver 无法通信（`nvidia-smi` 失败） | — | 虚拟化环境，GPU 直通不可用 |
| 虚拟化 | VirtualBox（VM `Kylin-desktop-neo`，8GB RAM / 8 CPU） | `kylin-desktop-v11.vhd` | VM 已更换 |
| Guest Additions | 7.2.8 r173730 | — | — |

---

## 2 应用层基线（Kaiming）

| 应用 | 实测版本 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| Kaiming 框架 | `kaiming 1.0.0-ok1k0.106fix0.3.u` | 1.0.0-ok1k0.75 | 升级 |
| **麒灵 AI 助手** `cn.kylin.kylin-aiassistant` | **5.0.3** | 3.0.67 | **大幅升级** |
| — runtime | `stable:top.openkylin.ukui/1.1.43-aipc.7/x86_64` | 1.1.40 | 升级 |
| — base | `stable:top.openkylin.base/1.1.13/x86_64` | — | 新增记录 |
| **记忆地图** `cn.kylin.kylin-ai-memorymap` | **2.0.23** | 不存在 | **新增应用** |
| 麒麟笔记 `cn.kylin.kylin-note` | 1.0.0.1-0k2.188 | — | 新增应用 |
| 语音助手 `voice-assistant` | 随助手包分发（Build ID 5325b0a7…） | — | 新增 |

> 应用安装路径由 `/opt/apps/` 迁移到 `/opt/kaiming/layers/stable/x86_64/app/<id>/binary/<ver>/`。
> 助手主二进制为 `/opt/kaiming/layers/.../5.0.3/files/bin/kylin-aiassistant`（25442632 字节），启动器为 `entries/bin/cn.kylin.kylin-aiassistant`（kaiming run 封装）。

### 2.1 关键二进制 Build ID / SHA-256（实测 readelf -n / sha256sum）

| 二进制 | Build ID | SHA-256 |
| --- | --- | --- |
| kylin-aiassistant（5.0.3 主程序） | `9acaa2de9d94a3d99a2fb510068a31910d47d492` | `6a13dd3aee2f30a963a49f701031df88c03a930d0a9db416b59ee11199874ebd` |
| voice-assistant | `5325b0a7bd2b151f6e7254d2f91183fb3bb6e5d7` | — |
| kylin-ai-runtime（/usr/bin） | `d3201935767c5f4a3a89fc00b7223d8c4770313b` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| kylin-ai-vector-engine（/usr/bin） | `92285a25f3f4e85b354c8192b2cbbc8fe02f5dde` | `c8df2a554453e730392bb9ae43725c6b618eb8a8517aeb7c4364b430e7f3177a` |
| libkysdk-coreai-embedding.so.1.0.0 | `845092235636ed78acc0710fe49bef7c67235253` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| libkyai-assistant.so.1.0.0 | `0ffedd8f74c6cec8d0096c9a924d67104ca9b222` | — |
| libkysdk-vector-engine-client.so.1 | `b39567d054c1d7cbb57ee52c054aa1db32708bfa` | — |
| libggml-base.so（kytensor-llm） | `b582170796fdbe208330376454781b5c88b65e07` | — |

> 对比旧基线：`kylin-ai-runtime` 的 Build ID/SHA-256 与旧基线（01 文档 §AI Runtime）**完全一致**，说明 runtime 二进制未变化，仅周边组件升级。

---

## 3 AI Runtime 与核心库

| 软件包 | 实测版本 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| kylin-ai-runtime | 1.2.0.4-0k0.1 | 1.2.0.4-0k0.1 | — |
| kylin-ai-subsystem（元包） | **1.3.0.1-0k0.1** | 1.2.0.0-0k0.3 | 升级 |
| kylin-ai-subsystem-modelconfig | 1.2.0.1-0k1.1 | — | 新增 |
| kylin-ai-subsystem-plugin | 1.1.0.1-0k1.0 | — | 新增 |
| libkyai-assistant0 | **1.2.0.2-0k0.1** | 无 | 新增（助手核心库） |
| libkyai-config0 | 1.2.0.1-0k0.2 | 无 | 新增 |
| libkyai-business-framework | 1.2.0.0-0k0.6 | 无 | 新增 |
| libkyai-data-management-client | 1.2.0.0-0k0.3 | 无 | 新增 |
| libkyai-depends | 1.2.0.0-0k0.1 | 无 | 新增 |
| libkysdk-ai-common | 1.2.0.2-0k1.0 | 1.2.0.2-0k1.0 | — |

### 3.1 Embedding SDK

| 项目 | 实测值 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| libkylin-coreai-embedding | **1.2.0.0-0k0.4** | 0k0.3 | 升级 |
| .so 文件 | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0`（366624 字节） | 同路径 | — |
| 导出符号 | 新增 `ai_runtime_core_image_embedding_*` 系列、`text_embedding_by_image_model(_async)` | 无 | **新增图像嵌入** |

`nm -D` 确认的 C API（文本侧）：
`text_embedding_create_session`、`text_embedding_init_session`、`text_embedding_init_model`、`text_embedding`、`text_embedding_async`、`text_embedding_get_model_info`、`text_embedding_get_model_list`、`text_embedding_destroy_session`、`text_embedding_by_image_model`、`text_embedding_by_image_model_async`、`embedding_result_get_*`、`embedding_model_list_get_*`、`embedding_model_info_get_*`。

> 相比旧基线（曾记录宿主缺 10 个符号），当前 .so 已导出 `text_embedding_init_model`、`text_embedding_get_model_list` 及图像嵌入系列，说明 ABI 已扩展，需重新做 ABI 兼容声明验证。

### 3.2 Vector Engine

| 项目 | 实测值 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| kylin-ai-vector-engine | **1.2.0.1-0k1.0** | 0k0.11 | 升级 |
| libkysdk-vector-engine-client | 1.2.0.0-0k1.1 | 1.2.0.0-0k1.1 | — |

---

## 4 推理后端（Kytensor / ONNX / LLM）

| 软件包 | 实测版本 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| kytensor-server / client / python | 2.49.0.6-ok7k0.14 | 同 | — |
| **kytensor-llm** | **2.0.0-ok15k0.11** | 无 | **新增（LLaMA 纯 C/C++ 推理，ggml）** |
| **llm-backend** | 1.0.1-ok8k0.2 | 无 | 新增（`/usr/lib/kytensor/backends/llamacpp/libtriton_llamacpp.so`） |
| **gf-arise-llama-ponn** | 02.00.08-1 | 无 | 新增（本地 LLM 推理，`libarisenn.so` 等） |
| onnxruntime-backend | 1.0.1-ok6k0.1 | 同 | — |
| libonnxruntime | **1.20.1+dfsg-ok1.1** | 无 | 新增 |
| libonnx / python3-onnx | 1.16.2-1kylin1 | — | 新增记录 |

> 本地 LLM 引擎配置位于 `/etc/kylin-ai/engines/ai-engines/ondevice/`：`llm_Qwen-2.5-3b_1.0`、`llm_Qwen-3-8b-0_1.0`、`llm_Qwen-3-8b-1_1.0`。`model_bank/default_model.yaml` 中 `llm: llm_Qwen-2.5-3b_1.0` 为默认本地 LLM。

---

## 5 模型仓库

| 模型包 | 实测版本 | 旧基线 | 变化 |
| --- | --- | --- | --- |
| kylin-gte-base-model | 1.0.0.1-0k0.9 | 同 | — |
| kylin-speech-asr-model / -onnx | 1.0.0.0-0k1.0 / 0k0.3 | 无 | 新增 |
| kylin-speech-tts-model / -onnx | 1.0.0.0-0k1.0 / 0k0.1 | 无 | 新增 |
| kylin-sam-model-onnx | 1.0.0.0-0k0.2 | 无 | 新增 |

`/usr/share/kylin-ai/model-repository/` 现含 **30 个目录**，完整清单如下（较旧基线 15 个目录大幅扩充）：

**Embedding**：`embd_gte-base_uint8-text`、`ensemble-embd_gte-base_uint8-text`、`tokenizer_gte-base_uint8-text`、`embd_cn-clip_512-uint8-image`、`embd_cn-clip_512-uint8-text`、`ensemble-embd_cn-clip_512-uint8-text`、`tokenizer_cn-clip_512-uint8-text`

**ASR**：`asr_encoder_streaming`、`asr_encoder_nonstreaming`、`asr_decoder_streaming`、`asr_feature-extractor_streaming`、`asr_feature-extractor_nonstreaming`、`asr_fsmn-vad_streaming`、`asr_lfr-cmvn-pe_streaming`、`asr_scoring_nonstreaming`、`asr_cif-search_streaming`、`ensemble-asr_paraformer_streaming`、`ensemble-asr_paraformer_nonstreaming`、`ensemble-asr_fsmn-vad_streaming`

**TTS**：`tts_melo`、`ensemble-tts_melo`

**视觉**：`ocr_ppocr`、`matting_portrait`、`matting_universal`、`seg_sam`、`seg_sam-encoder`、`seg_sam-decoder`

**标点/其他**：`punc_ct-transformer_nonstreaming`、`ensemble-punc_ct-transformer_nonstreaming`、`model_bank`

> `model_bank/1/` 内含 `default_model.yaml`（默认模型绑定：ocr/llm/matting 等）、`libtriton_model_bank.so`、`modeldevicebinding.json`。

---

## 6 新增业务服务（旧基线完全没有）

| 软件包 | 实测版本 | 二进制/unit |
| --- | --- | --- |
| kylin-ai-knowledge-base-service | 1.2.0.0-0k1.0 | `/usr/bin/kylin-ai-knowledge-base-service`；systemd user unit `kylin-ai-knowledgebase-service.service` |
| kylin-ai-document-qa-service | 1.2.0.0-0k1.0 | — |
| kylin-ai-document-service | 1.2.0.0-0k0.6 | — |
| kylin-ai-parser-extension | 1.2.0.0-0k0.4 | — |
| kylin-ai-python-env | 1.2.0.3-0k0.2 | `/usr/share/kylin-ai-python-env/python-env` |
| kylin-ai-recollect-service | 1.0.0.0-0k1.0 | `/usr/bin/kylin-ai-recollect-service`；systemd user unit `kylin-ai-recollect-service.service` |
| libkylin-ai-recollect-client | 1.0.0.0-0k1.0 | — |
| kylin-ai-abstract-models | 1.2.0.1-0k1.0 | — |
| kylin-ai-engine-plugins（元包） | 1.1.0.1-0k2.1 | — |
| kyai-data-management-service | 1.2.0.0-0k1.10 | — |

> 说明：Recollect 从旧基线的「仅部分依赖」升级为独立的 `kylin-ai-recollect-service` + `libkylin-ai-recollect-client`，说明官方已正式提供用户活动回溯服务；知识库、文档问答、数据管理均为本次新增，需重新纳入能力边界评估。

### 6.1 业务框架配置（`/usr/share/kylin-ai/kyai-business-framework/`）

| 文件 | 关键内容 |
| --- | --- |
| `KnowledgeBase.json` | `support_chunk_count: 30`、`document_chunk_size: 800` |
| `DataManagement.json` | `chunk_size: 512`、`extract_tag_nlp_model_name: llm_Qwen-2.5-3b_1.0`、`extract_tag_nlp_model_deploy_type: OnDevice`、`extract_tag_nums: 6`、`ai_index_task_type: [1,2,3]` |
| `knowledgebaseservice.json` | 知识库服务配置 |

> 关键发现：官方「数据管理」业务服务已用**本地 Qwen-2.5-3b**做标签提取与摘要（OnDevice），说明本地 LLM 推理已进入官方业务链，这与本项目「端侧轻量」目标形成直接参照/竞争关系。

---

## 7 多厂商引擎插件（新增）

引擎配置目录 `/etc/kylin-ai/engines/ai-engines/` 实测包含 **9 个厂商**：`baichuan`、`baidu`、`custom`、`deepseek`、`freetrial`、`ondevice`、`qwen`、`sensetime`、`xunfei`。

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

| 厂商 | ai-engine-plugin | nlp | speech | vision |
| --- | --- | --- | --- | --- |
| baidu | 1.0.0.2-0k0.7 | 1.2.0.2-0k1.0 | 1.2.0.2-0k0.1 | 1.2.0.1-0k0.4 |
| deepseek | 1.1.0.1-0k0.5 | 1.2.0.2-0k1.0 | — | — |
| qwen | 1.1.0.1-0k0.5 | 1.2.0.2-0k1.0 | — | — |
| xunfei | 1.1.0.1-0k0.8 | 1.2.0.2-0k0.3 | 1.2.0.3-0k0.1 | 1.2.0.2-0k0.4 |
| custom | 1.1.0.1-0k0.5 | 1.2.0.3-0k0.1 | — | — |
| freetrial | 1.1.0.0-0k0.7 | 1.2.0.3-0k0.1 | — | — |
| ondevice | 1.2.0.0-0k1.0 | 1.2.0.0-0k1.0 | 1.2.0.0-0k1.0 | 1.2.0.0-0k1.0 |

SDK 库补充：`libkysdk-coreai-speech0 1.2.0.1-0k0.2`、`libkysdk-coreai-vision0 1.2.0.1-0k0.3`、`libkysdk-genai-nlp0 1.2.0.3-0k1.0`、`libkysdk-genai-vision0 1.2.0.1-0k0.2`。

> 每个厂商目录下含 `prompt.json` + `<model>/prompts/`（default-chit-chat、text-polishing、text-summary、file-question-answering、meeting-information-extraction、weekly-report-generation 等），说明 Prompt/Skill 体系已覆盖文档问答、会议信息抽取等场景，需在能力边界中重新评估「官方已有能力」清单。

---

## 8 Runtime Unix Socket

`/tmp/.kylin-ai-runtime-unix/<uid>/` 下实测存在 8 个 socket：

`assistant.sock`、`config.sock`、`core-textembedding.sock`、`core-imageembedding.sock`、`core-speech.sock`、`core-vision.sock`、`genai-nlp.sock`、`genai-vision.sock`。

> 对比旧基线（仅 assistant/config/core-textembedding + 部分），新增 imageembedding、speech、vision、genai-nlp、genai-vision，与第 7 章多模态引擎一致。

---

## 9 服务状态

| 服务 | 状态 |
| --- | --- |
| kytensor.service | active running（8000 HTTP / 8001 gRPC 均监听） |
| ssh | active |
| 麒灵助手 D-Bus | `org.ukui.kylin_aiassistant.service`、`org.ukui.voice_assistant.service` |

---

## 10 与旧基线不一致项（需跟进）

| # | 项目 | 旧基线 | 实测 | 建议 |
| --- | --- | --- | --- | --- |
| 1 | 麒灵助手版本 | 3.0.67 | 5.0.3 | 重新评估 Hook/注入点 |
| 2 | Embedding 包版本 | 0k0.3 | 0k0.4 | 以实测为准 |
| 3 | Vector Engine 服务端 | 0k0.11 | 0k1.0 | 以实测为准 |
| 4 | cmake | 3.28.3 | 未安装 | 需重装后重新采集 |
| 5 | VM 镜像 | kylin-desktop-v11.vhd | Kylin-desktop-neo（kylin-desktop-new.vhd） | 更新快照锚点记录 |
| 6 | 新增记忆地图/知识库/文档/Recollect/多模态 | 无 | 大量新增 | 纳入能力边界文档重新评估 |

---

## 采集人 / 复核

- 采集人：Agent（guestcontrol，用户 kylin-agent）
- 待 Review 确认后冻结为 v2 基线；旧基线内容（`reviewDocuments/`、`docs/baseline/01_*`、`03_*`）保持不变。
