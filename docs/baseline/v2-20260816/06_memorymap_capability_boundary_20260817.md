# 记忆地图（kylin-ai-memorymap）能力边界调查报告

**编号**: KMA-CAPABILITY-MEMORYMAP-20260817
**性质**: 麒麟 VM 实测能力边界调查（ABI/包/Schema/字符串/依赖级 + 运行态探查）
**目标环境**: 银河麒麟 V11 2603 x86_64 VirtualBox（VM `kylin-agent-pc`，内核 6.6.0-76-generic）
**调查时间**: 2026-08-17
**调查方式**: SSH 127.0.0.1:2222（用户 kylin-agent）
**证据目录**: `evidence/l2-kylin-vm/memorymap-boundary-20260817/`（phase1~phase7 原始日志 + MANIFEST.sha256）

> 本报告结论均基于麒麟 VM 实测证据（文件、符号、依赖、Schema、字符串），未做交互式运行时功能验证（recording-memory 默认关闭，服务未运行），能力状态按证据等级如实标注。

---

## 0 结论摘要

1. **官方「记忆地图」（memorymap）是存在的、真实安装的 GUI 应用**：`cn.kylin.kylin-ai-memorymap 2.0.23`，属于 Kaiming 分层应用（非 dpkg 包），主二进制 `kylin-ai-memorymap`（Build ID `9f0b1cb72c6a1b90b57d8d039f1367f3d4875b5d`，746216 字节，未 strip）。

2. **memorymap 本质是「屏幕截图照片式记忆」的 UI 前端**，其后端是 `kylin-ai-recollect-service`（systemd user 服务，Build ID `dbb79394d82e722f230bc2f3e57510a98e5d2cf6`）。二者共同构成官方「视觉/截图时间线记忆」能力，**不是**偏好/知识/工具结果的通用 Agent 记忆系统。

3. **技术链路已确证（依赖 + 字符串 + Schema）**：截图采集 → 合成 MP4 → OCR（vision SDK）→ CLIP 图文 Embedding（embedding SDK，`cn-clip_512`）→ SQLite 结构化 + Milvus-Lite 向量库（vector-engine-client）→ 文本/视觉检索 → 时间线浏览 → 删除用户数据。

4. **与赛题关系**：memorymap/recollect 覆盖「屏幕活动视觉记忆」，**不覆盖**赛题的偏好动态提取与版本、知识结构化与冲突、Tool Result 语义、自然语言精准遗忘、短中长期流转、统一 Memory Context 注入。自研 Memory Service 仍为核心原创工作，memorymap 仅可作「屏幕行为」条件数据源（延续 01 §8 对 Recollect 的定位）。

---

## 1 组件与安装形态

| 项 | 实测值 | 证据 |
| --- | --- | --- |
| 应用标识 | `cn.kylin.kylin-ai-memorymap` 2.0.23 | phase1 `find /opt/kaiming` |
| 安装形态 | Kaiming 分层应用（`/opt/kaiming/layers/stable/x86_64/app/`），**非 dpkg 包**（`dpkg -l` 无此包） | phase1 |
| 主二进制 | `/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-ai-memorymap/binary/2.0.23/files/bin/kylin-ai-memorymap` | phase1/phase2 |
| 桌面入口 | `kylin-ai-memorymap.desktop`，`Exec=/usr/bin/kylin-ai-memorymap`（该路径实际不存在，由 Kaiming 启动器封装） | phase2 |
| 名称 | Memory Map / 记忆地图 | phase2 |
| 官方描述 | "以照片记忆般的体验，快速找回电脑中的一切" | phase2 |
| 桌面分类 | `Categories=AI` | phase2 |

后端 `kylin-ai-recollect-service` 是 **dpkg 包**（`kylin-ai-recollect-service 1.0.0.0-0k1.0`，binary `/usr/bin/kylin-ai-recollect-service`），systemd user unit `kylin-ai-recollect-service.service`（static）。配套 client 库 `libkylin-ai-recollect-client.so.1`（`libkylin-ai-recollect-client 1.0.0.0-0k1.0`）。

---

## 2 功能边界判定

### 2.1 明确存在的能力（ABI/符号/字符串实证）

**a. 屏幕截图采集与视频合成（后台服务）**
- 依赖 `libavcodec/libavformat/libavutil/libswscale`（ffmpeg）+ `libX11`/`libwayland` 截图。
- 字符串：`convertImagesToVideo`、`convertRemainedImagesToVideo`、`Failed to take screenshot`、`VideoComposer`。
- 截图间隔可配：`screenshot-interval` 2–60 秒（默认 5 秒）。

**b. OCR 文字提取**
- `OcrModule`（memorymap UI 侧）、`OcrModel`（service 侧）。
- 依赖 `libkysdk-coreai-vision.so.1`。
- SQLite `screenshots` 表含 `ocr_text` 字段；检索用 `AND ocr_text LIKE '%…%'`。

**c. CLIP 图文多模态 Embedding**
- 依赖 `libkysdk-coreai-embedding.so.1`。
- 模型：`ensemble-embd_cn-clip_512-uint8-text` + `embd_cn-clip_512-uint8-image`（512 维 CN-CLIP）。
- 调用：`image_embedding_create_session/init_session/init_model/image_embedding_by_base64_image_data`；`embedding_result_get_vector_data/get_vector_length`；`embedding_model_info_get_model_dim/get_model_name`。

**d. 向量存储与检索**
- 依赖 `libkysdk-vector-engine-client.so.1`（Milvus-Lite fork）。
- 字符串：`Failed to connect to milvus vector database`、`imagecollection`、`imageEmbedding`、`embedding field`、`Failed to search`。
- 向量库路径：`~/.cache/kylin-ai-memorymap/vector_database`；迁移路径 `~/.local/share/milvus-lite/default.db` → `~/.local/share/kylin-ai-vector-engine/default.db`。

**e. 结构化存储**
- SQLite `~/.cache/kylin-ai-memorymap/traditional_database/`，Schema（实证）：
  ```sql
  CREATE TABLE screenshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      video_name TEXT NOT NULL,
      ocr_text TEXT,
      frame_index_of_video INTEGER NOT NULL,
      frame_index_of_day INTEGER NOT NULL,
      real_time INTEGER NOT NULL,
      desktop_file_path TEXT
  );
  CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_screenshot
      ON screenshots(video_name, ocr_text, frame_index_of_video, frame_index_of_day, real_time, desktop_file_path);
  ```

**f. 检索与时间线**
- D-Bus 接口方法（`com.kylin.Recollect` @ `/com/kylin/Recollect`）：
  `getOcrScreenShotData`（文本检索）、`getVisualScreenShotData`（视觉检索）、`getScreenshotDataOfDay`、`getAppListOfDay`、`getFirstAndLastDay`、`getRecordingMemory`、`setRecordingMemory`、`deleteUserData`。
- 信号：`activeAppChanged`、`backInTimeDetected`、`frameDeleted`、`recordingMemoryChanged`、`todayFrameNumberChanged`。
- client 库导出 C API 见 phase4（`recollect_*` 系列 + `RecollectClient`/`ServiceManager`/`FrameExtractor` 类）。

**g. 数据管理与删除**
- `deleteUserData` / `handle-delete-user-data`。
- `DELETE FROM screenshots WHERE real_time > ? AND real_time <= ?`；drop collection；删除视频。

**h. 配置项（gschema `com.kylin.memorymap` / `com.kylin.recollect.service`）**
- `recording-memory`（默认 false）、`screenshot-interval`（5s）、`max-result-number`（18）、`max-storage-size-gb`（5–20GB）、`exclude-apps`、`close-window-option`（minimize/exit）、`no-remind`、`enabled`。

### 2.2 明确不存在 / 不覆盖的能力

| 赛题/项目需要的能力 | memorymap 是否具备 | 证据 |
| --- | --- | --- |
| 偏好动态提取与版本 | ❌ 无 | 无相关符号/字符串/表结构 |
| 知识结构化与冲突消解 | ❌ 无 | 仅 `screenshots` 一张表 + 向量 |
| Tool Result 语义治理 | ❌ 无 | 无 tool 相关接口 |
| 自然语言精准遗忘（语义级） | ⚠️ 仅底层删除原语 | `deleteUserData`（按时间区间删除，非语义） |
| 短/中/长期记忆流转 | ❌ 无 | 无生命周期/TTL 机制 |
| Memory Context 注入到聊天 | ❌ 无 | 独立应用，不接入聊天请求链 |
| 多源融合（聊天/会议/文档/配置） | ❌ 无 | 仅屏幕截图单一来源 |
| 用户偏好/证据/来源/版本字段 | ❌ 无 | Schema 无此类字段 |

### 2.3 能力状态标签（按 01 §2.1 口径）

| 能力 | 状态 | 证据等级 |
| --- | --- | --- |
| memorymap 应用存在并安装 | HOST_VERIFIED | E3（二进制/文件实测） |
| 截图+OCR+CLIP 图文 Embedding+Milvus 向量+SQLite 链路 | ABI_VERIFIED | E3（依赖 + 符号 + Schema 字符串） |
| 文本检索（OCR） | SOURCE/ABI_VERIFIED | E3（`ocr_text LIKE`、`getOcrScreenShotData`） |
| 视觉检索（CLIP） | SOURCE/ABI_VERIFIED | E3（CLIP 模型名、`getVisualScreenShotData`） |
| 删除用户数据 | ABI_VERIFIED | E3（`deleteUserData`、SQL DELETE） |
| 端到端运行/召回效果 | **UNTESTED** | E0（recording-memory=false，服务未运行，未做交互验证） |

---

## 3 与旧环境基线能力边界比对

| 维度 | 旧基线（01 v1.1 / 基线 v2） | 本次 5.0.3 实测 | 结论变化 |
| --- | --- | --- | --- |
| memorymap 组件 | 旧基线 v2「新增应用，功能未知」；01 v1.1 无此组件 | **已确认为「截图视觉记忆」UI + recollect 后台** | 从「未知」→「已定位能力边界」 |
| MEM-001 官方 MemoryClient | 01 v1.1：NOT_FOUND | **仍为 NOT_FOUND（无通用偏好/知识 MemoryClient）** | 维持，但需补充：官方提供了「视觉记忆 client」（`libkylin-ai-recollect-client`），非通用记忆 |
| MEM-002 完整 Memory Service | 01 v1.1：NOT_FOUND | **仍 NOT_FOUND（无偏好/知识/工具记忆闭环）** | 维持 |
| Recollect 定位 | 01 §8：独立截图/OCR/时间线系统，条件数据源，recording-memory=false | **证实：recollect-service 是 memorymap 的后台，链路 = 截图+OCR+CLIP+Milvus+SQLite** | 从「源码/ABI 推断」升级为「宿主二进制实测」 |
| REC-001 普通聊天参与 | 01 v1.1：NOT_FOUND/E4（成功聊天未启动 Recollect） | 未变化（memorymap 独立于聊天，recording 默认关） | 维持，仍非主链依赖 |
| REC-002 D-Bus 数据读取 | 基线 v2：SOURCE_VERIFIED（正式 client 已装） | **升级：`com.kylin.Recollect` D-Bus 接口 + 完整 C API 已实证** | SOURCE_VERIFIED → ABI_VERIFIED |
| Embedding 图像/多模态 | 基线 v2：ABI_VERIFIED（模型已就位） | **证实：memorymap 实际用 `cn-clip_512` 图文双模型做视觉记忆** | 印证基线 v2 上调结论 |
| Vector Engine 用途 | 01 §4：语义索引基础设施 | **证实：官方 recollect 直接用 vector-engine-client(Milvus-Lite) 存 CLIP 向量** | 印证「官方原生路径」存在，但仍非检索融合主链 |

### 3.1 对项目边界的关键影响

1. **官方「记忆」= 屏幕视觉记忆，非偏好/知识记忆**：memorymap/recollect 捕获的是「屏幕上出现过什么」（截图 + OCR + 视觉向量），不涉及「用户偏好」「知识冲突」「工具执行结果」。这**印证而非动摇**自研 Memory Service 的原创必要性。

2. **memorymap 可作为「屏幕行为」条件数据源**：其 D-Bus 接口（`com.kylin.Recollect`）与 client 库提供了可复用的读取通道（`getOcrScreenShotData`/`getVisualScreenShotData`/`getAppListOfDay`/`deleteUserData`），与 01 §8「Recollect 条件数据源」定位一致，且现在有了**正式的、可 ABI 级对接的接口证据**。

3. **共享基础设施确认**：官方 recollect 与本项目复用同一套 SDK（`libkysdk-coreai-embedding`、`libkysdk-coreai-vision`、`libkysdk-vector-engine-client`/Milvus-Lite）。这意味着本项目「端侧 Embedding + 轻量向量存储」的技术选型与官方同构，适配/评测风险更低，但也需在资源与隐私边界上与 recollect 隔离（独立 Collection、独立存储路径、独立授权）。

4. **隐私与遗忘仍需自研**：memorymap 的删除是「按时间区间」的底层删除原语，不提供语义级精准遗忘、跨来源级联、preview/confirm/幂等，与赛题「自然语言精准遗忘」仍有本质差距。

---

## 4 待运行时补测项（未在本报告声称已完成）

recording-memory 当前为 false，recollect-service 未运行，因此以下为 UNTESTED，需后续在 VM 交互式验证：

1. 开启 recording 后，截图→OCR→CLIP→向量落库的端到端闭环与召回效果。
2. `getVisualScreenShotData` 视觉检索（CLIP 跨模态）实际命中率。
3. `deleteUserData` 删除后向量/SQLite/视频是否全部清除（无残留）。
4. memorymap UI 与官方 AI 助手（5.0.3）是否存在联动（当前证据显示二者独立）。
5. 隐私边界：`exclude-apps` 是否真正阻止指定应用被截图。

---

## 5 证据清单

| 文件 | 内容 |
| --- | --- |
| `evidence/l2-kylin-vm/memorymap-boundary-20260817/phase1_package.log` | dpkg 包列表、Kaiming 应用层、find memorymap 文件树 |
| `phase2_binary.log` | desktop 入口、gschema、file/readelf(Build ID)/ldd 依赖 |
| `phase3_interfaces.log` | /usr/bin 符号、D-Bus services、systemd user units、gsettings、数据路径 |
| `phase4_symbols_strings.log` | recollect-client `nm -D` 导出符号 + memorymap 二进制关键字符串 |
| `phase5_recollect_service.log` | recollect-service unit/二进制/依赖（SQLite+Vision+Embedding+Vector+OpenCV）、数据路径、Schema |
| `phase6_recollect_gschema_dbus.log` | recollect gschema、D-Bus 名、SQLite CREATE TABLE、存储路径字符串 |
| `phase7_dbus_api.log` | D-Bus 接口方法/信号全量、CLIP 模型名、embedding/milvus 调用字符串 |
| `MANIFEST.sha256` | 上述 7 个日志的 SHA-256 |

## 签署

| 角色 | 姓名/标识 | 日期 | 结论 |
| --- | --- | --- | --- |
| 调查人 | Agent | 2026-08-17 | 待 Review |
| Reviewer 1 | 待填写 | | |
| Reviewer 2 | 待填写 | | |
