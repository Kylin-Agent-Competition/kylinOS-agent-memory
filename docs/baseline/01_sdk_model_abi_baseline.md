# 01 SDK / 模型 / ABI 基线清单

## 系统信息

| 项目     | 值                           |
| -------- | ---------------------------- |
| 操作系统 | 银河麒麟桌面 V11 2603 x86_64 |
| 虚拟化   | VirtualBox 7.2.14            |
| Python   | 3.12.3                       |
| GCC      | 12.3.0                       |

## Embedding SDK

| 属性          | 值                                                       |
| ------------- | -------------------------------------------------------- |
| 包名          | libkylin-coreai-embedding                                |
| .so 文件      | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 |
| 版本          | 1.2.0.0-0k0.4                                            |
| 通信          | D-Bus/Unix Socket → kylin-ai-runtime                     |
| 头文件来源    | gitee/openkylin/kylin-coreai-embedding (nile-sp2)        |
| 头文件 commit | 63aed6f3                                                 |
| 本地路径      | embedding_api.h（同目录）                                |

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
| `text_embedding_init_model`                 |  ✅  | 运行时日志提示应调用，传入正确模型名即可 |
| `text_embedding_get_model_list`             |  ✅  | 原文档标禁调，未运行验证                 |

### 内部 C++ 类 (nm -D, mangled)

| 类                            | 关键方法                                                       |
| ----------------------------- | -------------------------------------------------------------- |
| `TextEmbeddingServer`         | getInstance, createProxy, getConnection                        |
| `TextEmbeddingProcessorProxy` | connect, init_v2, initEngine, embeddingText, reconnectAndRetry |
| `_TextEmbeddingSession`       | connect, init, embeddingText, getModelInfo                     |

### ABI 风险

| 风险                                                                 | 缓解                                                                     |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `text_embedding_get_model_info` 等符号 nm 确认存在但头文件未全部收录 | 以 nm 验证为准，头文件列为参考资料                                       |
| init_model 原标禁调，但运行时日志建议调用                            | 传正确模型名（`ensemble-embd_gte-base_uint8-text`）即可，返回 0 表示成功 |
| 包版本(1.2.0.4) vs 内部 runtime(1.3.0) 不一致                        | Bridge 以运行时报告版本为准，初始化时记录 version string                 |
| init_session 实际走 init_v2 内部路径                                 | 已确认 embed 调用正常                                                    |
| Vector Client 与服务端版本耦合                                       | 保持版本栈不变                                                           |

## AI Runtime

| 属性              | 值                                                       |
| ----------------- | -------------------------------------------------------- |
| kylin-ai-runtime  | 1.2.0.4-0k0.1                                            |
| 内部 runtime 版本 | 1.3.0（⚠️ 与包版本不一致）                               |
| 依赖库路径        | /usr/lib/kylin-ai/depends                                |
| LD_LIBRARY_PATH   | 已配置                                                   |
| Unix Socket       | /tmp/.kylin-ai-runtime-unix/1000/core-textembedding.sock |

## GTE 模型

| 属性     | 值                                   |
| -------- | ------------------------------------ |
| 模型包   | kylin-gte-base-model 1.0.0.1-0k0.9   |
| 模型仓库 | /usr/share/kylin-ai/model-repository |
| 默认模型 | ensemble-embd_gte-base_uint8-text    |
| 主模型   | embd_gte-base_uint8-text             |
| 分词器   | tokenizer_gte-base_uint8-text        |

全部模型目录（15 个）：GTE(3) + CN-CLIP(3) + ASR(9) + TTS(1) + Matting(2) + SAM(3) + OCR(1) + Punc(1)

## Kytensor

| 属性 | 值                |
| ---- | ----------------- |
| 版本 | 2.49.0.6-ok7k0.14 |
| HTTP | 127.0.0.1:8000    |
| gRPC | 127.0.0.1:8001    |

## Vector Engine

| 属性   | 值            |
| ------ | ------------- |
| 客户端 | 1.2.0.0-0k1.1 |
| 服务端 | 1.2.0.1-0k1.0 |
