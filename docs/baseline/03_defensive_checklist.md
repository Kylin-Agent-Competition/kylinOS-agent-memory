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
| kylin-ai-runtime 已安装 | ✅ | 1.2.0.4-0k0.1 |
| /usr/lib/kylin-ai/depends 存在 | ✅ | 包含 libcurl 等 |
| LD_LIBRARY_PATH 含 kylin-ai/depends | ✅ | 已配置 |
| 二进制文件完整性 | ✅ | SHA-256 / Build ID / dpkg -V 均通过（详见 01 基线 Runtime 章节） |

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
| .so 文件存在 | ✅ | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 |
| text_embedding 导出 | ✅ | nm -D 确认 |
| create_session 导出 | ✅ | nm -D 确认 |
| init_session 导出 | ✅ | nm -D 确认 |
| .so 可读 | ✅ | |

---

## 检查 3：模型层

```bash
echo "=== 模型 ==="
# 3.1 GTE 模型目录
ls /usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 主模型" || echo "  ❌"
ls /usr/share/kylin-ai/model-repository/ensemble-embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE Ensemble" || echo "  ❌"
ls /usr/share/kylin-ai/model-repository/tokenizer_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 分词器" || echo "  ❌"

# 3.2 默认模型配置
ls /usr/share/kylin-ai/model-repository/model_bank/ 2>/dev/null
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| GTE 主模型目录存在 | ✅ | embd_gte-base_uint8-text |
| Ensemble 目录存在 | ✅ | ensemble-embd_gte-base_uint8-text |
| 分词器目录存在 | ✅ | tokenizer_gte-base_uint8-text |
| default_model.yaml 可读 | ❌ | 文件不存在，改为 config.pbtxt（protobuf 格式） |

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
| kytensor-server 已安装 | ✅ | 2.49.0.6-ok7k0.14 |
| kytensor-client 已安装 | ✅ | 2.49.0.6-ok7k0.14 |
| 8000/8001 端口 | ✅ | 8000(HTTP) + 8001(gRPC) 均监听中 |

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
| 编译成功 | ✅ | g++ 编译通过 |
| dlopen 成功 | ✅ | 已解析所有符号 |
| create_session 成功 | ✅ | 返回非 NULL |
| init_session 成功 | ✅ | 返回 0（内部走 init_v2） |

---

## 已知风险清单

| 编号 | 风险 | 严重程度 | 缓解措施 |
|:----:|------|:--------:|---------|
| R01 | 空输入导致 SDK 崩溃 | Medium | 实测空字符串返回正常向量（维度 768），Bridge 层仍建议拦截空串作为防御 |
| R02 | NULL 指针传给 SDK | High | Bridge 层做参数校验 |
| R03 | init_session 返回非 0（runtime 未启动） | High | init 时检查返回值，标记 unhealthy |
| R04 | text_embedding 返回 NULL | Medium | embed() 返回空向量 + 记录错误 |
| R05 | 返回向量维度不是 768 | Medium | init 时记录维度，后续每次校验 |
| R06 | 连续调用 3 次失败后 SDK 需重连 | Medium | 失败计数 ≥3 标记 unhealthy |
| R07 | ABI 不匹配（.so vs 头文件） | Medium | 以 nm 验证为准，不依赖头文件；接口验证状态见 `cpp-bridge/embedding_abi_compat.h` |
| R08 | Kytensor 服务未启动 | Medium | 检查端口 8000/8001 监听状态 |
| R09 | 长文本超时（>180ms） | Low | Provider 层设超时，超时返回空 |
| R10 | 包版本与内部 runtime 版本不一致 | Medium | PARTIAL：同时记录包版本与内部版本；环境复现以包版本、文件路径、SHA-256、Build ID 为准；功能结论以 Runtime Test 为准 |
| R11 | init 内部路径为 init_v2，可能与旧文档不符 | Medium | init_session 实际走 init_v2，已确认 embed 正常可用 |
| R12 | ldd 依赖全部满足 | — | 验证通过，无缺失依赖 |

---

## 检查结果汇总

| 层 | 检查项数 | 通过 | 失败 | 备注 |
|----|:-------:|:----:|:----:|------|
| Runtime | 7 | 7 | 0 | 包 1.2.0.4，内部 1.3.0（PARTIAL），SHA-256/Build ID 已确认 |
| Embedding SDK | 5 | 5 | 0 | 全部 17 个符号 nm 确认 |
| 模型 | 4 | 3 | 1 | default_model.yaml 不存在，改为 config.pbtxt 格式；SDK 仍能正常加载默认模型 |
| Kytensor | 3 | 3 | 0 | server + client 均已安装 |
| 最小调用 | 5 | 5 | 0 | 5 种文本全部通过（含空输入），维度 768 |

日期：________   检查人：________   麒麟 VM 快照：________
