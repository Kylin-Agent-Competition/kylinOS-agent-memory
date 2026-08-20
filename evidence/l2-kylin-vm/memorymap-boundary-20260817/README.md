# memorymap 能力边界调查证据包

- **调查对象**: 官方「记忆地图」`cn.kylin.kylin-ai-memorymap 2.0.23` + 后端 `kylin-ai-recollect-service 1.0.0.0-0k1.0`
- **环境**: 银河麒麟 V11 2603 x86_64（内核 6.6.0-76-generic，VirtualBox，SSH 127.0.0.1:2222）
- **调查日期**: 2026-08-17
- **报告**: `docs/baseline/v2-20260816/06_memorymap_capability_boundary_20260817.md`

## 证据文件

| 文件 | 内容 | 关键结论 |
| --- | --- | --- |
| phase1_package.log | dpkg 包列表 + Kaiming 应用层 + find 文件树 | memorymap 是 Kaiming 分层应用（非 dpkg），主二进制位于 /opt/kaiming/.../files/bin/ |
| phase2_binary.log | desktop 入口 + gschema + file/readelf/ldd | Build ID `9f0b1cb7...`，依赖 Qt5Quick/vision/recollect-client/ffmpeg/X11 |
| phase3_interfaces.log | /usr/bin 符号 + D-Bus + systemd + gsettings + 数据路径 | Exec 指向 /usr/bin（实际不存在）；gsettings 8 项配置默认值 |
| phase4_symbols_strings.log | recollect-client `nm -D` 导出符号 + memorymap 二进制字符串 | recollect_* C API + RecollectClient/ServiceManager/FrameExtractor 类 |
| phase5_recollect_service.log | recollect-service unit/二进制/依赖/数据路径/Schema | 依赖 SQLite+Vision+Embedding+Vector+OpenCV+ffmpeg；screenshots 表 Schema |
| phase6_recollect_gschema_dbus.log | recollect gschema + D-Bus 名 + SQL Schema + 存储路径 | `com.kylin.Recollect`；`~/.cache/kylin-ai-memorymap/{screenshots,traditional_database,vector_database}` |
| phase7_dbus_api.log | D-Bus 接口方法/信号 + CLIP 模型名 + embedding/milvus 字符串 | CLIP `cn-clip_512` 图文双模型；Milvus-Lite 向量检索链路 |
| phase8_arch_boundary.log | files 目录树 + memorymap UND 符号 + nm -D 导出 | memorymap 仅 import recollect+text_recognition，无导出业务 API |
| phase9_kernel_depth.log | memorymap NEEDED 直接依赖 + recollect-service UND 符号 | memorymap 无 embedding/vector/sqlite/ffmpeg；recollect-service 全套记忆内核符号 |
| phase10_ui_vs_kernel.log | memorymap OCR 符号 + QML 内嵌 + UI 模型类 | QML 编译进二进制；注册类全是 UI/数据模型 |

## 核心判定

memorymap（UI 前端）+ recollect-service（记忆内核）= 官方「屏幕截图照片式记忆」系统（截图→MP4→OCR→CLIP 图文向量→SQLite+Milvus-Lite→文本/视觉检索→时间线→删除）。

**纯 UI vs 记忆内核**：memorymap 是纯 UI（无 embedding/vector/sqlite 直接依赖，仅调 recollect-client + 本地 OCR 辅助）；记忆内核在 recollect-service（调用 embedding/vision/vector-engine-client SDK + sqlite3 + opencv + ffmpeg）。

**可复用/重叠/互补**：memorymap 不可复用（前端应用）；recollect-service 只读可复用（条件数据源）；与自研 Memory Service 仅基础设施重叠、功能互补。MEM-001/002 维持 NOT_FOUND，新增「官方视觉记忆组件」认知。

**不是**通用 Agent 记忆系统（无偏好提取/版本、知识结构化/冲突、Tool Result 语义、自然语言精准遗忘、Memory Context 注入）。

## 证据完整性

所有 `.log` 文件 SHA-256 见 `MANIFEST.sha256`。调查脚本 `_kylin_ssh.py` 可复用重跑（依赖 Python 3.13 paramiko + `KYLIN_VM_PASSWORD` 环境变量）。
