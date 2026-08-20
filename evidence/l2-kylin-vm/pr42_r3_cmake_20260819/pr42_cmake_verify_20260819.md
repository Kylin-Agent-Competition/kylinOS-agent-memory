# PR #42 第三轮 REWORK HIGH-02 — CMake 产物符号导出验证（麒麟 VM）

- **验证项**：`deliverables/PR42_R3_REWORK_ACTION_ITEMS_20260819.md` HIGH-02「CMake `-fvisibility=hidden` 导致 `connect` 符号无法动态导出」
- **修复方式**：方案 A — 删除 `CMakeLists.txt` 中 `-fvisibility=hidden`
- **验证日期**：2026-08-19
- **验证人**：周子腾（D）
- **执行环境**：麒麟 VM（KylinOS V11 x86_64），gcc 12.3.0，cmake 4.4.2（tarball 安装，路径 `/home/kylin-agent/下载/cmake-4.4.2-linux-x86_64/bin/cmake`）
- **源日志**：同目录 `pr42_cmake_verify_20260819.log`

---

## 一、验证结果

| 步骤 | 命令 | 结果 |
|------|------|------|
| 传输完整性 | `sha256sum`（libconnect_hook.c / CMakeLists.txt） | 2/2 MATCH |
| CMake 配置 | `cmake -S . -B build` | PASS（exit=0） |
| CMake 构建 | `cmake --build build` | PASS（exit=0），产出 `build/libconnect_hook.so` |
| 产物类型 | `file build/libconnect_hook.so` | ELF 64-bit LSB shared object |
| 动态符号导出 | `nm -D build/libconnect_hook.so \| grep -w connect` | `00000000000014f0 T connect` |
| 可见性确认 | `readelf -Ws ... \| grep -w connect` | `GLOBAL DEFAULT`（非 LOCAL / hidden） |

## 二、结论

- `connect` 以 `GLOBAL DEFAULT` 可见性导出（`T connect`），满足 LD_PRELOAD interpose 所需的动态符号导出要求，HIGH-02 关闭。
- CMake 构建路径（`-Wall -Wextra -O2`，无 `-fvisibility=hidden`）与手工 gcc 路径现使用等价编译选项，两条路径均确认 `connect` 导出成功。

## 三、诚实边界

- 本证据为 **L0 构建 / 符号级验证**（编译 + `nm -D`/`readelf -Ws` 符号检查），**非 L2 Runtime 证据**；不包含 LD_PRELOAD 实际拦截运行验证（后者见 `D4-OPENKYLIN-HOOK`，仍为 PARTIAL）。
- cmake 4.4.2 为 tarball 安装、未加入 PATH，验证通过绝对路径调用；`D4_BLOCKERS_SYNC_20260817.md` #10「cmake 重装」状态不受影响（系统包管理器仍未安装 cmake）。

## 四、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 验证人 | 周子腾（D） | 2026-08-19 | HIGH-02 关闭（`T connect` 导出验证通过） |
| Reviewer | 谢嘉然（E） | 待签 | |
