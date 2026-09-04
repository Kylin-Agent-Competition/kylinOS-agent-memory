# D11E 麒麟 VM 环境补齐尝试与限制（2026-09-03）

## 目的

按 D11E 项 5 继续补齐 A 轨真实 SDK/Embedding 运行条件，缩小广回归中的 39 skipped（`test_embedding_service_real.py` 等需真实 Embedding SDK + pybind11 Bridge）。

## 已确认的来宾环境

- A 轨 SDK 已安装：`kylin-ai-runtime 1.1.0.1-0k1.32`、`libkylin-coreai-embedding 1.2.0.0-0k0.3`、`libkylin-ondevice-embedding-engine 1.2.0.0-0k0.10`、`libkysdk-ai-common` 等（dpkg 实测）。
- 编译工具链齐备：cmake 3.28.3 / ninja / gcc / g++。
- 缺：`/usr/include/python3.12/Python.h` 不在磁盘（dpkg 记录属 `libpython3.12-dev`，但文件缺失）；`cpp-bridge` 未编译（无 `kylin_embedding*.so`）。

## 尝试与结果

| 步骤 | 结果 |
|---|---|
| `apt-get install -y python3-dev` | 已装（0 变更）；头文件仍缺失 |
| `apt-get install --reinstall -y libpython3.12-dev` | **失败**：Kylin `ostree-pkgs-guard` →「当前模式禁止执行（unpack）操作」退出 256（系统当前为只读/受保护模式，禁止包解包） |
| `cmake -B build` + `cmake --build build -j4`（pybind11 指向 `~/d11e-pylibs`） | 失败：`fatal error: Python.h: 没有那个文件或目录`（缺 Python 开发头） |

## 结论与口径

- A 轨真实 SDK Embedding 用例（39 skipped 主体）在本 D11E 克隆上**因 Kylin 只读模式无法安装 python3-dev 头文件而无法运行**；属环境限制，非 E 业务缺陷，本批不绕过 OS 保护（不尝试降级/破坏系统包管理）。
- 建议：由 A 轨在其可写模式的 D12A/D11 专用 VM（其 L2 证据所在环境）上复跑真实 SDK Embedding 用例；或在允许 unpack 的 VM 快照上补齐 `python3-dev` 后在本分支重跑。
- 本文件不改变既有结论：D11E 项 5 的 A 轨真实 SDK 同 Commit 端到端仍 `UNVERIFIED`；其余可运行项已由 `09–14` 证据覆盖。