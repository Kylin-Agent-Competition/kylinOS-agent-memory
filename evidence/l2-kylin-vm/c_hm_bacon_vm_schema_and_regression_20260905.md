# C-HM bacon VM 回归与宿主 Chat DB schema 确认报告

- 仓库：`Kylin-Agent-Competition/kylinOS-agent-memory`

- 分支：`feat/C-host-mapping` @ `ab43e7d`

- 环境：银河麒麟桌面操作系统 V11 x86\_64（bacon-pc，Qt 5.15.19，SSH `172.19.224.1:2222`）

- 日期：2026-09-05

- 执行方式：SSH（paramiko），脚本上传执行；源码经 `git archive` 本地打包上传（VM 直连 GitHub 不稳定，clone 阻塞后改用离线包）

## 一、memory-client L0 回归（ctest）

命令：`cmake --build build -j$(nproc) && ctest --output-on-failure`（`-DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF`，原因见三.2）

结果：**11/11 测试套件通过，0 失败**（总耗时 19.97s）：

```
protocol_adapter / memory_client_mock / d5_vertical_link_demo /
d7c_preference_editor / d6c_multi_source_adapters /
d8c_knowledge_conflict_lifecycle / d9c_context_assemble /
d10c_forgetting / d11c_e2e_orchestrator /
turn_extraction_adapter / production_source_resolver — 全部 Passed
```

`d11c_qml_load` 与 `qml_pages_load` 因缺 `qtquickcontrols2-5-dev` 被 CMake gate 跳过（预期降级，见三.2），其中 QML 加载验证由二节的 mini loader 等价补位。

## 二、QML 全页面加载验证（14/14 PASS）

`qtdeclarative5-dev-tools` 在本 VM 不含 `qmlscene` 二进制，现场编译 mini loader（等价 `qml_pages_load` 逻辑：注册 `kylin.memory 1.0` 后逐文件 `QQmlComponent` 编译，断言 `status==Ready`）：

```
PASS main.qml / StatusPage / MemoryQueryPage / PreferenceEditorPage /
     VerticalLinkPage / ToolAdapterPage / ManualConfigPage /
     BehaviorObservePage / KnowledgeDetailPage / ConflictComparisonPage /
     LifecycleStatusPage / ContextAssemblePage / ForgetPage /
     D11DemoOrchestratorPage
SUMMARY: total=14 fail=0（loader exit=0，QT_QPA_PLATFORM=offscreen）
```

**验证结论（V1/V2 修复）**：

- V2（`ManualConfigPage` SpinBox `suffix`）：Controls 2 在 Qt 5.x 全系无该属性，本 VM（5.15.19）修复后加载 PASS——修复在「麒麟真实运行时」确认有效；

- V1（ColumnLayout padding）：Qt 5.15 上合法，加载 PASS 确认修复无回归；**Qt 5.12 兼容性结论仍以 pr151 报告 VM（Qt 5.12）复测为准**，本 VM 不越权标注。

## 三、宿主 Chat DB schema 确认（V3 关闭：调查部分）

DB：`~/.config/kylin-aiassistant/kylin_aiassistant_database.db`（只读查询）。

### 3.1 实际 schema 与数据模型

```sql
CREATE TABLE RECORD(ID INT AUTO_INCREMENT, sessionID VARCHAR(36),
  msgIndex INT, message TEXT, operateTime INTEGER, PRIMARY KEY (ID));
-- 另有 HISTORY_ID（history_id 自增序号）、MEETINGRECORD（会议记录，独立域）
```

`message` 列为 JSON blob，关键字段（实测样本）：

| 字段                               | 含义   | 样本                                       |
| -------------------------------- | ---- | ---------------------------------------- |
| `author`                         | 角色   | `"User"` / `"Bot"`（role 信息在 JSON 内，非独立列） |
| `isEnd`                          | 终稿标记 | User 恒 `false`；Bot 终稿 `true`             |
| `message`                        | 正文   | `"如何去除白色衣服上的咖啡渍？"`                       |
| `modelMsg`                       | 模型名  | `"通义千问（Qwen-Plus） 试用版"`                  |
| `noModelError` / `reasonMessage` | 错误信息 | 正常为空串                                    |

数据现状：8 条 RECORD、5 个 session；session 0/1/2 为完整 turn（User+Bot 成对，msgIndex 0/1）；session 3/4 仅 User 无 Bot 终稿（2026-09-05 当日产生，模型未回复）→ **天然 fail-closed 场景样本**。

### 3.2 查询模型 SQL（已在真实 DB 验证通过）

```sql
-- 用户原文
SELECT json_extract(message,'$.message') FROM RECORD
 WHERE sessionID=? AND json_extract(message,'$.author')='User';
-- assistant 终稿
SELECT json_extract(message,'$.message') FROM RECORD
 WHERE sessionID=? AND json_extract(message,'$.author')='Bot'
   AND json_extract(message,'$.isEnd')=1;
-- 模型名（可映射 model_request 侧信息）
SELECT json_extract(message,'$.modelMsg') FROM RECORD
 WHERE sessionID=? AND json_extract(message,'$.author')='Bot';
```

B1\~B5 验证全部通过：用户原文提取、终稿正文提取、模型名提取、无终稿 turn 识别（仅 session 0/1/2 有终稿）、全表分布（User×5 isEnd=0，Bot×3 isEnd=1）。

### 3.3 对 ProductionSourceResolver 的改造结论

S2 的假设 schema（`role`/`turn_id`/`content` 独立列）与实际不符，改造方向明确：

- 表/列名经 `ProductionSourceResolverConfig` 覆盖为 `RECORD`/`sessionID`/`msgIndex`/`message`/`operateTime`；

- role 判定从「列值比较」改为「`json_extract(message,'$.author')`」；

- 终稿判定：`json_extract(message,'$.isEnd')=1 AND author='Bot'`；

- turn 划分：`sessionID` + msgIndex 配对（User N / Bot N+1）；无 Bot 终稿 → fail-closed（nullopt），与 ADR-010 §INSERT 语义一致；

- SQLite 需启用 JSON1（`json_extract`）——麒麟 VM 系统 sqlite3 支持（已实测）。

## 四、环境发现

1. 本 VM 无 S4-BLOCK-003（qtbase5-dev/qtdeclarative5-dev 已装，git/cmake/g++/make 齐备）；
2. `qtquickcontrols2-5-dev` 安装被 KYSEC **ostree-pkgs-guard** 阻止（`当前模式禁止执行（unpack）操作`）——系统分区只读保护，与「不写 /usr」红线一致；QML app target 因此 OFF 构建，QML 验证由 mini loader 补位（不触碰 /usr）；
3. 本 VM 无 kylin-aiassistant 源码与 `os-agent-integration/` 目录 → S3（Hook patch 部署）与 TD-007/008 在本 VM 不可行，需在具备宿主源码构建链的环境执行；
4. GitHub 直连不稳定（DNS 瞬时故障 + clone 长时间阻塞），离线 `git archive` 上传为可靠替代。

## 五、结论

- L0 ctest 在麒麟 VM（本机）11/11 全绿；QML 14/14 加载 PASS（含 V1/V2 修复确认，V1 的 Qt 5.12 兼容性以 pr151 VM 复测为准）；

- **V3（schema 不匹配）调查关闭**：真实 schema、JSON 字段语义、查询模型 SQL 均已在真实 DB 验证，resolver 改造输入齐备；

- S3/S4/TD-007/008/009 未在本 VM 执行（无宿主源码），状态不变；S5 全链路复测待 resolver 改造（V3-R）落地后进行。

