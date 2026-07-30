# snapshot_package_versions.sh 版本快照采集测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03:38+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- AI Runtime 包已安装
- packaging/original-packages/ 目录存在

## 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/snapshot_package_versions.sh
```

## 退出码
`0` (成功)

## stdout
```

=== Package Snapshot Complete ===
  Passed:  13 packages captured
  Failed:  0 packages not found
  Manifest: /home/ZhouYifan/projects/kylin-memory-sdk/packaging/original-packages/package-manifest-20260730_170338.txt

NOTE: This script captures version metadata only.
To backup actual .deb files, use:
  mkdir -p /home/ZhouYifan/projects/kylin-memory-sdk/packaging/original-packages/deb-backup-20260730_170338
  for pkg in kylin-ai-runtime libkysdk-ai-common libkylin-coreai-embedding libkylin-ondevice-embedding-engine libkylin-ondevice-traditional-ai-engine-plugin kylin-ai-abstract-models kylin-gte-base-model kytensor-client kytensor-server kytensor-python onnxruntime-backend libkysdk-vector-engine-client kylin-ai-vector-engine; do
    find /var/cache/apt/archives -name "${pkg}_*.deb" -exec cp {} /home/ZhouYifan/projects/kylin-memory-sdk/packaging/original-packages/deb-backup-20260730_170338/ \;
  done
```

## Manifest 内容
```
# Kylin AI Runtime Package Manifest
# Generated: 2026-07-30T09:03:38Z
# Host: ZhouYifan-pc
# OS: Kylin V11
# Arch: x86_64
# Commit: 824a3c38fb885387a16029c20940156d97e6d68d
#
# Format: <package-name>|<version>|<architecture>|<sha256>|<status>|<cache-path>
#
kylin-ai-runtime|1.2.0.4-0k0.1|amd64|N/A|NOT_CACHED|
libkysdk-ai-common|1.2.0.2-0k1.0|amd64|N/A|NOT_CACHED|
libkylin-coreai-embedding|1.2.0.0-0k0.4|amd64|9b8d6b90a789aaf942a53bf6552589167d1b4743d4b688d41d310f64eab8a302|CACHED|/var/cache/apt/archives/libkylin-coreai-embedding_1.2.0.0-0k0.4_amd64.deb
libkylin-ondevice-embedding-engine|1.2.0.0-0k1.0|amd64|N/A|NOT_CACHED|
libkylin-ondevice-traditional-ai-engine-plugin|1.2.0.0-0k1.0|amd64|N/A|NOT_CACHED|
kylin-ai-abstract-models|1.2.0.1-0k1.0|amd64|N/A|NOT_CACHED|
kylin-gte-base-model|1.0.0.1-0k0.9|all|N/A|NOT_CACHED|
kytensor-client|2.49.0.6-ok7k0.14|amd64|N/A|NOT_CACHED|
kytensor-server|2.49.0.6-ok7k0.14|amd64|N/A|NOT_CACHED|
kytensor-python|2.49.0.6-ok7k0.14|amd64|N/A|NOT_CACHED|
onnxruntime-backend|1.0.1-ok6k0.1|amd64|8afea2ed2cd06e9e9949cca763cc06f6c711b3788522daf788fb6ac6c441041c|CACHED|/var/cache/apt/archives/onnxruntime-backend_1.0.1-ok6k0.1_amd64.deb
libkysdk-vector-engine-client|1.2.0.0-0k1.1|amd64|N/A|NOT_CACHED|
kylin-ai-vector-engine|1.2.0.1-0k1.0|amd64|cf9d9dde043ca8ba6cf7a7395add07cb0792459081a71d18ac57156fc7d3173f|CACHED|/var/cache/apt/archives/kylin-ai-vector-engine_1.2.0.1-0k1.0_amd64.deb
```

## 执行后状态
- Manifest 文件已生成: packaging/original-packages/package-manifest-20260730_170338.txt
- Latest 链接已更新: packaging/original-packages/package-manifest-latest.txt
- 13/13 包已采集版本信息
- 3/13 包的 .deb 有缓存 (CACHED)，10/13 缓存已过期 (NOT_CACHED)
- 未声称"包备份完成"，明确标注 NOTE: This script captures version metadata only

## 验证项说明
| 检查项 | 结果 |
| --- | --- |
| Manifest 包含 Package/Version/Architecture/SHA-256/Status/CachePath 六列 | PASS |
| Manifest 头包含生成时间/主机/OS/架构/Commit | PASS |
| 所有白名单包已采集 (13/13) | PASS |
| NOT_CACHED 状态正确标注 | PASS |
| latest 链接已创建 | PASS |
| 文档未声称"包备份完成" | PASS |

## 已知限制
- 大部分 .deb 缓存已过期（apt cache 自动清理），需要时需从源仓库重新下载
- 脚本只采集版本元数据，不备份实际 .deb 文件