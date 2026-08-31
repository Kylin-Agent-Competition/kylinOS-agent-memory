# 03 防御性检查清单（v2 · 2026-08-16）

> **版本对照真源**：`Kylin-runtime-knowledge/VERSION_MAP.md`（2026-08-17，VM 运行时接口版本对照表）
> **版本**：v2，基于 `02_kylin_vm_environment_baseline_20260816.md`（环境基线 v2 实测）与
> `05_capability_boundary_reevaluation_20260816.md`（能力边界重评估 v1.2）更新。
> **证据诚实**：本清单为 ABI / 包 / Schema 级检查；旧基线 HOST_VERIFIED 结论因组件版本变化已降级，
> 需在麒麟 VM 上重新跑一遍运行时验证后方可标记通过。
> **关键变化**：Embedding SDK → 1.2.0.0-0k0.4（新增图像嵌入符号）；Vector Engine → 1.2.0.1-0k1.0；
> 助手 → 5.0.3；模型仓库 → 30 目录；cmake **未安装**（检查 5 编译步骤前需先重装）。
> 旧基线 `docs/baseline/03_defensive_checklist.md` 保持不变，本文件是其修订与增补。

## 目的

在开发 A 轨道 Bridge 代码之前，确认每一层都可用。按清单逐项检查，记录结果。
v2 检查重点：确认 Embedding 0k0.4 的图像嵌入符号、模型仓库扩充、以及 cmake 缺失的修复状态。

---

## 检查 0：构建工具链（v2 新增前置项）

```bash
# 在麒麟 VM 终端执行
echo "=== 构建工具链 ==="
# 0.1 cmake 是否安装（v2 实测未安装）
which cmake > /dev/null 2>&1 && cmake --version | head -1 || echo "  ❌ cmake 未安装（v2 实测缺失，需先重装）"

# 0.2 g++ / make 是否可用
g++ --version | head -1
make --version | head -1
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| cmake 已安装 | ❌ | v2 实测 `which cmake` 退出码 127，需重装后再采集 |
| g++ 可用 | ✅ | 12.3.0（openKylin 12.3.0-1ok3k0.1） |
| make 可用 | ✅ | /usr/bin/make |

> **阻塞提示**：检查 5（最小调用验证）依赖 g++ 编译，可直接进行；但 C++ Bridge（CMake 工程）在 cmake 重装前无法编译。

---

## 检查 1：Runtime 层

```bash
# 在麒麟 VM 终端执行
echo "=== Runtime 层 ==="
# 1.1 kylin-ai-runtime 是否安装
dpkg -l kylin-ai-runtime | grep "^ii" && echo "  ✅ kylin-ai-runtime" || echo "  ❌"

# 1.2 kylin-ai-subsystem 元包版本
dpkg -l kylin-ai-subsystem | grep "^ii" | awk '{print "  subsystem:", $3}'

# 1.3 依赖库是否存在
ls /usr/lib/kylin-ai/depends/libcurl.so* > /dev/null 2>&1 && echo "  ✅ depends" || echo "  ❌"

# 1.4 LD_LIBRARY_PATH 是否配置
echo $LD_LIBRARY_PATH | grep kylin-ai > /dev/null && echo "  ✅ LD_LIBRARY_PATH" || echo "  ❌"

# 1.5 Runtime 二进制完整性（SHA-256 / Build ID）
sha256sum /usr/bin/kylin-ai-runtime
readelf -n /usr/bin/kylin-ai-runtime | grep "Build ID"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| kylin-ai-runtime 已安装 | ✅ | 1.2.0.4-0k0.1（二进制与旧基线一致，未变化） |
| kylin-ai-subsystem 元包 | ⚠️ | 1.3.0.1-0k0.1（旧 1.2.0.0-0k0.3，已升级） |
| /usr/lib/kylin-ai/depends 存在 | ✅ | 包含 libcurl 等 |
| LD_LIBRARY_PATH 含 kylin-ai/depends | ✅ | 已配置 |
| 二进制文件完整性 | ✅ | SHA-256 / Build ID 与旧基线完全一致（详见 01 v2 基线 Runtime 章节） |
| Unix Socket 数量 | ⚠️ | v2 实测 8 个（新增 imageembedding/speech/vision/genai-nlp/genai-vision） |

---

## 检查 2：Embedding SDK 层

```bash
echo "=== Embedding SDK ==="
SO=/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0

# 2.1 .so 文件是否存在
ls $SO > /dev/null 2>&1 && echo "  ✅ .so" || echo "  ❌"

# 2.2 关键文本符号是否导出
nm -D $SO 2>/dev/null | grep "T text_embedding$" > /dev/null && echo "  ✅ text_embedding" || echo "  ❌"
nm -D $SO 2>/dev/null | grep "T text_embedding_create_session" > /dev/null && echo "  ✅ create_session" || echo "  ❌"
nm -D $SO 2>/dev/null | grep "T text_embedding_init_session" > /dev/null && echo "  ✅ init_session" || echo "  ❌"

# 2.3 新增符号（v2：模型列表/图像嵌入）
nm -D $SO 2>/dev/null | grep "T text_embedding_init_model" > /dev/null && echo "  ✅ init_model（v2 已导出）" || echo "  ❌"
nm -D $SO 2>/dev/null | grep "T text_embedding_get_model_list" > /dev/null && echo "  ✅ get_model_list（v2 已导出）" || echo "  ❌"
nm -D $SO 2>/dev/null | grep "T text_embedding_by_image_model$" > /dev/null && echo "  ✅ by_image_model（v2 新增）" || echo "  ❌"
nm -D $SO 2>/dev/null | grep "ai_runtime_core_image_embedding" > /dev/null && echo "  ✅ image_embedding 系列（v2 新增）" || echo "  ❌"

# 2.4 版本确认
dpkg -l libkylin-coreai-embedding | grep "^ii" | awk '{print "  版本:", $3}'

# 2.5 访问权限
test -r $SO && echo "  ✅ 可读" || echo "  ❌"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| .so 文件存在 | ✅ | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0（366624 字节） |
| text_embedding 导出 | ✅ | nm -D 确认 |
| create_session 导出 | ✅ | nm -D 确认 |
| init_session 导出 | ✅ | nm -D 确认 |
| init_model 导出 | ⬜ | v2 已导出（旧基线曾记录宿主缺），参数/返回类型待头文件推断，**待运行时验证** |
| get_model_list 导出 | ⬜ | v2 已导出，原标禁调，**待运行时验证** |
| by_image_model 导出 | ⬜ | **v2 新增**，图像嵌入同步接口，ABI 已就绪，待运行时验证 |
| image_embedding 系列导出 | ⬜ | **v2 新增**，底层图像嵌入符号，待运行时验证 |
| 包版本 | ✅ | 1.2.0.0-0k0.4（旧 0k0.3，已升级） |
| .so 可读 | ✅ | |

---

## 检查 3：模型层

```bash
echo "=== 模型 ==="
REPO=/usr/share/kylin-ai/model-repository

# 3.1 目录总数（v2 实测 30 个）
ls -d $REPO/*/ 2>/dev/null | wc -l

# 3.2 GTE 文本模型目录
ls $REPO/embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 主模型" || echo "  ❌"
ls $REPO/ensemble-embd_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE Ensemble" || echo "  ❌"
ls $REPO/tokenizer_gte-base_uint8-text > /dev/null 2>&1 && echo "  ✅ GTE 分词器" || echo "  ❌"

# 3.3 图像嵌入模型（v2 新增：CN-CLIP / SAM）
ls $REPO/embd_cn-clip_512-uint8-image > /dev/null 2>&1 && echo "  ✅ CN-CLIP 图像" || echo "  ❌"
ls $REPO/embd_cn-clip_512-uint8-text > /dev/null 2>&1 && echo "  ✅ CN-CLIP 文本" || echo "  ❌"
ls $REPO/seg_sam > /dev/null 2>&1 && echo "  ✅ SAM" || echo "  ❌"

# 3.4 默认模型配置
ls $REPO/model_bank/1/default_model.yaml 2>/dev/null && echo "  ✅ default_model.yaml" || echo "  ❌"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| 模型目录总数 | ✅ | 30 个（旧基线 15 个，大幅扩充） |
| GTE 主模型目录存在 | ✅ | embd_gte-base_uint8-text |
| Ensemble 目录存在 | ✅ | ensemble-embd_gte-base_uint8-text |
| 分词器目录存在 | ✅ | tokenizer_gte-base_uint8-text |
| CN-CLIP 图像/文本模型 | ⬜ | v2 新增（embd_cn-clip_512-uint8-image/text），配合图像嵌入符号，待运行时验证 |
| SAM 模型 | ⬜ | v2 新增（seg_sam / seg_sam-encoder / seg_sam-decoder） |
| default_model.yaml 存在 | ✅ | v2 实测 `model_bank/1/default_model.yaml`（旧基线标不存在，现已修复） |

---

## 检查 4：Kytensor 层

```bash
echo "=== Kytensor ==="
# 4.1 是否安装
dpkg -l kytensor-server | grep "^ii" && echo "  ✅ kytensor-server" || echo "  ❌"
dpkg -l kytensor-client | grep "^ii" && echo "  ✅ kytensor-client" || echo "  ❌"

# 4.2 本地 LLM（v2 新增）
dpkg -l kytensor-llm | grep "^ii" && echo "  ✅ kytensor-llm" || echo "  ❌"
dpkg -l llm-backend | grep "^ii" && echo "  ✅ llm-backend" || echo "  ❌"

# 4.3 端口是否在监听
ss -tlnp 2>/dev/null | grep -E "8000|8001" || echo "  ⚠️ 端口未监听（可能需手动启动服务）"
```

| 检查项 | 状态 | 备注 |
|--------|:----:|------|
| kytensor-server 已安装 | ✅ | 2.49.0.6-ok7k0.14 |
| kytensor-client 已安装 | ✅ | 2.49.0.6-ok7k0.14 |
| kytensor-llm 已安装 | ⬜ | v2 新增（2.0.0-ok15k0.11，LLaMA ggml 推理），待运行时验证 |
| llm-backend 已安装 | ⬜ | v2 新增（1.0.1-ok8k0.2），待运行时验证 |
| 8000/8001 端口 | ✅ | 8000(HTTP) + 8001(gRPC) 均监听中 |

---

## 检查 5：最小调用验证

> ⚠️ **v2 前置**：cmake 未安装。本检查用 g++ 直接编译（不依赖 cmake），可先行；C++ Bridge CMake 工程需先重装 cmake。

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
    void* h = dlopen("/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0", RTLD_NOW);
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
| 编译成功 | ⬜ | g++ 编译待 v2 复测（cmake 缺失不影响，但需在 v2 快照重跑） |
| dlopen 成功 | ⬜ | 待复测（.so 已升级到 0k0.4） |
| create_session 成功 | ⬜ | 待复测 |
| init_session 成功 | ⬜ | 待复测（旧基线返回 0，内部走 init_v2） |

> 以上 4 项为旧基线 HOST_VERIFIED，因 Embedding 包 0k0.3→0k0.4 升级，一律降级「待复测」，需在 v2 快照重跑确认。

---

## 已知风险清单

| 编号 | 风险 | 严重程度 | 缓解措施 |
|:----:|------|:--------:|---------|
| R01 | 空输入导致 SDK 崩溃 | Medium | 旧基线实测空字符串返回正常向量（768 维）；0k0.4 升级后需复测；Bridge 层仍建议拦截空串作为防御 |
| R02 | NULL 指针传给 SDK | High | Bridge 层做参数校验 |
| R03 | init_session 返回非 0（runtime 未启动） | High | init 时检查返回值，标记 unhealthy |
| R04 | text_embedding 返回 NULL | Medium | embed() 返回空向量 + 记录错误 |
| R05 | 返回向量维度不是 768 | Medium | init 时记录维度，后续每次校验；0k0.4 升级后维度需复测确认 |
| R06 | 连续调用 3 次失败后 SDK 需重连 | Medium | 失败计数 ≥3 标记 unhealthy |
| R07 | ABI 不匹配（.so vs 头文件） | Medium | nm/readelf 仅确认符号是否导出；函数原型来自匹配版本头文件/源码；最终通过编译和宿主调用确认。接口状态见 `cpp-bridge/embedding_abi_compat.h` |
| R08 | Kytensor 服务未启动 | Medium | 检查端口 8000/8001 监听状态 |
| R09 | 长文本超时（>180ms） | Low | Provider 层设超时，超时返回空 |
| R10 | 包版本与内部 runtime 版本不一致 | Medium | PARTIAL：同时记录包版本与内部版本；环境复现以包版本、文件路径、SHA-256、Build ID 为准；功能结论以 Runtime Test 为准 |
| R11 | init 内部路径为 init_v2，可能与旧文档不符 | Medium | init_session 实际走 init_v2；v2 未重测，需复测确认 embed 正常 |
| R12 | ldd 依赖全部满足 | — | 旧基线验证通过；0k0.4 升级后需重跑 ldd 确认 |
| R13 | 图像嵌入符号已导出但头文件/运行时语义未验证 | Medium | by_image_model / image_embedding 系列仅 nm 确认；不得标 HOST_VERIFIED，纳入 Provider 扩展边界（不阻塞主链） |
| R14 | cmake 未安装导致 C++ Bridge 无法编译 | High | 重装 cmake 后重新采集基线；检查 0 前置 |
| R15 | Vector Engine 服务端 0k0.11→0k1.0，CRUD/持久化结论失效 | High | 重跑 CRUD/持久化/精准遗忘回归后再固化结论 |
| R16 | 助手 5.0.3 与旧基线 Hook/DB Schema 结论不一致 | High | RECORD 表新增 6 字段、DOCUMENT_REFERENCE 表、knowledgebase_database.db；request_data 字段语义需优先实验（引用 05 §2.3） |
| R17 | 官方记忆能力（memorymap/知识库/数据管理）边界未知 | High | P0 立即调查官方记忆组件功能边界，重写 01 §9（引用 05 §4） |

---

## 检查结果汇总

| 层 | 检查项数 | 通过 | 待复测 | 失败 | 备注 |
|----|:-------:|:----:|:-----:|:----:|------|
| 构建工具链 | 3 | 2 | 0 | 1 | cmake 未安装（v2 实测缺失） |
| Runtime | 6 | 5 | 1 | 0 | runtime 二进制未变；subsystem 元包升级 1.3.0.1；socket 扩至 8 个 |
| Embedding SDK | 10 | 6 | 4 | 0 | 0k0.4；新增图像嵌入符号（待运行时验证） |
| 模型 | 8 | 5 | 3 | 0 | 30 目录；CN-CLIP/SAM 新增；default_model.yaml 已存在 |
| Kytensor | 5 | 3 | 2 | 0 | 新增 kytensor-llm / llm-backend（待验证） |
| 最小调用 | 4 | 0 | 4 | 0 | 旧基线 HOST_VERIFIED，0k0.4 升级后待复测 |

> 汇总口径：本表「通过」仅代表 ABI/包/Schema 级确认，「待复测」代表旧基线运行时结论因版本变化降级，
> 需在麒麟 VM 重新跑运行时验证后方可标记通过。最终运行时结论以 L2/L3 实测证据为准。

日期：________   检查人：________   麒麟 VM 快照：________
