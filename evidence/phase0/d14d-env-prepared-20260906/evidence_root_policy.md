# W5c — D14D 正式 evidence root 规则（冻结）

> task: `D14D_ENV_PREPARED` · 交付给 D13D I3d 与 D14D FORMAL L3 使用。

## 1. 命名规则（正式 run）

```text
<repo>/evidence/l3-kylin-vm/d14d_<UTC-RUN-ID>_<前7位SHA>/
```

- `<UTC-RUN-ID>`：ISO/compact UTC 时间戳，例如 `20260906T022719Z`；
- `<前7位SHA>`：被测代码/运行对象前 7 位 hex（正式 package run 为
  tested commit 前 7 位）；
- ENV_PREPARED 阶段 root（本目录）为准备证据，不占正式 run root 名额。

## 2. 创建与不可复用规则

```text
1. root 预创建且为空；先写 identity（snapshot/environment/dependency）
   再执行 Gate；
2. root 单次执行、不可复用：失败即停，保留原始失败日志，另开新 root；
3. 同一 run 内禁止覆盖/重跑同一 Gate；重试必须使用新 run-id 并登记原因；
4. 原始日志按字节保留，禁止手工删除/改写；
5. 历史 evidence root 永不改写（含本 ENV_PREPARED root）。
```

## 3. 权限规则

```text
1. evidence root 与文件：owner 可读写，group/other 只读（host: rwxr-xr-x /
   rw-r--r--；对应 JSON/log 不包含凭据，可入库）；
2. 正式 Seal/.sig、trust root PEM 属于 D13D/D13E 权限 Gate（system 权限
   Gate + owner 约束），本 root 不代管；
3. 含任何密钥/凭据/用户正文的采集必须脱敏后方可入库（本包无此类文件）。
```

## 4. 索引规则

```text
1. <repo>/evidence/index.yaml 只追加，禁止修改历史条目；
2. 正式 run 关闭 G9 前登记 ENV_PREPARED/历史条目时 status 只允许
   PREPARED / PARTIAL / NOT_RUN，不允许 L3_READY；
3. 每个条目必须含 source、date、reviewer、limitations、checksum_sha256。
```

## 5. 本包交接

- 本 ENV_PREPARED evidence root：
  `evidence/phase0/d14d-env-prepared-20260906/`
- D13D I3d 消费入口：本 root 的 `snapshot_identity.json`、
  `environment.json`、`dependency_identity.json` 与 `raw/`。

## 6. 边界

本规则是 evidence root 纪律的冻结口径；不授予 D14D PASS / D13D_FROZEN /
L3_READY / Release Gate。
