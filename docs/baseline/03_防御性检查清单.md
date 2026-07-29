# 03 防御性检查清单

## 目的

在开发 A 轨道 Bridge 代码之前，确认每一层都可用。按清单逐项检查，记录结果。

---

## 检查 1：Runtime 层

```bash
# 在麒麟 VM 终端执行
echo "=== Runtime 层 ==="
# 1.1 kylin-ai-runtime 是否安装
dpkg -l kylin-ai-runtime | grep "^ii" && echo "  ✅ kylin-ai-runtime" || echo "  ❌"

# 1.2 依赖库是否存在
ls /usr/lib/kylin-ai/depends/libcurl.so* > /dev/null 2>&1 && echo "  ✅ depends" || echo "  ❌"

# 1.3 LD_LIBRARY_PATH 是否配置
echo $LD_LIBRARY_PATH | grep kylin-ai > /dev/null && echo "  ✅ LD_LIBRARY_PATH" || echo "  ❌"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| kylin-ai-runtime 已安装 | | |
| /usr/lib/kylin-ai/depends 存在 | | |
| LD_LIBRARY_PATH 含 kylin-ai/depends | | |

---

## 检查 2：Embedding SDK 层

```bash
echo "=== Embedding SDK ==="
# 2.1 .so 文件是否存在
ls /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 > /dev/null 2>&1 && echo "  ✅ .so" || echo "  ❌"

# 2.2 关键符号是否导出
nm -D /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 2>/dev/null | grep "T text_embedding$" > /dev/null && echo "  ✅ text_embedding" || echo "  ❌"
nm -D /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 2>/dev/null | grep "T text_embedding_create_session" > /dev/null && echo "  ✅ create_session" || echo "  ❌"
nm -D /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 2>/dev/null | grep "T text_embedding_init_session" > /dev/null && echo "  ✅ init_session" || echo "  ❌"

# 2.3 访问权限
test -r /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 && echo "  ✅ 可读" || echo "  ❌"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| .so 文件存在 | | |
| text_embedding 导出 | | |
| create_session 导出 | | |
| init_session 导出 | | |
| .so 可读 | | |

---

## 检查 3：模型层

```bash
echo "=== 模型 ==="
# 3.1 GTE 模型目录
ls /usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 主模型" || echo "  ❌"
ls /usr/share/kylin-ai/model-repository/ensemble-embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE Ensemble" || echo "  ❌"
ls /usr/share/kylin-ai/model-repository/tokenizer_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 分词器" || echo "  ❌"

# 3.2 默认模型配置
cat /usr/share/kylin-ai/model-repository/model_bank/default_model.yaml 2>/dev/null | head -5
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| GTE 主模型目录存在 | | |
| Ensemble 目录存在 | | |
| 分词器目录存在 | | |
| default_model.yaml 可读 | | |

---

## 检查 4：Kytensor 层

```bash
echo "=== Kytensor ==="
# 4.1 是否安装
dpkg -l kytensor-server | grep "^ii" && echo "  ✅ kytensor-server" || echo "  ❌"
dpkg -l kytensor-client | grep "^ii" && echo "  ✅ kytensor-client" || echo "  ❌"

# 4.2 端口是否在监听
ss -tlnp 2>/dev/null | grep -E "8000|8001" || echo "  ⚠️ 端口未监听（可能需手动启动服务）"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| kytensor-server 已安装 | | |
| kytensor-client 已安装 | | |
| 8000/8001 端口 | | 未监听时，运行：`kytensor-server start` |

---

## 检查 5：最小调用验证

```bash
echo "=== 最小调用 ==="
# 5.1 编译测试程序
g++ -std=c++17 -o /tmp/embed_check /dev/stdin \
    -L/usr/lib/x86_64-linux-gnu -lkysdk-coreai-embedding \
    -ldl -lpthread << 'CPPEOF'
#include <cstdio>
extern "C" {
    struct S {}; typedef S* (*T1)(); typedef int (*T2)(S*);
    typedef void* (*T3)(S*,const char*);
}
int main() {
    void* h = dlopen("/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1", RTLD_NOW);
    if (!h) { printf("❌ dlopen 失败\n"); return 1; }
    T1 create = (T1)dlsym(h, "text_embedding_create_session");
    T2 init   = (T2)dlsym(h, "text_embedding_init_session");
    if (!create || !init) { printf("❌ dlsym 失败\n"); return 1; }
    S* s = create();
    if (!s) { printf("❌ create_session 返回 NULL\n"); return 1; }
    int r = init(s);
    printf("init_session 返回 %d\n", r);
    dlclose(h);
    return r;
}
CPPEOF

LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH /tmp/embed_check
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| 编译成功 | | 失败则缺少 build-essential 或 -dev 包 |
| dlopen 成功 | | 失败则 .so 不存在或损坏 |
| create_session 成功 | | 失败则 kylin-ai-runtime 未就绪 |
| init_session 成功 | | 返回 0 表示正常 |

---

## 已知风险清单

| 编号 | 风险 | 严重程度 | 缓解措施 |
|:----:|------|:--------:|---------|
| R01 | 空输入导致 SDK 崩溃 | High | Bridge 层拦截空字符串，不传给 SDK |
| R02 | NULL 指针传给 SDK | High | Bridge 层做参数校验 |
| R03 | init_session 返回非 0（runtime 未启动） | High | init 时检查返回值，标记 unhealthy |
| R04 | text_embedding 返回 NULL | Medium | embed() 返回空向量 + 记录错误 |
| R05 | 返回向量维度不是 768 | Medium | init 时记录维度，后续每次校验 |
| R06 | 连续调用 3 次失败后 SDK 需重连 | Medium | 失败计数 ≥3 标记 unhealthy |
| R07 | ABI 不匹配（.so vs 头文件） | Medium | 以 nm 验证为准，不依赖头文件 |
| R08 | Kytensor 服务未启动 | Medium | 检查端口 8000/8001 监听状态 |
| R09 | 长文本超时（>180ms） | Low | Provider 层设超时，超时返回空 |
| R10 | 龙芯实机 ABI 不同 | Medium | D15 前在龙芯环境验证 |

---

## 检查结果汇总

| 层 | 检查项数 | 通过 | 失败 | 备注 |
|----|:-------:|:----:|:----:|------|
| Runtime | | | | |
| Embedding SDK | | | | |
| 模型 | | | | |
| Kytensor | | | | |
| 最小调用 | | | | |

日期：________   检查人：________   麒麟 VM 快照：________
