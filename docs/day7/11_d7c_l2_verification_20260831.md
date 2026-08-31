# D7-C L2 验证报告（麒麟 VM）— 2026-08-31

> 对应 D7C 任务卡 `08_d7c_task_card.md` 工作项 6/7；**验证提交 `a4abe0e`**（`feat/C-d7-preference-version-ui`，MEDIUM-02 重跑绑定最终 HEAD 与真实命令）。

## 一、环境

- VM：`Kylin-V11-2603-D7C-aaed155-Test`（链接克隆，基础快照 `20-btrack-test-deps-20260821`）。
- 来宾：Kylin V11 2603，kernel `6.6.0-63-generic`；SSH `127.0.0.1:2222`，用户 `yanmouren778`。
- 代码：`~/kylinOS-agent-memory-d7c`，工作树 = **`a4abe0e` 内容**（VM 无法直连 GitHub，采用宿主→VM 字节传输 a4abe0e 变更文件 11 个；校验标记：`app.py` 含 `--register-preference-handlers`、`preference_handlers.py` 含 D3 §7.9 冲突校验）。
- Python 3.12.3；依赖安装于 `~/d7c-pylibs`（`pip --target`：pydantic 2.13.5 / sqlalchemy 2.0.52 / pytest 9.1.1 / alembic 1.19.1）。

## 二、前置处理（OSTree）

- `ostree admin unlock`（/usr 可写 overlay，重启后丢弃）。
- 因 OSTree 包守卫拦截 unpack，在 `unshare -m` 命名空间内 `apt install qtbase5-dev`（5.15.19）。
- 修复解锁后缺失文件：cmake/git 二进制、`librhash.so.0`、`libuv.so.1`、`cmake-data`（`apt install --reinstall`）。

## 三、结果

| 项目 | 命令 | 结果 |
|------|------|------|
| D7C 偏好 handler 定向（最终 HEAD） | `pytest tests/test_preference_handlers_d7c.py -q` | **14 passed**（含 HIGH-01 临时生命周期/冲突校验用例） |
| memory-service 全量（最终 HEAD） | `pytest -q` | **1285 passed, 49 skipped**（49 skip = A 轨 `kylin_embedding` 缺失，与 D4B 记录一致） |
| memory-client L0 ctest | `cmake ... && ctest --test-dir memory-client/build` | **4/4**：CI（GitHub Actions）对 `a4abe0e` 复跑确认（含 `d7c_preference_editor` P1–P6）；VM 于 `aaed155` 亦 4/4 |
| 网关级真实 IPC 冒烟 | 启动 `python3 -m app --socket /tmp/d7c-memory.sock --db ~/d7c-gateway.db --no-outbox --register-preference-handlers`（候选契约显式激活 profile）+ FRZ-IPC 客户端 | **9/9 PASS**（create v1/v2、history、rollback v3 current、list、跨用户隔离、INVALID_REQUEST 错误映射） |

## 四、证据

- 证据目录（本机）：`辅助生成文件/文本整理/D7C_L2_20260831/`
- `memory-service-full-d7c-a4abe0e.log`（SHA-256 `b742578ab55418611c91c570c4410ac6d9e1101037844ed2123a874fd3e33c4f`）— 最终 HEAD 全量
- `d7c-gateway-a4abe0e.log`（SHA-256 `cb1fedb80764828742c17e6f7112af5467de5c4d1097ea2e124f9fcbc331aef5`）— 最终 HEAD 真实 IPC 冒烟（命令含 `--register-preference-handlers`）
- 早期（aaed155）证据归档：`memory-service-full-d7c-aaed155.log` / `memory-client-ctest-d7c-aaed155.log` / `d7c-gateway-live.log`（SHA 见旧版本文档）

## 五、未完成

- **工作项 6 宿主侧**：`kylin-aiassistant` 宿主 GUI 的跨会话行为输入联调未执行（本克隆未含宿主集成；网关级 preference.* 真实链路已验证）。
- 契约状态：preference.* 为 `CANDIDATE_SYNC`（ADR-016 待立项），production 默认不注册；上述 IPC 冒烟在 `--register-preference-handlers` 显式激活 profile 下执行（MEDIUM-02：本次重跑即该真实命令组合，tested 状态 = `a4abe0e`）。
- 不声明「麒麟宿主真实交互验收」完成：需另行把修改版 MemoryClient/偏好 IPC 部署到宿主应用后联调。
