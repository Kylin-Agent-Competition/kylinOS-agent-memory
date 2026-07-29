# 04 最小 Embedding 调用脚本（已修正 — 使用官方头文件签名）

## 在麒麟 VM 编译运行

```bash
cat > /tmp/embed_correct.cpp << 'CPPEOF'
#include <cstdio>
#include <dlfcn.h>
#include <cstring>

// ============================================================
// 官方 API 声明（来自 gitee embedding.h）
// ============================================================
typedef struct _EmbeddingResult EmbeddingResult;
typedef struct _TextEmbeddingSession TextEmbeddingSession;

// ── 会话 ──
typedef TextEmbeddingSession* (*F_create)();
typedef void (*F_destroy)(TextEmbeddingSession**);
typedef int  (*F_init)(TextEmbeddingSession*);
typedef void (*F_evloop)(TextEmbeddingSession*, bool);

// ── embedding ──
typedef bool (*F_embed)(TextEmbeddingSession*, const char*, EmbeddingResult**);

// ── 结果 ──
typedef float*      (*F_vdata)(EmbeddingResult*);
typedef int         (*F_vlen)(EmbeddingResult*);
typedef int         (*F_errc)(EmbeddingResult*);
typedef const char* (*F_errmsg)(EmbeddingResult*);
typedef void        (*F_freeres)(EmbeddingResult**);

int main() {
    void* h = dlopen("/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1", RTLD_NOW);

    F_create  create  = (F_create) dlsym(h, "text_embedding_create_session");
    F_destroy destroy = (F_destroy)dlsym(h, "text_embedding_destroy_session");
    F_init    init    = (F_init)   dlsym(h, "text_embedding_init_session");
    F_evloop  evloop  = (F_evloop) dlsym(h, "text_embedding_enable_internal_event_loop");
    F_embed   embed   = (F_embed)  dlsym(h, "text_embedding");
    F_vdata   vdata   = (F_vdata)  dlsym(h, "embedding_result_get_vector_data");
    F_vlen    vlen    = (F_vlen)   dlsym(h, "embedding_result_get_vector_length");
    F_errc    errc    = (F_errc)   dlsym(h, "embedding_result_get_error_code");
    F_errmsg  errmsg  = (F_errmsg) dlsym(h, "embedding_result_get_error_message");
    F_freeres freeres = (F_freeres)dlsym(h, "embedding_result_destroy");

    printf("=== Embedding SDK 最小调用（已修正） ===\n\n");

    // 1. 创建会话
    TextEmbeddingSession* s = create();
    if (!s) { printf("❌ create_session 返回 NULL\n"); return 1; }
    printf("✅ 创建会话\n");

    // 2. 初始化
    int r = init(s);
    if (r != 0) { printf("❌ init_session 返回 %d\n", r); return 1; }
    printf("✅ 初始化\n");

    // 3. 开启事件循环
    evloop(s, true);
    printf("✅ 事件循环\n\n");

    // 4. 测试
    struct { const char* text; const char* label; } tests[] = {
        {"你好世界",          "中文"},
        {"Hello world",       "英文"},
        {"我喜欢用表格输出",   "偏好句子"},
        {"A",                 "单字符"},
    };

    for (int i = 0; i < 4; i++) {
        printf("[%d] %s: \"%s\"\n", i+1, tests[i].label, tests[i].text);

        EmbeddingResult* result = nullptr;
        bool ok = embed(s, tests[i].text, &result);

        if (!ok || !result) {
            printf("  ❌ embed 返回 false 或 result 为 NULL\n");
            continue;
        }

        int ec = errc(result);
        if (ec != 0) {
            printf("  ❌ 错误码=%d, 消息=%s\n", ec, errmsg(result));
            freeres(&result);
            continue;
        }

        int dim = vlen(result);
        float* vec = vdata(result);
        printf("  ✅ 维度=%d, 前5值: ", dim);
        for (int j = 0; j < 5 && j < dim; j++) printf("%.4f ", vec[j]);
        printf("...\n");

        freeres(&result);
    }

    // 5. 清理
    destroy(&s);
    dlclose(h);
    printf("\n✅ 完成\n");
    return 0;
}
CPPEOF

g++ -std=c++17 /tmp/embed_correct.cpp -ldl -o /tmp/embed_correct && \
    LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH /tmp/embed_correct
```

## 关键修正

| 函数 | 之前的错误签名 | 正确签名 |
|------|:-----------:|------|
| `text_embedding` | `void* f(session*, char*)` | `bool f(session*, char*, result**)` |
| `embedding_result_destroy` | `void f(result*)` | `void f(result**)` |
| `embedding_result_get_vector_data` | `const float*` | `float*` |
