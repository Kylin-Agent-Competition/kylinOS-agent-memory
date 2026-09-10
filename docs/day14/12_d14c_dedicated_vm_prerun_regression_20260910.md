# D14C 专用 VM 预运行回归（2026-09-10）

## 结论与边界

本轮在用户提供的 D14C 专用银河麒麟 VM 上完成构建环境配置、MemoryClient
回归和运行时只读盘点。结果为 `UNVERIFIED` 的预运行/诊断记录；未创建 D14C
formal evidence root，且不构成 `L3 PASS`、`HOST_VERIFIED` 或 production-ready
结论。

受测源树为 `/home/yanmouren778/d14b-ba3b50e-full-preparation`，其提交为
`ba3b50e1bdeea185bca9daee9d1d45958f62a636`。测试结束后 `git status --short`
无输出，构建生成物未改动版本化源码。

## 环境与构建

- VM：Kylin V11，Linux `6.6.0-63-generic`，x86_64。
- 本轮安装 Qt5 开发依赖，并恢复 CMake、CMake 运行库和 Git；该机为 OSTree
  系统，配置位于可写 overlay，重启后可能失效。本轮未重启 VM。
- 非 GUI 测试配置和编译均成功。
- `QT_QPA_PLATFORM=offscreen ctest --output-on-failure`：14/14 通过，实际耗时
  34.39 秒，覆盖 protocol adapter、mock client、D5--D13C、QML 加载、turn
  extraction 与 production source resolver。
- `KYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON`、
  `KYLIN_MEMORY_CLIENT_BUILD_TESTS=OFF` 的 GUI 客户端构建成功，
  `kylin-memory-client` 目标已链接。

编译仅出现既有 Qt5 弃用 API 与未使用函数警告，没有编译或测试失败。

## 运行时盘点

- `kylin-memory.service` 为 `active`，MainPID 为 1722；UDS
  `/run/user/1000/kylin-memory/memory.sock` 的属主为目标用户、模式为 0600。
- 以目标用户建立并立即关闭 UDS 连接成功；未发送协议帧、未调用业务方法，亦未读写
  聊天数据。该检查仅证明 socket accept 可达。
- 运行中 AI Assistant 的遗留启动路径 `/bin/kylin-aiassistant` 已不存在，但其进程映像
  SHA-256 与官方 Kaiming 3.0.67 layer 中的安装二进制完全一致，因此运行映像可绑定
  到该安装物；旧启动路径下的重启/回退安全性仍未验证。
- 已构建 GUI 客户端二进制，但未发现已部署、正在运行的生产 MemoryClient 进程。

## Formal D14C 的后续条件

真实链路“AI Assistant → 已部署 MemoryClient → UDS → Memory Service”尚因生产
MemoryClient 未部署而未闭合。与此同时，主线当前仍没有可消费的 D14C formal
handoff；D14D handoff 虽保持 `L3_READY`，但明确 `production_ready=false`。G4--G7
尚未形成可机读的 D14C 开跑输入，故不得启动 formal preflight 或创建 evidence root。

本记录不含用户/助手正文、命令行原文、账号口令或其他凭据。
