/*
 * fake_sdk_malformed.c
 *
 * 轨道 A — 可控假 SDK .so（P0-2 畸形结果防御测试）
 *
 * 编译为共享库，提供与 libkysdk-coreai-embedding 相同的符号，
 * 但 embed() 返回可配置的畸形结果（由环境变量控制）：
 *   FAKE_MALFORMED=none    → 正常结果（768 维）
 *   FAKE_MALFORMED=null    → text_embedding 返回 true 但 result=NULL
 *   FAKE_MALFORMED=dim0    → result 有效但维度=0
 *   FAKE_MALFORMED=datnull → 维度>0 但 data=NULL
 *   FAKE_MALFORMED=nan     → 数据含 NaN
 *   FAKE_MALFORMED=inf     → 数据含 Inf
 *   FAKE_MALFORMED=embedfalse → text_embedding 返回 false（ERR_EMBED_CALL，P2 补充）
 *
 * 仅用于测试，不进入正式构建。
 */

#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

/* 与 embedding_abi_compat.h 相同的 Opaque 类型（此文件独立编译，不引用头文件） */
typedef struct _TextEmbeddingSession TextEmbeddingSession;
typedef struct _EmbeddingResult EmbeddingResult;

struct _TextEmbeddingSession {
    int dummy;
};

struct _EmbeddingResult {
    int error_code;
    int dimension;
    float* data;
    int mode; /* 0=none, 1=dim0, 2=datnull, 3=nan, 4=inf */
};

static const int kDim = 768;

TextEmbeddingSession* text_embedding_create_session(void) {
    TextEmbeddingSession* s = (TextEmbeddingSession*)calloc(1, sizeof(TextEmbeddingSession));
    return s;
}

void text_embedding_destroy_session(TextEmbeddingSession** s) {
    if (s && *s) {
        free(*s);
        *s = NULL;
    }
}

int text_embedding_init_session(TextEmbeddingSession* s) {
    (void)s;
    /* P1-High: FAKE_MALFORMED=initfail 时返回非零（模拟 init_session 失败） */
    const char* mode = getenv("FAKE_MALFORMED");
    if (mode && strcmp(mode, "initfail") == 0) {
        return -1;
    }
    return 0;
}

void text_embedding_enable_internal_event_loop(TextEmbeddingSession* s, bool on) {
    (void)s;
    (void)on;
}

bool text_embedding(TextEmbeddingSession* s, const char* text, EmbeddingResult** out) {
    (void)s;
    (void)text;
    const char* mode = getenv("FAKE_MALFORMED");
    if (mode && strcmp(mode, "embedfalse") == 0) {
        *out = NULL;
        return false;  /* ERR_EMBED_CALL：调用失败，无结果 */
    }
    if (mode && strcmp(mode, "null") == 0) {
        *out = NULL;
        return true;
    }
    EmbeddingResult* r = (EmbeddingResult*)calloc(1, sizeof(EmbeddingResult));
    if (mode && strcmp(mode, "dim0") == 0) {
        r->dimension = 0;
        r->data = (float*)calloc(1, sizeof(float)); /* 非空但 dim=0 */
        *out = r;
        return true;
    }
    if (mode && strcmp(mode, "datnull") == 0) {
        r->dimension = kDim;
        r->data = NULL;
        *out = r;
        return true;
    }
    if (mode && (strcmp(mode, "nan") == 0 || strcmp(mode, "inf") == 0)) {
        r->dimension = kDim;
        r->data = (float*)calloc((size_t)kDim, sizeof(float));
        float v = (strcmp(mode, "nan") == 0) ? 0.0f / 0.0f : 1.0f / 0.0f;
        for (int i = 0; i < kDim; i++) r->data[i] = v;
        *out = r;
        return true;
    }
    /* 默认：正常 768 维 */
    r->dimension = kDim;
    r->data = (float*)calloc((size_t)kDim, sizeof(float));
    for (int i = 0; i < kDim; i++) r->data[i] = (float)i * 0.001f;
    *out = r;
    return true;
}

float* embedding_result_get_vector_data(EmbeddingResult* r) {
    return r->data;
}

int embedding_result_get_vector_length(EmbeddingResult* r) {
    return r->dimension;
}

int embedding_result_get_error_code(EmbeddingResult* r) {
    return r->error_code;
}

const char* embedding_result_get_error_message(EmbeddingResult* r) {
    (void)r;
    return "fake error";
}

void embedding_result_destroy(EmbeddingResult** r) {
    if (r && *r) {
        if ((*r)->data) free((*r)->data);
        free(*r);
        *r = NULL;
    }
}
