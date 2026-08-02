# Scripts

自动化脚本集合，用于环境检查、仓库基线验证和日常开发辅助。

## 脚本清单

| 脚本 | 说明 |
|------|------|
| `check_kylin_environment.sh` | 麒麟虚拟机只读环境信息采集 |
| `verify_repository_baseline.sh` | 仓库基线结构验证 |
| `run_d1_vector_baseline.sh` | D1 Vector 基线构建与分阶段探针运行；服务重启由操作者执行 |
| `run_d2_vector_smoke.sh` | D2 旧客户端固定哈希构建、KySec/服务/DB/Socket 门禁、一次性 cleanup 授权和分阶段真实数据面验证 |

## 当前状态

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
