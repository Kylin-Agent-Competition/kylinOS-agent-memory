# D13D Phase 3 准备与交接清单

> **Scope: `PREPARATION / NON-FORMAL`**
>
> 本文件只覆盖 Reviewer E 在 PR #160 中授权的 Phase 3 preparation / handoff 工作。
> 授权引用：PR #160 comment `5564455955`，结论 `APPROVE_PHASE3_START`。
> 授权基线：`feat/d13d-i3b-completion @ 18cb28e4322c9121a917b83c3da5a8d01431a5f9`。
>
> 本文件不授权，也不得用于宣称：
> `P0-I3b-completion = COMPLETE`、PR #160 final `APPROVE`、
> `P0-I3d = READY_TO_START`、final/formal `tested_commit` 已冻结、
> 正式 VM 17 raw 已产生、Review Seal / Execution Seal / attestation、
> Runner Gate 0-10、`D13D_FROZEN` / `HOST_VERIFIED` / `FORMAL PASS`。

## 1. 双层状态

### 当前允许

- Phase 3 freeze / execution checklist 与 handoff 计划；
- 新 evidence root / manifest / checksum / provenance 结构准备；
- 隔离 VM 的候选部署、preflight、环境 / Trust Root / 服务 / 数据库只读复核；
- G5/G6 的真实 provider、SDK headers、bridge compile/link/smoke 等前置闭合；
- 其他明确标注为 `PREPARATION / NON-FORMAL` 的准备性工作。

### 当前禁止

- 选择或宣称 final/formal `tested_commit`；
- 执行正式 VM 17 raw；
- 生成 Review Seal / Execution Seal / attestation；
- 运行正式 Runner Gate 0-10；
- 标记 `D13D_FROZEN` / `HOST_VERIFIED` / `FORMAL PASS`；
- 修改 Dataset、Gold、Threshold、Runner、冻结 IPC / Schema / 错误码。

## 2. 目标

在不提前进入正式执行 Gate 的前提下，把 Phase 3 所需的下列准备件先闭合：

1. 唯一 `PREPARATION / NON-FORMAL` evidence root 结构与校验清单；
2. 隔离 VM 的候选部署、preflight、Trust Root、服务、数据库只读复核命令；
3. G5/G6 的真实运行前置闭合计划与证据模板；
4. 正式执行前的 Phase 2 交接缺口与责任分工。

## 3. Phase 3 preparation evidence root 契约

Phase 3 准备阶段使用独立的 `PREPARATION / NON-FORMAL` evidence root，
不得复用或伪装为正式 execution evidence root。建议命名：

```text
d13d_phase3_prep_<UTC_RUN_ID>/
  README.md
  environment_preflight.json
  vm_identity.json
  deployment_preflight.json
  runtime_versions.txt
  service_unit.txt
  trust_root_check.json
  commands.log
  SHA256SUMS
```

约束：

- `README.md` 必须明确写入 `PREPARATION / NON-FORMAL`；
- `environment_preflight.json` 不得携带 `D13D_FROZEN`、`FORMAL PASS`、
  `HOST_VERIFIED` 等正式闭环字段；
- `SHA256SUMS` 只覆盖当前准备目录内文件；
- `commands.log` 记录实际命令、stdout / stderr、exit code 与 UTC 时间；
- 任一必填项缺失、哈希不匹配、工作树不干净或部署 SHA 不一致时，
  本 evidence root 只能标记 `BLOCKED`，不得进入正式执行流程。

## 4. VM / 环境只读 preflight 清单

以下命令用于准备阶段采集，不得作为正式证据。

```bash
git rev-parse HEAD
git status --porcelain
cat /etc/kylin-release
uname -a
systemctl --user is-active kylin-memory.service
systemctl --user cat kylin-memory.service
stat -c '%a %n' "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"
sqlite3 --version
python3 --version
sha256sum \
  evaluation/d13e/D13E_FORMAL_TESTSET_V1.jsonl \
  evaluation/d13e/D13E_GOLD_V1.jsonl \
  evaluation/d13e/D13E_FORMAL_THRESHOLDS_V1.json \
  evaluation/d13e/D13E_FORMAL_MANIFEST_V1.json \
  scripts/run_d13e_formal_eval.py
```

Trust Root 只读检查：

```bash
sudo -n stat -c '%U %G %a %n' /etc/kylin-memory/trust \
  /etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json \
  /etc/kylin-memory/trust/d13e-review-public.pem \
  /etc/kylin-memory/trust/d13d-execution-public.pem
sudo -n find /etc/kylin-memory/trust -maxdepth 1 -type l -print
sudo -n sha256sum /etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json \
  /etc/kylin-memory/trust/d13e-review-public.pem \
  /etc/kylin-memory/trust/d13d-execution-public.pem
```

任一路径不存在、是 symlink、owner 不是 root、或 group / other 可写时，
只读 preflight 必须记录为 `BLOCKED`，不得伪造通过。

## 5. G5 / G6 前置闭合

### G5 真实 provider 前置

目标：

- 在麒麟 VM 的 isolated runtime binding 中注入真实 Embedding 与 Vector provider；
- pre-delete probe 在 FTS 与 Vector 双通道都命中；
- vector delete / rebuild 证据可复核。

准备阶段允许：

1. 只读确认 VM 上 Embedding / Vector 相关动态库、包版本、socket 路径；
2. 编写真实 provider 注入桥与 smoke 脚本，但不得写入正式 evidence；
3. 在独立隔离目录中试运行，不生成 formal raw。

准备阶段禁止：

- 用 `FakeVectorProvider` / deterministic embedding 宣称 G5 完成；
- 把 FTS-only L1 外推为 Vector 双通道完成；
- 把宿主 runtime 证据写成非正式 VM 准备证据。

### G6 SDK `0k1.1` headers / bridge 前置

目标：

- 取得与 SDK `0k1.1` 匹配的 `Database.h` 与依赖头文件；
- 编译 / 链接 `vector_bridge_cli`；
- 完成真实 smoke 并记录 compile / link / run provenance。

准备阶段允许：

1. 只读检查 `/usr/lib/x86_64-linux-gnu/libkysdk-vector-engine-client.so.1`
   的包版本、`nm -D` 导出符号与相关头文件路径；
2. 编写 build / smoke 脚本与 provenance 模板；
3. 在隔离构建目录内编译、链接、试运行。

准备阶段禁止：

- 复用 `0k0.7` binary / header 冒充当前 ABI；
- 把 compile / link 成功写成向量语义通过；
- 把 smoke 结果写入正式 evidence root。

## 6. 执行顺序

1. 固化本 checklist；
2. 建立 Phase 3 `PREPARATION / NON-FORMAL` evidence root；
3. 采集 VM / 部署 / Trust Root 只读 preflight；
4. 采集 G5 / G6 现场状态，确认是否具备真实 provider / SDK headers；
5. 若具备，进行 isolated 试运行并归档为准备证据；
6. 汇总 Phase 3 preparation handoff 报告；
7. 待 PR #160 final APPROVE + merge 后，再按 26_ 正式状态机推进 Phase 3。

## 7. 交接输入

进入正式 Phase 3 前，仍必须完成：

1. Forget 5/5 real preview / execute / consumer ACK / realtime / rebuild / receipt；
2. Safety-001 状态在 PR Body 与 26_ 中统一为带证据的单一结论；
3. 最终 exact HEAD 的 Phase 2 regression / Runner contract regression /
   Gold-isolation audit / CI 全绿；
4. `P0-I3b-completion = READY_FOR_REVIEW`；
5. Reviewer E final APPROVE；
6. PR #160 merge 并记录 `I3B_COMPLETION_MERGE_SHA`；
7. `P0-I3d = READY_TO_START`；
8. 再由 D 主审从最新干净 main 选择完整 40 位 `tested_commit`。

在上述事项完成前，本 checklist 不得升级为 formal execution / freeze Gate。

## 8. 2026-09-07 preparation 现场结果

VM 环境已在候选 `feat/d13d-i3b-completion @ c462c4205dc79f6931954abe601de7e7fa883dbf`
上部署并复核：

- `kylin-memory.service` = `active`；
- IPC socket 权限 = `0600 kylin-agent:kylin-agent`；
- Alembic schema 迁移通过，SQLite DB 文件权限为 `0600`；
- Vector client 包 = `libkysdk-vector-engine-client 1.2.0.0-0k1.1`。

G5 preparation：当前源码的 `kylin_embedding` pybind11 模块已在 VM 上从源码编译，并连
接真实 SDK 完成一次 embed smoke。默认模型为
`ensemble-embd_gte-base_uint8-text`，输出 768 维，L2 norm≈1.0。准备证据位于
`evidence/phase3-prep/d13d_g5_embedding_smoke_20260907/`，仍为
`PREPARATION / NON-FORMAL`。这不等于 G5 formal closure，也不等于 Vector 双通道 5/5 完成。

G6 preparation：`0k1.1` headers 已从本地 dev 包解包；`vector_bridge_cli` 已用这些 headers
在 VM 上编译/链接，并完成真实 engine smoke（create → insert → search hit → delete →
search miss → drop）。准备证据位于
`evidence/phase3-prep/d13d_g6_bridge_smoke_20260907/`，仍为
`PREPARATION / NON-FORMAL`。正式执行前必须在 final tested_commit 的冻结 evidence root 上重放并独立复核。

Preflight：`evidence/phase3-prep/d13d_phase3_prep_20260907_c462c42_g5smoke/`
如实保持 `BLOCKED`。阻塞点是 Trust Root 目录尚未安装，以及运行时包本身不含 headers；
后者由本地 dev 包解包的准备路径解决，但正式 preflight 仍应独立记录这一差异。
