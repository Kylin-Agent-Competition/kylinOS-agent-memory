# env_check.sh 环境自检测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03:33+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- 项目已 Clone 至 `~/projects/kylin-memory-sdk`
- tools/env_check.sh 已可执行
- AI Runtime 依赖包已安装

## 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/env_check.sh
```

## 退出码
`0` (成功)

## stdout
```
WARNING: Repository root not at expected name 'kylinOS-agent-memory', found: /home/ZhouYifan/projects/kylin-memory-sdk
================================================
  Kylin Memory Environment Check
  Date: 2026-07-30 17:03:33
  Host: ZhouYifan-pc
================================================

--- 1. OS & Architecture ---
  [PASS] OS: Kylin V11
  [PASS] Architecture: x86_64

--- 2. Python ---
  [PASS] Python 3.12.3

--- 3. AI Runtime Packages ---
  [PASS] kylin-ai-runtime = 1.2.0.4-0k0.1
  [PASS] libkysdk-ai-common = 1.2.0.2-0k1.0
  [PASS] libkylin-coreai-embedding = 1.2.0.0-0k0.4
  [PASS] libkylin-ondevice-embedding-engine = 1.2.0.0-0k1.0
  [PASS] kylin-ai-abstract-models = 1.2.0.1-0k1.0
  [PASS] kylin-gte-base-model = 1.0.0.1-0k0.9
  [PASS] kytensor-client = 2.49.0.6-ok7k0.14
  [PASS] kytensor-server = 2.49.0.6-ok7k0.14
  [PASS] kytensor-python = 2.49.0.6-ok7k0.14
  [PASS] onnxruntime-backend = 1.0.1-ok6k0.1
  [PASS] libkysdk-vector-engine-client = 1.2.0.0-0k1.1
  [PASS] kylin-ai-vector-engine = 1.2.0.1-0k1.0

--- 4. Kaiming ---
  [PASS] Kaiming binary: /opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant
  [PASS] Chat database: /home/ZhouYifan/.config/kylin-aiassistant/kylin_aiassistant_database.db

--- 5. Runtime Paths ---
  [PASS] Runtime depends: /usr/lib/kylin-ai/depends
  [PASS] Model repository: /usr/share/kylin-ai/model-repository
  [PASS] App model repository: /opt/appdata/kylin-ai/model-repository

--- 6. Kytensor ---
  [PASS] Kytensor HTTP: 127.0.0.1:8000 (reachable)

--- 7. Project Directories ---
  [PASS] Project dir: /home/ZhouYifan/projects/kylin-memory-sdk
  [PASS] Memory dir: /home/ZhouYifan/.config/kylin-memory
  [PASS] Memory dir: /home/ZhouYifan/.local/share/kylin-memory
  [PASS] Memory dir: /home/ZhouYifan/.local/state/kylin-memory

--- 8. Build Tools ---
  [PASS] g++ available
  [PASS] cmake available
  [PASS] ninja available
  [PASS] git available
  [PASS] pkg-config available
  [INFO] python3-dev not found (may need to install development packages)
  [PASS] sqlite3 available

--- 9. KYSEC ---
  [PASS] kysec_set available

================================================
  Summary: 32 PASSED, 0 FAILED
================================================
```

## 执行后状态
- 所有 32 项检查通过，0 项失败
- 所有 AI Runtime 包版本确认已安装
- Kaiming 3.0.67 确认已部署
- Kytensor HTTP 端口 8000 可达
- KYSEC 工具可用
- WARNING 仅因仓库目录名非预期（kylin-memory-sdk vs kylinOS-agent-memory），不影响功能

## 已知限制
- python3-dev 未安装（在麒麟虚拟机上不影响运行时）
- 仓库目录名 kylin-memory-sdk 而非 kylinOS-agent-memory（警告非阻塞）