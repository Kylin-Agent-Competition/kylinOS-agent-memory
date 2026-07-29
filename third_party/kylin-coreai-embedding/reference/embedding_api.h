/**
 * embedding_api.h
 *
 * 官方 kylin-coreai-embedding SDK 头文件
 * 来源：gitee.com/openkylin/kylin-coreai-embedding (openkylin/nile-sp2)
 * Commit: 63aed6f3
 */

#ifndef KYLIN_EMBEDDING_API_H
#define KYLIN_EMBEDDING_API_H

#include <stdbool.h>  // bool for C callers inside extern "C"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct _EmbeddingResult EmbeddingResult;
typedef struct _TextEmbeddingSession TextEmbeddingSession;
typedef struct _EmbeddingModelList EmbeddingModelList;
typedef struct _EmbeddingModelInfo EmbeddingModelInfo;

// ── 会话 ──
TextEmbeddingSession *text_embedding_create_session();
void text_embedding_destroy_session(TextEmbeddingSession **session);
int  text_embedding_init_session(TextEmbeddingSession *session);
void text_embedding_enable_internal_event_loop(TextEmbeddingSession *session, bool enable);

// ── 模型 ──
int  text_embedding_init_model(TextEmbeddingSession *session, const char *model_name);
EmbeddingModelList *text_embedding_get_model_list(TextEmbeddingSession *session, int *error_code);
int  embedding_model_list_get_count(EmbeddingModelList *list);
EmbeddingModelInfo *embedding_model_list_get_model(EmbeddingModelList *list, int index);
const char *embedding_model_info_get_model_name(EmbeddingModelInfo *info);
int  embedding_model_info_get_model_dim(EmbeddingModelInfo *info);

// ── Embedding（同步 + 异步）──
bool text_embedding(TextEmbeddingSession *session, const char *text, EmbeddingResult **result);

typedef void (*TextEmbeddingResultCallback)(EmbeddingResult *result, void *userdata);
void text_embedding_async(TextEmbeddingSession *session, const char *text,
                          TextEmbeddingResultCallback callback, void *userdata);

// ── 结果 ──
float *embedding_result_get_vector_data(EmbeddingResult *result);
int   embedding_result_get_vector_length(EmbeddingResult *result);
int   embedding_result_get_error_code(EmbeddingResult *result);
const char *embedding_result_get_error_message(EmbeddingResult *result);
void  embedding_result_destroy(EmbeddingResult **result);

#ifdef __cplusplus
}
#endif
#endif
