# kysec_allow.sh KYSEC 放行安全边界测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03:50+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- kysec_set 命令可用
- 项目 build/ 目录尚未创建（无实际 ELF 二进制可放行）

## 测试用例 1: 无参数调用（帮助信息）

### 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/kysec_allow.sh
```

### 退出码
`1` (参数不足)

### stdout
```
Usage: tools/kysec_allow.sh <binary_path>

Restrictions:
  - Only ELF executables under /home/ZhouYifan/projects/kylin-memory-sdk/build/ are allowed
  - Symlinks are rejected
  - System directories (/usr, /bin, /lib, /opt) are rejected

Example: tools/kysec_allow.sh /home/ZhouYifan/projects/kylin-memory-sdk/build/test_embedding
```

## 测试用例 2: 系统路径拒绝（越界拒绝）

### 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/kysec_allow.sh /usr/bin/ls
```

### 退出码
`1` (安全拒绝)

### stdout
```
ERROR: Binary must be under /home/ZhouYifan/projects/kylin-memory-sdk/build/
  Given: /usr/bin/ls
```

## 执行后状态
- 系统 KYSEC 状态未变更
- 无日志写入（因安全检查在日志记录之前拦截）

## 安全边界验证
| 检查项 | 预期行为 | 结果 |
| --- | --- | --- |
| 无参数调用 | 显示 usage 并退出 | PASS |
| 系统路径 /usr/bin/ls | 拒绝，报错退出 | PASS |
| 符号链接拒绝 | 脚本中包含 realpath 检查和对比逻辑 | CODE PRESENT |
| 非 ELF 文件拒绝 | file -b 检查 ELF magic | CODE PRESENT |
| 非可执行文件拒绝 | -x 权限检查 | CODE PRESENT |
| build/ 目录限制 | 正则匹配 ^${REPO_ROOT}/build/ | PASS |
| 修改前状态保存 | kysec_get 记录 prev_state | CODE PRESENT |
| 操作日志 | 写入 kysec_allow.log (含 SHA-256/Commit/操作者/主机) | CODE PRESENT |
| 恢复命令提示 | 输出 sudo kysec_set -n exectl -v default 恢复命令 | CODE PRESENT |

## 已知限制
- 未对 build/ 目录下的实际 ELF 文件执行完整放行测试（build 目录尚无构建产物）
- kysec_set/kysec_get 需要 sudo 权限，脚本适当地使用了 sudo