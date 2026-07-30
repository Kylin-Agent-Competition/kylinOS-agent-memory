# Gate 0 SPIKE · Kaiming → 自定义 UDS Echo

## 目录

| 文件 | 用途 |
|------|------|
| `memory_echo_server.py` | Python UDS Echo Server（长度前缀 JSON） |
| `echo_client.cpp` | C++/Qt5 UDS Echo Client（QLocalSocket + QJsonDocument） |
| `CMakeLists.txt` | C++ 构建配置 |
| `deploy_echo.sh` | 构建、安装、启动、测试、备份、回退一体化脚本 |
| `kysec_authorize.sh` | KYSEC 最小授权脚本 |
| `test_echo_on_kylin.py` | 麒麟虚拟机 SSH 自动化测试脚本 |
| `README.md` | 本文档 |

## 架构

```
麒麟虚拟机 (Kylin V11)
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  echo_client (C++/Qt5)          memory_echo_server.py       │
│  QLocalSocket ────── UDS ────── socket.socket(AF_UNIX)      │
│  ┌───────────────┐              ┌──────────────────────┐   │
│  │ 长度前缀 JSON  │  ────Send──▶ │ 解析 JSON，Echo 返回  │   │
│  │ (4B BE len +  │  ◀──Reply─── │                      │   │
│  │  JSON payload) │              └──────────────────────┘   │
│  └───────────────┘              $XDG_RUNTIME_DIR/kylin-     │
│                                  memory/memory.sock          │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

在麒麟虚拟机上执行：

```bash
# 一键全流程
bash os-agent-integration/echo/deploy_echo.sh full

# 或分步执行
bash deploy_echo.sh build     # 构建 C++ 客户端
bash deploy_echo.sh install   # 安装到 /opt/kylin-memory/echo/
bash deploy_echo.sh start     # 启动 Echo Server
bash deploy_echo.sh test      # 运行 UDS Echo 测试
bash deploy_echo.sh status    # 查看状态
bash deploy_echo.sh stop      # 停止服务

# KYSEC 授权
bash kysec_authorize.sh verify  # 最小授权
bash kysec_authorize.sh status  # 查看状态
bash kysec_authorize.sh restore # 恢复（回退后）

# 备份与回退
bash deploy_echo.sh backup      # 备份当前版本
bash deploy_echo.sh rollback    # 回退到最近备份
```

## IPC 协议

- **传输层**: Unix Domain Socket (SOCK_STREAM)
- **编码层**: 长度前缀 JSON
  - 4 字节大端无符号整数长度头
  - 后接 UTF-8 JSON 负载
- **Socket 路径**: `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`（fallback `/tmp/kylin-memory/memory.sock`）

### 请求示例

```
[00 00 00 B5]{"protocol_version":"1.0","request_id":"req_001","method":"memory.retrieve","deadline_ms":150,"payload":{"user_id":"local-user","query_text":"测试"}}
```

### 响应示例

```
[00 00 01 2C]{"protocol_version":"1.0","request_id":"req_001","status":"ok","echo":{"method":"memory.retrieve","received_payload":{...}}}
```

## 通过 SSH 远程测试

从开发机（Windows）通过 `test_echo_on_kylin.py` 自动化：

```bash
python os-agent-integration/echo/test_echo_on_kylin.py
```

## 完成标准

- [x] 代码编写完成（Python Echo Server + C++ Echo Client）
- [ ] 麒麟虚拟机构建通过（CMake + g++/Qt5）
- [ ] UDS 收发成功（3 个测试用例全部 PASS）
- [ ] systemd --user 安装与启动成功
- [ ] KYSEC 最小授权验证
- [ ] 备份与回退链路可用
- [ ] 证据截图/日志收集

## 关联文档

- 任务卡: `D1_OS_Agent_调用链与Hook_Spike_任务卡.md`
- 架构 SOP: 02 文档 §3.3 Gate 0, §4 UDS IPC
- 环境配置: 03 文档 §5 路径约定, §8 KYSEC
- Skill: kylin-memory-dev / kylin-ssh-connect