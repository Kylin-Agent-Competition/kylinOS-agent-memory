# Packaging

## 模块定位

负责将 Memory Service 及 Bridge 打包为可部署的发行包，支持 systemd 服务和 Kaiming 包两种分发方式。

## 当前状态

**仅建立目录和职责边界，尚无生产实现。**

## 子目录

| 目录 | 说明 |
|------|------|
| `systemd/` | systemd service unit 和安装脚本 |
| `kaiming/` | Kaiming 包打包配置与脚本 |

## 验收要求

| 层级 | 要求 |
|------|------|
| **L2** | 麒麟 VM 中 systemd 服务正常启停 |
| **L2** | 麒麟 VM 中 Kaiming 包安装与卸载正常 |
