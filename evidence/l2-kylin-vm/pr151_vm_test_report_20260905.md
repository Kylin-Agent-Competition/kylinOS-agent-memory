# PR151 VM 测试报告

- 仓库：`Kylin-Agent-Competition/kylinOS-agent-memory`
- 分支：`feat/C-host-mapping`
- 被测提交：`a8b78df8c19210886bd3be1c6fb0020fdf5468f3`
- 环境：银河麒麟 V11 x86_64，SSH `127.0.0.1:2222`
- 日期：2026-09-05

## 已完成测试

### 客户端完整回归

命令：

```bash
ctest --test-dir memory-client/build --output-on-failure
```

结果：`12/12` 测试套件通过，`0` 失败，退出码 `0`，总耗时 `36.21 sec`。

其中：

- `turn_extraction_adapter`：15/15 PASS
- `production_source_resolver`：18/18 PASS
- `d11c_qml_load`：7/7 PASS

完整输出记录：
`/home/yanmouren778/test-rounds/d13a-e10dfb6/pr151_memory_client_ctest_20260905.log`

记录 SHA-256：
`d775abd35dec70eb6be02338a4ef7cf1fdb19c610f10755b1e873426c9721363`

### Hook 集成回归

命令：

```bash
bash os-agent-integration/patches/test_connect_hook.sh --keep --verbose
```

结果：`20 PASS / 0 FAIL / 0 SKIP`。覆盖 Hook 编译、匹配重定向、非匹配直通、自定义环境变量、多次连接和无 Hook 失败路径。

日志：
`/home/yanmouren778/kylin-memory-echo/logs/hook_tests/test_connect_hook_20260905_171255.log`

### QML 应用构建

`kylin-memory-client` 应用本体编译成功。

## 未通过或未完成项

- QML 应用运行 smoke 在 `VerticalLinkPage.qml:96` 失败：QtQuick.Layouts 运行时不支持 `bottomPadding` 属性，退出码 `255`。
- 真实助手 DB `/home/yanmouren778/.config/kylin-aiassistant/kylin_aiassistant_database.db` 可读，但当前为 0 条 `RECORD`、0 个 session；实际 `RECORD(ID, sessionID, msgIndex, message, operateTime)` schema 与当前 resolver 所需的 `role/turn_id/content` 不一致。
- PR151 当前提交仍保持 `memory-service` 的 `PRODUCTION_RESOLVER_STATUS = BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED`，未接入真实 Chat DB、production `turn.finalized` handler 或 TD-008/TD-009 宿主观察链路。因此本报告不将真实宿主 S5 L2 声明为 PASS。

## 结论

本次提交在 VM 上完成了当前分支可执行的客户端全量回归和既有 Hook 集成回归；真实宿主 S5 L2 仍待 C/D 轨补齐 production mapping、handler 和宿主 Hook 证据后复测。

