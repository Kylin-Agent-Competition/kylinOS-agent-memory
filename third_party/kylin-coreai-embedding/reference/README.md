# kylin-coreai-embedding — 官方 SDK 头文件（参考副本）

## 来源

| 属性 | 值 |
|------|-----|
| 上游仓库 | gitee.com/openkylin/kylin-coreai-embedding |
| 分支 | openkylin/nile-sp2 |
| Commit | 63aed6f3 |
| 原始路径 | `embedding/kylin_embedding_api.h` |
| 许可证 | 上游仓库许可证（LGPL-2.1+） |

## 用途

仅用作参考，便于离线查阅官方 API 签名与数据结构。

**⚠️ 头文件声明不等同于当前宿主 ABI。** Bridge 实现必须依赖宿主 `.so` 实际导出的符号（`nm -D` 确认），不得因头文件中存在声明而直接链接。宿主角度的已验证接口见 `cpp-bridge/embedding_abi_compat.h`。

**🚫 正式构建禁止引用此头文件。** 生产代码（C++ Bridge、pybind11 封装、Provider 层）必须使用 `cpp-bridge/embedding_abi_compat.h`。任何直接 `#include` 此参考副本的代码将不予合并。

## 更新说明

上游仓库更新时，如需同步此副本，请：

1. 对比新版本与当前宿主 `.so` 的符号差异
2. 更新本 README 中的 Commit 和日期
3. 同步更新 `cpp-bridge/embedding_abi_compat.h` 中的接口状态标记
