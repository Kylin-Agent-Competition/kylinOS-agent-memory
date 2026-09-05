# C-HM S5r2 真实宿主 Chat DB 验证报告（V3-R 改造后复测）

- 仓库：`Kylin-Agent-Competition/kylinOS-agent-memory`

- 分支：`feat/C-host-mapping` @ `d9a834b`（代码 @ `55ca828`）

- 环境：银河麒麟桌面操作系统 V11 x86_64（bacon-pc，Qt 5.15.19，g++ 11.x，KYSEC enabled；SSH `172.19.224.1:2222`）

- 日期：2026-09-05

- 执行方式：`git archive` 离线包上传 + paramiko SSH 脚本化执行（同 `c_hm_bacon_vm_schema_and_regression_20260905.md` 流程）

- 本轮范围：V3-R 改造（`55ca828`，ProductionSourceResolver 适配 RECORD + JSON blob）后的 S5 client 侧复测——真实宿主 Chat DB 上验证 resolver + TurnExtractionAdapter

## 一、memory-client L0 回归（ctest，d9a834b）

命令：`cmake -S . -B build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF && cmake --build build -j$(nproc) && cd build && ctest --output-on-failure`

结果：**11/11 测试套件通过，0 失败**（22.05s）：

```
protocol_adapter / memory_client_mock / d5_vertical_link_demo /
d7c_preference_editor / d6c_multi_source_adapters /
d8c_knowledge_conflict_lifecycle / d9c_context_assemble / d10c_forgetting /
d11c_e2e_orchestrator / turn_extraction_adapter / production_source_resolver
```

其中 `production_source_resolver` 为 V3-R 重构后版本（RECORD + JSON blob fixture，25 用例），在麒麟真实运行时全绿。QML 2 项 gate 跳过同前（KYSEC ostree guard，QML 侧验证已由上轮 mini loader 14/14 补位，本轮无 QML 改动）。

## 二、V5 新发现：RECORD.ID 全部为 NULL（行无逻辑主键）

S5 前置 DB 快照发现（上轮 B1~B5 以 sessionID 为查询键，未覆盖本项）：

```
PRAGMA table_info(RECORD):
0|ID|INT AUTO_INCREMENT|0||1     ← pk=1 但…
1|sessionID|VARCHAR(36)|0||0
2|msgIndex|INT|0||0
3|message|TEXT|0||0
4|operateTime|INTEGER|0||0

sqlite_master: CREATE TABLE RECORD(ID INT AUTO_INCREMENT, sessionID VARCHAR(36),
  msgIndex INT, message TEXT, operateTime INTEGER, PRIMARY KEY (ID))

rowid/ID/typeof(ID): 8 行全部 ID=NULL（typeof=null）；
sqlite_sequence 为空；同库 MEETINGRECORD 用正确方言
（ID INTEGER PRIMARY KEY AUTOINCREMENT）——RECORD 的 MySQL 方言建表是宿主应用缺陷
```

诊断：`INT AUTO_INCREMENT` 非 SQLite 自增语法（正确应为 `INTEGER PRIMARY KEY AUTOINCREMENT`），被 SQLite 解释为列类型名；非 INTEGER PRIMARY KEY 的 PK 列不隐含 NOT NULL（SQLite 历史行为），宿主应用插入时不写 ID → 全表 ID=NULL。

影响：`ref:chat-record:{messageId}` 以 RECORD.ID 定位行的假设对真实 DB 不成立；行唯一可用标识 = 隐式 `rowid`（1..8 连续，未发生 VACUUM 重排）。

处置：**不改代码**——`ProductionSourceResolverConfig.idColumn` 覆盖为 `rowid` 即可命中（§三验证），config 适配设计经受住第二类 schema 分歧考验；生产默认值决策（ID vs rowid vs S3 Hook 侧标识）登记待 S3（宿主源码环境确认 Hook 观察点可取得的行标识）后定，红线不变：默认 config 对真实 DB fail-closed，不编造。

## 三、S5 真实 Chat DB harness 验证（18/18 PASS）

### 3.1 方法学：双路径独立基线

- 基线路径：`sqlite3 -readonly` CLI `json_extract` 提取每行正文 → `sha256sum`（VM sqlite3 无 sha256() 函数，shell 管道生成 `~/s5r2_baseline.txt`：rowid|sha256|字节数）
- 被验路径：ProductionSourceResolver（Qt QSQLITE + QJsonDocument，即 V3-R 实现）
- 两路径二进制、JSON 解析器、SQL 引擎调用方式全部独立；SHA-256 + 字节长度双重比对

### 3.2 harness 结果（编译：`g++ -std=c++17 -fPIC` + Qt5Core/Qt5Sql，从 /tmp 执行——/home 受 KYSEC exec control 拦截）

```
PASS [D0.db-hash-before] — sha256=911738367e91…fa927
PASS [A0.default-config-open]
PASS [A1.default-id-fail-closed-ref-2] — RECORD.ID 全 NULL，按 ID 引用必须 fail-closed
PASS [A1.default-id-fail-closed-ref-4] — 同上
PASS [A1.default-id-fail-closed-ref-6] — 同上
PASS [B0.rowid-config-open]
PASS [B1.rowid-hit-final-2] — user[len=51B sha=9fb55514150e921c prefix="有哪些适合户外聚会的小游戏可以玩？"] resp[len=245B sha=6ce48cdd36c5505e prefix="适合户外聚会的小游戏…"] modelRequest=空(不编造)
PASS [B1.rowid-hit-final-4] — user[len=42B sha=bb28efad648dea21…] resp[len=15B sha=8ee465e74a4fb229… prefix="已停止回答"]
PASS [B1.rowid-hit-final-6] — user[len=42B sha=bb28efad648dea21…] resp[len=24B sha=b9fc8d4ffeb6bbe4…] prefix="去除白色衣服上的"]
PASS [B2.user-row-fail-closed] — rowid=7 为 User 行（session3 无终稿）
PASS [B3.missing-row-fail-closed]
PASS [B4.non-controlled-ref-fail-closed]
PASS [B5.repeat-resolve-still-hits]
PASS [C1.adapter-extracted]
PASS [C2.provider-candidate-real-texts] — 真实正文与基线 SHA-256 一致
PASS [C3.ipc-event-content-isolation] — ipcEvent 不含正文（含关键词扫描）
PASS [C4.source-event-id-linked]
PASS [D1.db-hash-unchanged] — sha256=911738367e91…fa927

S5R2 SUMMARY: failures=0（退出码 0）
```

验证语义明细：

| 组 | 验证点 | 结果 |
|----|--------|------|
| §A | 默认 config（idColumn=ID）：真实终稿引用（rowid 2/4/6）全部 fail-closed | 3/3 PASS（V5 影响下不编造、不误命中） |
| §B | rowid 覆盖 config：真实 Bot 终稿（rowid 2/4/6）全命中；userText/modelResponse 与独立基线 SHA-256 + 字节数一致；modelRequest 留空 | 3/3 PASS |
| §B | fail-closed：User 行（rowid=7）/ 缺失行（999）/ 非受控引用格式 / 重复 resolve 连接复用 | 4/4 PASS |
| §C | TurnExtractionAdapter 真实 finalMessageId="2" 全链路：Extracted、providerCandidate 含真实正文（SHA-256 对基线）、ipcEvent 序列化不含正文（原文隔离红线）、source_event_id ↔ event_id 关联 | 4/4 PASS |
| §D | resolve 前后 DB 文件 SHA-256 不变（harness 内 + shell 独立复核双重） | PASS |

真实数据形态备注：session 0/1/2 为完整 turn（User msgIndex=0 / Bot 终稿 msgIndex=1，相邻配对）；session 3/4 仅 User 无终稿（天然 fail-closed 样本）；rowid=2 终稿为停止生成的部分正文（isEnd=1 且文本截断）、rowid=4 终稿="已停止回答"——均为宿主真实行为样本，resolver 按数据原样返回（终稿判定只看 author=Bot + isEnd=true）。

## 四、结论与遗留

- **V3-R 改造在真实宿主 Chat DB 上验证通过**：resolver（默认 + rowid 覆盖两种 config）与 TurnExtractionAdapter 集成 18/18 PASS；正文提取与 sqlite3 独立基线一致；只读红线（DB 哈希不变）与原文隔离红线（ipcEvent 无正文）均持守
- **V5（RECORD.ID 全 NULL）登记**：生产默认 idColumn 决策待 S3（Hook 观察点可取得的行标识）确认；rowid 覆盖路径已验证可用
- **S5 剩余项**（本 VM 不可行，需宿主源码 / service 运行时环境）：
  - turn.finalized → memory-service → 落库的服务端全链路（本 VM 未部署 memory-service 运行时栈）
  - S3 Hook patch 部署 + TD-008 Hook 点注入确认 + TD-007 三类 Tool 事件（GUI 手动触发）
- 复现：`~/s5r2/`（源码 d9a834b 构建）、`~/s5_realdb_harness.cpp` + `~/s5_harness`（二进制）、`~/s5r2_baseline.txt`（基线）保留在 VM；harness 编译命令见 §3.2
