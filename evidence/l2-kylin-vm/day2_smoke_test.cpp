/**
 * day2_smoke_test.cpp
 *
 * Day 2 — Embedding SDK 扩展边界 Smoke Test（完全自包含版本）
 * 不依赖仓库中其他文件，直接在麒麟 VM 编译运行。
 *
 * 在麒麟 VM 终端执行：
 *   g++ -std=c++17 /tmp/day2_smoke_test.cpp -ldl -o /tmp/day2_smoke
 *   LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH /tmp/day2_smoke
 *   echo "EXIT_CODE=$?"
 */

#include <cstdio>
#include <cstring>
#include <cmath>
#include <dlfcn.h>
#include <cstdint>

// ── 不透明类型声明（与 embedding_abi_compat.h 一致） ──
typedef struct _EmbeddingResult      EmbeddingResult;
typedef struct _TextEmbeddingSession TextEmbeddingSession;

// ── dlsym 函数指针类型 ──
typedef TextEmbeddingSession* (*FP_create)();
typedef void (*FP_destroy)(TextEmbeddingSession**);
typedef int  (*FP_init)(TextEmbeddingSession*);
typedef void (*FP_evloop)(TextEmbeddingSession*, bool);
typedef bool (*FP_embed)(TextEmbeddingSession*, const char*, EmbeddingResult**);
typedef float*      (*FP_vdata)(EmbeddingResult*);
typedef int         (*FP_vlen)(EmbeddingResult*);
typedef int         (*FP_errc)(EmbeddingResult*);
typedef const char* (*FP_errmsg)(EmbeddingResult*);
typedef void        (*FP_freeres)(EmbeddingResult**);

// ── 测试用例 ──
struct TestCase {
    const char* label;
    const char* text;
};

static const TestCase cases[] = {
    // 基线对照（与 Day 1 一致）
    { "中文短句",          "你好世界" },
    { "英文短句",          "Hello world" },
    { "单字符",            "A" },

    // ── Day 2 扩展 ──
    { "超长文本(2000字)", nullptr },  // TC-1: 运行时构造
    { "纯空白字符",        "   \t\t\n\n  \t" },                          // TC-2
    { "特殊Unicode",       "Hello \xF0\x9F\x98\x80 你好 \xE2\x88\x91\xE2\x88\xAB\xE2\x88\x9A \xE3\x81\xAE \xE2\x98\x85 \xE4\x90\x80\xF0\xA0\x80\x80" },  // TC-3: emoji, CJK, 数学符号
    { "纯数字",            "1234567890 3.1415926 0x1A2B" },               // TC-4
    { "纯标点",            "!@#$%^&*()_+-=[]{}|;:',.<>?/~`" },            // TC-5
    { "任意文本传参",        "任意字符串输入测试" },                           // TC-6: text_embedding() 不验证文本内容
    { "混合代码",          "int main() { printf(\"hello 世界\\n\"); return 0; }" },  // TC-7
};

static const int NUM_CASES = sizeof(cases) / sizeof(cases[0]);

// 构造超长文本（~2000 字符）
static void build_long_text(char* buf, size_t size) {
    const char* sentence = "麒麟操作系统嵌入式AI能力边界验证测试用例。";
    size_t written = 0;
    while (written < size - strlen(sentence) - 1) {
        size_t n = strlen(sentence);
        memcpy(buf + written, sentence, n);
        written += n;
    }
    buf[written] = '\0';
}

// L2 范数
static double l2_norm(const float* vec, int dim) {
    double sum = 0.0;
    for (int i = 0; i < dim; i++) sum += (double)vec[i] * (double)vec[i];
    return sqrt(sum);
}

int main() {
    void* h = dlopen("/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1", RTLD_NOW);
    if (!h) { fprintf(stderr, "❌ dlopen failed: %s\n", dlerror()); return 1; }

    auto create  = (FP_create) dlsym(h, "text_embedding_create_session");
    auto destroy = (FP_destroy)dlsym(h, "text_embedding_destroy_session");
    auto init    = (FP_init)   dlsym(h, "text_embedding_init_session");
    auto evloop  = (FP_evloop) dlsym(h, "text_embedding_enable_internal_event_loop");
    auto embed   = (FP_embed)  dlsym(h, "text_embedding");
    auto vdata   = (FP_vdata)  dlsym(h, "embedding_result_get_vector_data");
    auto vlen    = (FP_vlen)   dlsym(h, "embedding_result_get_vector_length");
    auto errc    = (FP_errc)   dlsym(h, "embedding_result_get_error_code");
    auto errmsg  = (FP_errmsg) dlsym(h, "embedding_result_get_error_message");
    auto freeres = (FP_freeres)dlsym(h, "embedding_result_destroy");

    if (!create || !init || !evloop || !embed || !vdata || !vlen || !errc || !errmsg || !freeres || !destroy) {
        fprintf(stderr, "❌ dlsym 符号加载失败\n"); return 1;
    }

    TextEmbeddingSession* s = create();
    if (!s) { fprintf(stderr, "❌ create_session 返回 NULL\n"); return 1; }
    printf("✅ 创建会话\n");

    int r = init(s);
    if (r != 0) { fprintf(stderr, "❌ init_session 返回 %d\n", r); return 1; }
    printf("✅ 初始化\n");

    evloop(s, true);
    printf("✅ 事件循环\n\n");

    // 构造超长文本
    char long_buf[2200];
    build_long_text(long_buf, sizeof(long_buf));
    printf("超长文本实际长度: %zu bytes\n", strlen(long_buf));

    int pass = 0, fail = 0, error_expected = 0;
    for (int i = 0; i < NUM_CASES; i++) {
        const char* text = cases[i].text;
        if (!text) text = long_buf;

        printf("\n[%d] %s: ", i + 1, cases[i].label);
        printf("\"%s\"\n", text);

        EmbeddingResult* result = nullptr;
        bool ok = embed(s, text, &result);

        if (!ok || !result) {
            printf("  ❌ embed 返回 false\n"); fail++; continue;
        }

        int ec = errc(result);
        if (ec != 0) {
            printf("  ❌ 错误码=%d, 消息=%s\n", ec, errmsg(result));
            fail++;
            freeres(&result);
            continue;
        }

        int dim = vlen(result);
        const float* vec = vdata(result);
        double norm = l2_norm(vec, dim);
        printf("  ✅ dim=%d, L2=%.6f, 前5值: ", dim, norm);
        for (int j = 0; j < 5 && j < dim; j++) printf("%.4f ", vec[j]);
        printf("...\n");

        bool has_nan = false;
        for (int j = 0; j < dim; j++) {
            if (std::isnan(vec[j]) || std::isinf(vec[j])) { has_nan = true; break; }
        }
        if (has_nan) printf("  ⚠️ 包含 NaN/Inf\n");

        freeres(&result);
        pass++;
    }

    printf("\n═══════════════════════════════\n");

    // ── TC-8: 重复调用稳定性（同一文本连续 5 次） ──
    printf("\n═══════ TC-8: 重复调用稳定性 ═══════\n");
    const char* repeat_text = "麒麟操作系统重复调用稳定性测试。";
    float* prev_vec = nullptr;
    int prev_dim = 0;
    bool deterministic = true;
    for (int k = 0; k < 5; k++) {
        EmbeddingResult* result = nullptr;
        if (!embed(s, repeat_text, &result) || !result) {
            printf("  ❌ 第 %d 次调用失败\n", k + 1);
            deterministic = false; break;
        }
        if (errc(result) != 0) {
            printf("  ❌ 第 %d 次调用 errorCode=%d\n", k + 1, errc(result));
            freeres(&result); deterministic = false; break;
        }
        int dim = vlen(result);
        const float* vec = vdata(result);
        printf("  [%d] dim=%d, L2=%.6f, 前5值: ", k + 1, dim, l2_norm(vec, dim));
        for (int j = 0; j < 5 && j < dim; j++) printf("%.4f ", vec[j]);
        printf("...\n");
        if (k == 0) {
            prev_dim = dim;
            prev_vec = new float[dim];
            memcpy(prev_vec, vec, dim * sizeof(float));
        } else {
            if (dim != prev_dim) deterministic = false;
            else {
                for (int j = 0; j < dim; j++) {
                    if (vec[j] != prev_vec[j]) { deterministic = false; break; }
                }
            }
        }
        freeres(&result);
    }
    delete[] prev_vec;
    printf("  → 确定性: %s\n", deterministic ? "✅ 是 (5 次完全一致)" : "⚠️ 否 (存在差异)");

    destroy(&s);
    dlclose(h);

    printf("\n═══════════ 结果汇总 ═══════════\n");
    printf("  通过:       %d\n", pass);
    printf("  预期错误:   %d\n", error_expected);
    printf("  失败:       %d\n", fail);
    printf("  总计:       %d\n", NUM_CASES);
    printf("═══════════════════════════════\n");

    return (fail > 0) ? 1 : 0;
}
