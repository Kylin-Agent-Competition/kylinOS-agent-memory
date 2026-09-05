# D14A 实施报告 v2（REWORK 修复后，2026-09-05）

> 对应 D14A 交接文档 + 台账 D14-A「L3 干净虚拟机发布回归」。
> 本报告为 D14A 第一阶段（发布包构建 + 发布链验证）完成记录；正式 L3 clean-VM
> 回归待 D14D 干净快照 + D13D 冻结环境就绪后执行。
> **状态：PACKAGE_IMPLEMENTATION_CANDIDATE**（按 D 主审 BLOCKER 5 口径；正式 L3 前不升 READY）。

---

## 1. REWORK 处置摘要

D 主审 5 个 BLOCKER 全部处置并重新验证：

| BLOCKER | 处置 | 验证 |
|---|---|---|
| B1 launcher/install_prefix 失效 | 整包安装到 `<install_prefix>`；`~/.local/bin` 做 symlink；unit 渲染 `ExecStart=<prefix>/bin/kylin-memory-server` | smoke：unit 正确渲染 + 服务从 prefix 启动 + socket 就绪 |
| B2 缺 Alembic 迁移 + env.py 重写错误 | install 前 `alembic upgrade head`；env.py 改为确定性重写（cwd 即 runtime/app）；构建时包内 migration smoke | migration head `20260902_add_memory_relation_conflict`；smoke PASS |
| B3 install/verify fail-closed 缺失 | install 校验 SDK 版本+SHA/manifest；wait socket/journal/restart；verify 校验 PID==MainPID/cmdline/SDK SHA/memory.embed | smoke 全链 PASS |
| B4 evidence 身份不一致 | 从最终 PR head `e3d4b9d` 重建；manifest.source_commit=完整 40 位 SHA | `source_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d` |
| B5 evidence 格式/语义 | 修复 JSON；补全 install/smoke/service identity/dependency audit；状态降级 | 16 个 evidence 文件全部合法 |

---

## 2. 完成情况总览

| 交接要求 | 状态 | 证据 |
|---|---|---|
| 冻结 release package contract | ✅ | `docs/day14/00_d14a_release_package_contract.md` |
| 构建正式发布包（无源码/无个人 venv 依赖） | ✅ | `dist/kylin-memory-a-d14a-0.1.0-d14a/`（87MB，3360 文件） |
| 消除个人开发目录依赖 | ✅ | launcher 可重定位；`ldd` 0 not-found；无 RPATH |
| 发布链（install→migrate→start→verify→restart→rollback） | ✅ | `package_smoke.sh` 全链 EXIT=0 |
| 真实 SDK 调用 | ✅ | `memory.embed` dim=768，非 fake；SDK SHA 校验 |
| 异常恢复（restart） | ✅ | restart 后 verify 全 PASS |
| 性能基线 | ⏳ | 单次 embed 205.5ms/restart 后 2.1ms；D13A 可比基准待 L3 |
| A READY 声明 | ⏳ | 待 D 主审 + L3 clean-VM + D13A 性能回归 |

---

## 3. 发布包身份（冻结，最终 head）

| 项 | 值 |
|---|---|
| package_name / version | `kylin-memory-a-d14a` / `0.1.0-d14a` |
| **source_commit** | **`e3d4b9d565e2c3c153973125b3c071225e1b9e4d`（= PR head）** |
| package_tar_sha256 | `15d79383f5aed05407d849cf5dfafe6ab2195a80ee42d987294747c6f74081ce` |
| manifest_sha256 | `18475655969b8fb6c88820d9e3ee94dc9c5e17a4e2c533b4cf65be46cb46ef22` |
| bridge_so_sha256 | `a271891238102d0299395284d486c2e5afdaa4494e6ab0d1ff51a2d2ab9d4db6` |
| SDK `.so` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` sha `028e7099…` |
| SDK 版本 | `libkylin-coreai-embedding 1.2.0.0-0k0.4` |
| runtime | `kylin-ai-runtime 1.2.0.4-0k0.1`（内部 1.3.0，PARTIAL 已知） |
| model | `ensemble-embd_gte-base_uint8-text`（dim=768） |

---

## 4. 发布链验证（`package_smoke.sh` 全链 EXIT=0）

```
package: /tmp/kylin-d14a-dist/kylin-memory-a-d14a-0.1.0-d14a
[install] manifest core files verified
[install] Alembic migration upgrade head -> alembic_version=20260902_add_memory_relation_conflict
[install] journal: Memory Service 就绪
[install] restart 验证 -> 服务 active, socket 就绪
[verify]  PASS: service active
[verify]  PASS: socket holder = MainPID
[verify]  PASS: cmdline 指向发布包 venv（无开发目录依赖）
[verify]  PASS: 真实 SDK memory.embed dim=768 (latency 205.5ms)
[verify]  PASS: embedding server SDK 实际加载 SHA 校验
[verify]  ALL PASS
[restart] verify 再次 ALL PASS (embed dim=768, latency 2.1ms)
[rollback] symlink/unit/install_prefix 清理完成
ALL PASS: install → migration → start → verify(real SDK) → restart → rollback
```

---

## 5. Evidence（`evidence/l3-kylin-vm/d14a_20260905/`）

```
environment.json  git_identity.json  package_manifest.json  SHA256SUMS
package_identity.json  real_sdk_smoke.json  sdk_model_identity.json
service_identity.txt  smoke.log  summary.json
dependency_audit/{ldd,readelf,path_scan}.txt
recovery/{service_restart,process_crash,stale_socket}.log
```

全部 JSON 合法；`tested_commit == PR head == manifest.source_commit == e3d4b9d…`。

---

## 6. 遗留事项（不阻塞发布包交付）

1. **D13A 可比性能回归**：正式 L3 上按 `scripts/run_day13a_benchmarks.sh` 复跑，budget 需 D 主审冻结。
2. **c8/c16 高并发**：归入正式 L3。
3. **正式 L3 clean-VM**：依赖 D14D 干净快照 + D13D 冻结环境；用本包 `systemd/install.sh` + `verify.sh`。
4. **状态升级**：PACKAGE_IMPLEMENTATION_CANDIDATE → READY_CANDIDATE 待 D 主审对发布链 smoke + evidence 确认。

---

*D14A REWORK 修复完成；发布链 smoke 全 PASS，evidence 已从最终 head 重建。*