# install_memory_service.sh 安装测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03:42+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- 项目已 Clone 至 `~/projects/kylin-memory-sdk`
- memory-service/main.py 占位入口文件存在
- packaging/systemd/kylin-memory.service 模板文件存在
- 之前已卸载（确保干净安装环境）

## 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/install_memory_service.sh
```

## 退出码
`0` (成功)

## stdout
```
WARNING: Repository root not at expected name 'kylinOS-agent-memory', found: /home/ZhouYifan/projects/kylin-memory-sdk
[INSTALL] Creating directories...
[INSTALL] Installing systemd service file...
[INSTALL] Reloading systemd user daemon...
[INSTALL] Enabling service...
Created symlink /home/ZhouYifan/.config/systemd/user/default.target.wants/kylin-memory.service → /home/ZhouYifan/.config/systemd/user/kylin-memory.service.
[INSTALL] Starting service...

[INSTALL] Verifying installation...
  [PASS] Unit file syntax valid
  [PASS] Python entry point found: /home/ZhouYifan/projects/kylin-memory-sdk/memory-service/main.py
  [PASS] Python module path accessible
  [PASS] Service is active
  [PASS] Service is enabled

=== Installation Complete ===
Service: systemctl --user status kylin-memory
Config:  ~/.config/kylin-memory/
Data:    ~/.local/share/kylin-memory/
Logs:    ~/.local/state/kylin-memory/
```

## 执行前状态
- 无 kylin-memory.service 已安装

## 执行后状态
- systemd user unit 已安装至 ~/.config/systemd/user/kylin-memory.service
- 服务状态: active (running), enabled
- Unit 文件中 __REPO_ROOT__ 已替换为实际路径 /home/ZhouYifan/projects/kylin-memory-sdk
- 目录已创建: ~/.config/kylin-memory/, ~/.local/share/kylin-memory/, ~/.local/state/kylin-memory/

## systemctl 验证
```
● kylin-memory.service - Kylin Memory Service
     Loaded: loaded (/home/ZhouYifan/.config/systemd/user/kylin-memory.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-07-30 17:03:45 CST; 2s ago
       Docs: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory
   Main PID: 386193 (python)
      Tasks: 1 (limit: 9405)
     Memory: 9.8M (peak: 9.8M)
        CPU: 105ms
     CGroup: /user.slice/user-1000.slice/user@1000.service/app.slice/kylin-memory.service
```

## 验证项说明
| 检查项 | 结果 |
| --- | --- |
| Unit 文件语法验证 (systemd-analyze verify) | PASS |
| Python 入口存在性 | PASS |
| Python 模块路径可访问性 | PASS |
| 服务 active 状态 | PASS |
| 服务 enable 状态 | PASS |

## 已知限制
- 仓库目录名 kylin-memory-sdk 而非 kylinOS-agent-memory（警告非阻塞）
- 占位 Python 入口 (asyncio.sleep) - 真实 Memory Service 待 D2 实现