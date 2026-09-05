# D14A 实施报告（2026-09-05）

> 对应 D14A 交接文档（`D11E_A轨...` 系列）与台账 D14-A「L3 干净虚拟机发布回归」。
> 本报告为 D14A 第一阶段（发布包构建 + 真实 SDK 验证）完成记录；正式 L3 clean-VM
> 回归待 D14D 干净快照 + D13D 冻结环境就绪后执行。

---

## 1. 完成情况总览

| 交接要求 | 状态 | 证据 |
|---|---|---|
| 冻结 release package contract | ✅ | `docs/day14/00_d14a_release_package_contract.md`（FROZEN_DRAFT v1） |
| 构建正式发布包（无源码/无个人 venv 依赖） | ✅ | `dist/kylin-memory-a-d14a-0.1.0-d14a/`（88MB，1199 文件） |
| 消除个人开发目录依赖 | ✅ | launcher 以 `$0` 推导 prefix；`ldd` 0 not-found；无 RPATH |
| 真实 SDK 调用 | ✅ | `memory.embed` dim=768，l2=1.0，非 fake |
| 异常恢复（restart） | ✅ | socket 重建 + SDK 重载 + embed/health 正常 |
| 性能基线 | ⏳ | 单次 embed 105.3ms；D13A 可比基准待 clean-VM 正式执行 |
| 无残留依赖 | ✅ | 包内自包含（app/bridge/python venv/migrations） |
| A READY 声明 | ⏳ | 待 D 主审 + L3 clean-VM + D13A 性能回归确认 |

---

## 2. 发布包身份（冻结）

| 项 | 值 |
|---|---|
| package_name / version | `kylin-memory-a-d14a` / `0.1.0-d14a` |
| source_commit | `c1fdc528f0d68e0d534cae574f0d765bc0a2600f`（release 分支） |
| package_tar_sha256 | `e6e5716aa942a842a2fba24e08578bb4fe24989f0655ef353269d82c18519705` |
| manifest_sha256 | `92884d6f2c96b6ad9179245c48eda089d4d27148956728c9f6f94b630b5ca11a` |
| bridge_so_sha256 | `a271891238102d0299395284d486c2e5afdaa4494e6ab0d1ff51a2d2ab9d4db6` |
| SDK `.so` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` sha `028e7099…` |
| SDK 版本 | `libkylin-coreai-embedding 1.2.0.0-0k0.4` |
| runtime | `kylin-ai-runtime 1.2.0.4-0k0.1`（内部自报 1.3.0，PARTIAL 已知） |
| model | `ensemble-embd_gte-base_uint8-text`（dim=768, ondevice） |

---

## 3. 消除开发目录依赖（对照 A14-B02 关闭标准）

- **源码 checkout 依赖 = NONE**：`runtime/app` 为 memory-service 模块级复制，不含 .git/docs/tests。
- **个人 venv 依赖 = NONE**：`runtime/python` 为包内独立 venv（python3.12 + requirements）。
- **硬编码开发者路径 = NONE**：launcher 以 `$0` 推导 prefix；migrations/env.py 已改为包内相对路径。
- **动态库**：`ldd` 0 not-found；`readelf` 无 RPATH/RUNPATH。
- **构建脚本**：`packaging/release/build_release_package.sh`（Git 身份 Gate + 前置依赖校验 + manifest/SHA256SUMS 生成）。

---

## 4. 真实 SDK 验证（A14-B03 关闭标准）

- **SDK 实际加载**：`/proc/<PID>/maps` 命中 `libkysdk-coreai-embedding.so.1.0.0`，SHA-256 与声明一致。
- **真实调用**：`memory.embed` → `status=ok, dimension=768, vector_len=768, l2_norm=1.0`。
- **health**：`service=ok, provider=ready, bridge_loaded=True, sdk_missing=False`。
- **模型**：`ensemble-embd_gte-base_uint8-text`（SDK 默认加载）。
- **fake/mock = false**。

---

## 5. 异常恢复（A14-DoD R1）

- **Service restart**：终止 embedding server → nohup 重启 → socket 重建（新时间戳）→
  `memory.embed` ok（dim=768）+ `memory.health` ok（bridge_loaded=True）。
- **无 stale socket**：重启后 socket 为新建（旧 socket 被删除）。
- **无重复残留进程**：重启后 procs=1。

---

## 6. 遗留事项（不阻塞发布包交付）

1. **D13A 可比性能回归**：正式 clean-VM L3 上按 `scripts/run_day13a_benchmarks.sh` 复跑，
   与 D13A 账本对照（P50/P95/P99、吞吐、error rate），budget 需 D 主审冻结。
2. **c8/c16 高并发**：D14A 本轮未执行，归入正式 L3。
3. **index backlog / IPC benchmark**：发布包已含 D13A 链，正式 L3 一并复跑。
4. **正式 L3 clean-VM**：依赖 D14D 干净快照 + D13D 冻结环境；届时用本包 `systemd/install.sh`
   安装并跑 `systemd/verify.sh`，与 D14B 共享。

---

## 7. 交接包（给 B/D）

见 `docs/day14/00_d14a_release_package_contract.md` §18；发布包本体在
`dist/kylin-memory-a-d14a-0.1.0-d14a/`（本 VM 构建，clean-VM 用 tar 传输）。

---

*D14A 阶段一完成；正式 L3 回归待 D14D/D13D 冻结输入后推进。*