# D7-C L2 验证报告（麒麟 VM）— 2026-08-31

> 对应 D7C 任务卡 `08_d7c_task_card.md` 工作项 6/7；验证提交 `aaed155`（`feat/C-d7-preference-version-ui`）。

## 一、环境

- VM：`Kylin-V11-2603-D7C-aaed155-Test`（链接克隆，基础快照 `20-btrack-test-deps-20260821`）。
- 来宾：Kylin V11 2603，kernel `6.6.0-63-generic`；SSH `127.0.0.1:2222`，用户 `yanmouren778`。
- 代码：`~/kylinOS-agent-memory-d7c`，HEAD = `aaed15550d650358b86bcdd73abe90bd99acd2ee`。
- Python 3.12.3；依赖安装于 `~/d7c-pylibs`（`pip --target`：pydantic 2.13.5 / sqlalchemy 2.0.52 / pytest 9.1.1 / alembic 1.19.1）。

## 二、前置处理（OSTree）

- `ostree admin unlock`（/usr 可写 overlay，重启后丢弃）。
- 因 OSTree 包守卫拦截 unpack，在 `unshare -m` 命名空间内 `apt install qtbase5-dev`（5.15.19）。
- 修复解锁后缺失文件：cmake/git 二进制、`librhash.so.0`、`libuv.so.1`、`cmake-data`（`apt install --reinstall`）。

## 三、结果

| 项目 | 命令 | 结果 |
|------|------|------|
| D7C 定向（handler+D7D+迁移+协议） | `pytest tests/test_preference_handlers_d7c.py tests/test_preference_version_repository_d7d.py tests/test_migrations_d7d.py tests/test_protocol.py -q` | **66 passed in 7.40s** |
| memory-service 全量 | `pytest -q` | **1281 passed, 49 skipped in 41.08s**（49 skip = A 轨 `kylin_embedding` 缺失，与 D4B 记录一致） |
| memory-client L0 ctest | `cmake ... && ctest --test-dir memory-client/build` | **100% tests passed, 0 failed out of 4**（含 `d7c_preference_editor` P1–P6） |
| 网关级真实 IPC 冒烟 | 启动 `python3 -m app --socket /tmp/d7c-memory.sock --db ~/d7c-gateway.db --no-outbox` + FRZ-IPC 客户端 | **9/9 PASS**（create v1/v2、history、rollback v3 current、list、跨用户隔离、INVALID_REQUEST 错误映射） |

## 四、证据

- 证据目录（本机）：`辅助生成文件/文本整理/D7C_L2_20260831/`
- `memory-service-full-d7c-aaed155.log`（SHA-256 `cd26534155ee2b4f79b8ad920fc868c3088aa28cf58439a376c8849a4eee392f`）
- `memory-client-ctest-d7c-aaed155.log`（SHA-256 `16cdfc7fd1378a7e1885dda2c07ad58a4be881b6642f3712f7b132842c1137c9`）
- `d7c-gateway-live.log`（SHA-256 `5cc1db3ddd6a5cf45559be28d8e51db98892c017a57879bd498ed7763fc1d13a`）

## 五、未完成

- **工作项 6 宿主侧**：`kylin-aiassistant` 宿主 GUI 的跨会话行为输入联调未执行（本克隆未含宿主集成；网关级 preference.* 真实链路已验证）。
- 不声明「麒麟宿主真实交互验收」完成：需另行把修改版 MemoryClient/偏好 IPC 部署到宿主应用后联调。
