# 部署指南

本目录保存麒麟 OS Agent 记忆系统的安装、运行、回滚与银河麒麟宿主验证说明。

## 推荐入口

- [安装与部署指南](INSTALLATION_GUIDE.md)：从发布包构建、银河麒麟 V11 安装、systemd、真实 Embedding SDK 验证，到 Host Integration RC、回滚和比赛提交前验收。
- [`../../packaging/README.md`](../../packaging/README.md)：D14A 发布包结构、构建与 smoke 的实现级说明。
- [`../../os-agent-integration/host-memory-bridge/README.md`](../../os-agent-integration/host-memory-bridge/README.md)：post-D15D 真实麒灵助手 Host Integration RC。

## 当前边界

当前 `main` 的历史 D15D release identity 已因后续 runtime/package-impacting drift 失去对当前主线的正式发布新鲜度。比赛最终版本应在最终冻结 Commit 上重新构建发布包，并重新完成干净银河麒麟 VM 安装、验证、回滚与 evidence 绑定。

WSL/CI 结果只用于 L0/L1，不能替代银河麒麟 V11 的 L2/L3 Runtime Evidence。
