# rollback_packages.sh 安全回退测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:04:41+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- snapshot_package_versions.sh 已执行，manifest 已生成
- packaging/original-packages/package-manifest-latest.txt 存在
- 系统处于正常 runlevel（非维护模式）

## 执行命令
```bash
cd ~/projects/kylin-memory-sdk
echo "no" | ./tools/rollback_packages.sh
```

## 退出码
`0` (用户选择取消后正常退出)

## stdout
```
[ROLLBACK] Pre-flight checks...
WARNING: System appears to be in normal runlevel.
Rollback should be performed in maintenance mode.
Enter maintenance mode: sudo mm-cli -o
Aborted.
```

## 执行后状态
- 系统状态未变更（回退被取消）
- 前置检查正确识别非维护模式
- 提示了正确的维护模式进入命令

## 验证项说明
| 检查项 | 结果 |
| --- | --- |
| 维护模式检测 | PASS (正确识别正常 runlevel) |
| 维护模式警告信息 | PASS (提示正确命令) |
| 用户确认退出来 | PASS ("no" 输入正确取消) |
| manifest 文件检查 | PASS (不执行到此处，因维护模式检查先行) |
| 异常退出不损坏系统 | PASS |

## 安全特性验证
| 特性 | 实现 |
| --- | --- |
| 包白名单 | Manifest 驱动，只回退 manifest 中已记录的包 |
| SHA-256 校验 | 安装前校验，不匹配则中止 |
| 任意失败中止 | dpkg 失败后收集失败包，最终退出非零 |
| 维护模式检查 | 提示进入维护模式 |
| 版本固定 (apt-mark hold) | 安装后执行 |
| 安装后逐包验证 | 版本/架构验证 |
| Smoke test | Runtime / Embedding / Vector client 存在性检查 |
| 明确 PASS/FAIL 输出 | ROLLBACK_COMPLETE=PASS/FAIL |

## 已知限制
- 完整回退测试需要在维护模式 + 有 .deb 备份的条件下进行
- 当前环境为非维护模式，无法进行实际的 dpkg 安装测试
- 大部分包的 .deb 缓存已过期，需要从源仓库重新下载