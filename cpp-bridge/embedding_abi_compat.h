/**
 * embedding_abi_compat.h
 *
 * 最小 ABI 兼容声明 — 仅包含当前麒麟宿主 .so 已确认导出的接口。
 *
 * 状态标记（每个接口一行）：
 *   SOURCE_VERIFIED — 上游头文件有声明
 *   ABI_VERIFIED   — nm -D 确认 .so 已导出符号
 *   HOST_VERIFIED  — 在麒麟虚拟机实测通过
 *   UNTESTED       — 尚未在宿主验证
 *
 * 规则：
 *   1. 只包含 HOST_VERIFIED 或 ABI_VERIFIED 的接口。
 *   2. 未标记 ABI_VERIFIED 的接口不得在此声明。
 *   3. nm -D 仅确认符号存在（T/t 表示代码段导出），
 *      无法确认函数参数列表、返回类型或 C++ mangling 语义。
 *      实际签名以 HOST_VERIFIED 实测调用为准，
 *      未实测的接口以 SOURCE（头文件）为参考但不保证正确。
 */

#ifndef KYLIN_EMBEDDING_ABI_COMPAT_H
#define KYLIN_EMBEDDING_ABI_COMPAT_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── 不透明类型 ── */
typedef struct _EmbeddingResult      EmbeddingResult;      /* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED */
typedef struct _TextEmbeddingSession TextEmbeddingSession; /* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED */
typedef struct _EmbeddingModelList   EmbeddingModelList;   /* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED */
typedef struct _EmbeddingModelInfo   EmbeddingModelInfo;   /* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED */

/* ── 会话管理 ── */

/** 创建 Embedding 会话 */
TextEmbeddingSession* text_embedding_create_session(void);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/** 销毁 Embedding 会话 */
void text_embedding_destroy_session(TextEmbeddingSession** session);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/** 初始化会话（内部走 init_v2 路径） */
int text_embedding_init_session(TextEmbeddingSession* session);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过（返回 0） */

/** 启用内部事件循环 */
void text_embedding_enable_internal_event_loop(TextEmbeddingSession* session, bool enable);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/* ── 同步 Embedding ── */

/** 将文本转为向量 */
bool text_embedding(TextEmbeddingSession* session, const char* text, EmbeddingResult** result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 5 用例实测通过（含空输入） */

/* ── 异步 Embedding ── */

typedef void (*TextEmbeddingResultCallback)(EmbeddingResult* result, void* userdata);

/** 异步 Embedding 调用 */
void text_embedding_async(TextEmbeddingSession* session, const char* text,
                          TextEmbeddingResultCallback callback, void* userdata);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认符号导出，未在宿主实测 */

/* ── 结果读取 ── */

/** 获取向量数据指针 */
float* embedding_result_get_vector_data(EmbeddingResult* result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过（维度 768） */

/** 获取向量维度 */
int embedding_result_get_vector_length(EmbeddingResult* result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过（返回 768） */

/** 获取错误码 */
int embedding_result_get_error_code(EmbeddingResult* result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/** 获取错误消息 */
const char* embedding_result_get_error_message(EmbeddingResult* result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/** 销毁结果对象 */
void embedding_result_destroy(EmbeddingResult** result);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_VERIFIED ✅ nm + 实测通过 */

/* ── 模型管理（HOST_VERIFIED 部分） ── */

/** 显式初始化指定模型 */
int text_embedding_init_model(TextEmbeddingSession* session, const char* model_name);
/* SOURCE_VERIFIED | ABI_VERIFIED | HOST_UNTESTED ⚠️ nm 确认符号存在，参数/返回类型由头文件推断，宿主未完整实测 */

/* ── 模型管理（ABI_VERIFIED 仅 nm 确认） ── */

/** 获取模型列表（原文档标禁调） */
EmbeddingModelList* text_embedding_get_model_list(TextEmbeddingSession* session, int* error_code);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认导出，未在宿主实测 */

/** 获取模型列表数量 */
int embedding_model_list_get_count(EmbeddingModelList* list);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认导出，未在宿主实测 */

/** 获取指定索引的模型信息 */
EmbeddingModelInfo* embedding_model_list_get_model(EmbeddingModelList* list, int index);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认导出，未在宿主实测 */

/** 获取模型名称 */
const char* embedding_model_info_get_model_name(EmbeddingModelInfo* info);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认导出，未在宿主实测 */

/** 获取模型向量维度 */
int embedding_model_info_get_model_dim(EmbeddingModelInfo* info);
/* SOURCE_VERIFIED | ABI_VERIFIED | UNTESTED ⚠️ nm 确认导出，未在宿主实测 */

/* ── nm 额外发现的符号（头文件未收录） ── */

/** 获取模型信息（nm 发现，头文件无声明） */
/* ABI_VERIFIED ⚠️ nm 确认导出，头文件无声明，未在宿主实测 */

#ifdef __cplusplus
}
#endif

#endif /* KYLIN_EMBEDDING_ABI_COMPAT_H */
