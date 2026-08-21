# Scripts

自动化脚本集合，用于环境检查、仓库基线验证和日常开发辅助。

## 脚本清单

| 脚本 | 说明 |
|------|------|
| `check_kylin_environment.sh` | 麒麟虚拟机只读环境信息采集 |
| `verify_repository_baseline.sh` | 仓库基线结构验证 |
| `verify_a_day4_day5_vm.sh` | A 轨 Day4–Day5 麒麟 VM 统一构建与真实宿主验证；含依赖/SDK 符号 fail-closed 门禁及 49 项零跳过检查 |
| `check_junit_totals.py` | 按 JUnit `testcase` 节点汇总实际结果，避免依赖 pytest 版本特定的 suite 属性 |
| `run_d1_vector_baseline.sh` | D1 Vector 基线构建与分阶段探针运行；服务重启由操作者执行 |
| `run_d2_vector_smoke.sh` | D2 旧客户端固定哈希构建、KySec/服务/DB/Socket 门禁、一次性 cleanup 授权和分阶段真实数据面验证 |

## 当前状态

`verify_a_day4_day5_vm.sh` 默认从自身位置推导源码根，并允许通过
`A_VM_*` 环境变量隔离 venv、CMake build 和证据目录。它不会安装系统包，
会先核对实际 Python 开发头文件、固定 SDK 包版本和必需动态符号；环境不完整
时在构建前失败。Day4/Day5 的四组真实宿主 JUnit 必须精确得到
`49 passed, 0 skipped`。

`run_d1_vector_baseline.sh` 与 `run_d2_vector_smoke.sh` 会按显式参数
构建或运行测试探针。它们不安装依赖，不自动修改 KySec 信任，不自动
启动/重启服务，不上传证据。运行前必须阅读脚本帮助并由操作者完成
服务与数据库隔离。

`run_d2_vector_smoke.sh` 的 Manifest v2 使用
`reserved → prepared → verified → cleanup_in_progress → cleaned` 状态机。
cleanup 时，runner 持有 run-specific `flock`，锁覆盖
`validate → authorize → probe → finalize`，并在锁内领取一次性 token。
C++ 探针会在创建客户端前复核 Manifest 与数据库文件身份，并独立核验
`/proc/self/exe` 对应真实二进制 SHA-256、systemd InvocationID、engine PID、
进程实际 DB 参数和 Unix Socket 所有者；执行 `DropCollection()` 前还会再次
核验实时身份。cleanup 成功后 runner 在同一把锁内原子写入
`cleanup_completed=true`、完成时间、InvocationID 和 Collection 缺失确认，
并将 token 标记为 `consumed`。已清理 Manifest 不能再次触发破坏性 cleanup；
需要重复确认时，只能运行只读的 `verify-cleanup` 阶段。

Manifest 同时绑定探针主源码 `d2_vector_smoke.cpp`、cleanup 授权与运行时身份
头文件 `d2_cleanup_manifest.h`、runner、ABI 补丁、ABI 断言和最终二进制的
独立 SHA-256，避免新增头文件逻辑只被提交号或二进制哈希间接覆盖。
