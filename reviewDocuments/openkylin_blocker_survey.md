# openkylin 仓库阻塞项调查报告

**调查时间**: 2026-08-07  
**调查对象**: https://gitee.com/openkylin 组织  
**对照文档**: `D4_GATE0_FORMAL_DECISION_20260807.md` §1.4 及 `D2-1-KAIMING-HOOK`

---

## 一、阻塞项核查结果

| # | 文档阻塞原因 | 仓库实际情况 | 结论 |
|---|-----------|-----------|------|
| 1 | 闭源二进制，源码不可获取 | `kylin-aiassistant` 在 [gitee.com/openkylin/kylin-aiassistant](https://gitee.com/openkylin/kylin-aiassistant) **完全开源**，含完整 C++ 源码、`debian/` 打包目录、README 构建说明 | ❌ **不成立** |
| 2 | 无 SDK 构建环境 | README 提供 `debian/control` Build-Depends，支持 `sudo apt-get build-dep .` 一键安装；`kylin-ai-subsystem` 提供 `build-deploy.sh` 统一构建脚本，自动处理 `devscripts`/`build-essential`/`fakeroot` 等依赖 | ❌ **不成立** |
| 3 | 无签名权限 | 仓库 README 明确使用 `dpkg-buildpackage -us -uc`（`-us`/`-uc` = 不签名源码包/不签名 changes）；本地 `qmake && make` 验证完全不需要签名 | ⚠️ **局部不成立** — 仅生产部署需签名，Gate 0 VM 内编译验证无需签名 |
| 4 | Socket 路径硬编码（strings 扫描未发现） | 源码可获取后，无需再依赖 `strings` 黑盒扫描。`kylin-aiassistant.pro` 显示通信通过 `-lkylin-ai-base` 实现，对应 `chatoperator.cpp`；Socket 路径可在源码层直接审计/修改 | ⚠️ **前提失效** — 黑盒分析前提已不存在 |
| 5 | Gate 0 不具备修改麒麟 SDK 组件的权限 | 源码开源后，Gate 0 可在 VM 内独立克隆、修改、编译验证，无需向麒麟申请"修改 SDK 权限" | ❌ **伪阻塞** — 组织假设错误 |
| 6 | 无 QLocalSocket 配置点 | 同 #4，源码层可审计 `ChatOperator` 到 `kylin-ai-base` 的调用链；且 `kylin-ai-runtime`、`kylin-ai-sdk` 等依赖库也在 openkylin 开源 | ⚠️ **前提失效** |

---

## 二、关键遗漏信息

原阻塞项分析 **完全未包含** 以下 openkylin 仓库已提供的解决路径：

### 2.1 `kylin-ai-subsystem` 统一构建流水线

该 meta-package 的 `build-deploy.sh` 支持：
- `--mode debuild/cmake` 双模式构建
- `--only NAME` 单仓库构建
- `--keep-going` 容错构建

已覆盖 Gate 0 所需的"获取源码 → 安装依赖 → 编译 → 打包"全链路。

### 2.2 `kylin-aiassistant` 本地编译无需打包即可验证

`qmake && make && sudo make install` 可直接生成未签名二进制在 VM 中运行，跳过 deb 签名问题。

### 2.3 AI 子系统多组件均已开源

除 `kylin-aiassistant` 外，以下上下游组件均在同一组织下开源：
- `kylin-ai-runtime`
- `kylin-ai-sdk`
- `kylin-ai-engine-plugins`
- `kylin-ai-model-manager`

Tool Result 链路的依赖库并非黑盒。

---

## 三、建议

1. **立即更新 D2-1 调查报告**  
   `kylin-aiassistant` 源码可获取，"闭源二进制"和"无构建环境"两条阻塞原因应标记为 **RESOLVED**。

2. **重新评估 Gate 0 第 3 项**  
   在 VM 中执行 `git clone + qmake + make` 编译真实 `kylin-aiassistant`，通过源码修改 Socket 目标指向 Memory Service，验证真实 Tool Result 链路。这不需要官方签名，也不需要"修改 SDK 权限"。

3. **确认 `kylin-ai-base` 接口**  
   该库未找到独立仓库，可能内嵌于 `kylin-ai-sdk` 或 `kylin-ai-runtime`。建议直接查看 `kylin-aiassistant` 源码中 `ChatOperator` 对 `kylin-ai-base` 的调用点，确认 UDS/QLocalSocket 路径是否可通过环境变量或配置文件注入。

---

## 四、参考仓库

| 仓库 | 地址 | 说明 |
|------|------|------|
| kylin-aiassistant | https://gitee.com/openkylin/kylin-aiassistant | 主程序，C++ 源码开源 |
| kylin-ai-subsystem | https://gitee.com/openkylin/kylin-ai-subsystem | 统一构建脚本、仓库清单 |
| kylin-ai-runtime | https://gitee.com/openkylin/kylin-ai-runtime | 运行时依赖 |
| kylin-ai-sdk | https://gitee.com/openkylin/kylin-ai-sdk | SDK 接口 |
| kylin-ai-engine-plugins | https://gitee.com/openkylin/kylin-ai-engine-plugins | 引擎插件 |
| kylin-ai-model-manager | https://gitee.com/openkylin/kylin-ai-model-manager | 模型管理 |
