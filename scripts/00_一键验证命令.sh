# A 轨道 D1 任务 — 验证命令

把下面整段复制到麒麟虚拟机终端，一次性执行全部检查。

```bash
echo "╔══════════════════════════════════════╗"
echo "║  A 轨道 D1 能力基线一键检查          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ==========================================
# 1. Runtime
# ==========================================
echo "━━━ 1. Runtime ━━━"
dpkg -l kylin-ai-runtime | grep "^ii" && echo "  ✅ kylin-ai-runtime" || echo "  ❌ kylin-ai-runtime"
ls /usr/lib/kylin-ai/depends/libcurl* > /dev/null 2>&1 && echo "  ✅ depends" || echo "  ❌ depends"
echo $LD_LIBRARY_PATH | grep kylin-ai > /dev/null && echo "  ✅ LD_LIBRARY_PATH" || echo "  ❌ LD_LIBRARY_PATH"

echo ""
echo "━━━ 2. Embedding SDK ━━━"
ls /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 > /dev/null 2>&1 && echo "  ✅ .so 存在" || echo "  ❌ .so 缺失"
test -r /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 && echo "  ✅ .so 可读" || echo "  ❌ .so 无权限"
echo "  关键符号："
for sym in text_embedding_create_session text_embedding_init_session text_embedding text_embedding_destroy_session embedding_result_get_vector_data embedding_result_get_vector_length; do
    nm -D /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 2>/dev/null | grep "T $sym$" > /dev/null && echo "    ✅ $sym" || echo "    ❌ $sym"
done

echo ""
echo "━━━ 3. 模型 ━━━"
for d in embd_gte-base_uint8-text ensemble-embd_gte-base_uint8-text tokenizer_gte-base_uint8-text; do
    ls /usr/share/kylin-ai/model-repository/$d > /dev/null 2>&1 && echo "  ✅ $d" || echo "  ❌ $d"
done

echo ""
echo "━━━ 4. Kytensor ━━━"
dpkg -l kytensor-server | grep "^ii" && echo "  ✅ kytensor-server" || echo "  ❌"
ss -tlnp 2>/dev/null | grep -q "8000" && echo "  ✅ 端口 8000 监听中" || echo "  ⚠️ 端口 8000 未监听"
ss -tlnp 2>/dev/null | grep -q "8001" && echo "  ✅ 端口 8001 监听中" || echo "  ⚠️ 端口 8001 未监听"

echo ""
echo "━━━ 5. 最小调用 ━━━"
cat > /tmp/embed_check.cpp << 'CPPEOF'
#include <cstdio>
#include <dlfcn.h>
extern "C" { struct S {}; }
int main() {
    void* h = dlopen("/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1", RTLD_NOW);
    if (!h) { printf("  ❌ dlopen 失败: %s\n", dlerror()); return 1; }
    typedef void* (*F1)(); typedef int (*F2)(void*);
    F1 create = (F1)dlsym(h, "text_embedding_create_session");
    F2 init   = (F2)dlsym(h, "text_embedding_init_session");
    if (!create||!init) { printf("  ❌ dlsym\n"); return 1; }
    void* s = create();
    printf("  create_session: %s\n", s?"OK":"NULL");
    if (s) printf("  init_session: %d\n", init(s));
    dlclose(h); return 0;
}
CPPEOF
g++ -std=c++17 /tmp/embed_check.cpp -ldl -o /tmp/embed_check 2>/dev/null && {
    LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH /tmp/embed_check
} || echo "  ⚠️ 编译失败（可能需先装 g++ build-essential）"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  检查完成，请把输出贴给 Reasonix      ║"
echo "╚══════════════════════════════════════╝"
```
