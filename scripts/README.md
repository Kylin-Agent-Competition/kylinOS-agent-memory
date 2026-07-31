# Scripts

自动化脚本集合，用于环境检查、仓库基线验证和日常开发辅助。

## 脚本清单

| 脚本 | 说明 |
|------|------|
| `check_kylin_environment.sh` | 麒麟虚拟机只读环境信息采集 |
| `verify_repository_baseline.sh` | 仓库基线结构验证 |
| `run_d1_vector_baseline.sh` | D1 Vector 基线构建与分阶段探针运行；服务重启由操作者执行 |
| `run_d2_vector_smoke.sh` | D2 旧客户端固定哈希构建、KySec/服务/DB 门禁和分阶段真实数据面验证 |

## 当前状态

`run_d1_vector_baseline.sh` 与 `run_d2_vector_smoke.sh` 会按显式参数
构建或运行测试探针。它们不安装依赖，不自动修改 KySec 信任，不自动
启动/重启服务，不上传证据。运行前必须阅读脚本帮助并由操作者完成
服务与数据库隔离。
