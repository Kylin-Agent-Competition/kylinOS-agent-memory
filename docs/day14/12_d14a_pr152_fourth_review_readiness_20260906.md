# PR #152 第四轮复审就绪清单（对 PR head `02ca7a0`）

> 状态：`PREPARED_FOR_REVIEWER`。本文件是给 D 主审的复审材料，不是 D 主审结论；
> 每项“ADDRESSED”仅表示 PR head 源码/本地 L1 已满足，不表示已经 D 主审批准，
> 也不表示真实麒麟 VM 证据存在。
> 2026-09-06 仲裁已回填（D-01~D-14），见
> [14_d14a_arbitration_record_20260906.md](14_d14a_arbitration_record_20260906.md)；
> Ducknesses 的实际第四轮 review 仍未发生，本清单不替代。

## 1. 当前复审对象

- PR #152 head：`02ca7a0a6370034f0918ea45809c7fcd2c1cd0f2`
- 最新评审：Ducknesses 第三轮 REWORK（针对 `26e8c00`，2026-09-05）
- Repository Baseline Check：SUCCESS（run 34005247687，2026-09-06T01:59Z）
- 本会话 WSL L1 复跑：`77 passed in 31.87s`（详见
  `evidence/l1/pr152_head_02ca7a0_packaging_l0_20260906.log`）

## 2. 第三轮“下一轮最低通过条件”逐项状态

### 条件 1：venv/console-script 可重定位，删除构建 venv 后 migration smoke

状态：**ADDRESSED（源码 + L1 实测）**

- `build_release_package.sh`：打包阶段扫描并删除 `runtime/python/bin` 中含构建期
  venv 绝对路径的常规文件，二次残留扫描 fail-closed，删除 `/tmp/kylin-d14a-build-venv`
  后才执行包内 `python -m alembic` migration smoke；
- `test_d14a_relocatable_runtime.py` 覆盖静态入口、残留扫描与删除构建 venv 后的
  行为验证。

### 条件 2：最终 packaging head 的 package/hash/真实 VM evidence；contract 溯源不再漂移

状态：**PARTIAL——溯源已收口，runtime evidence 明确标为 stale，未经新 VM 重跑**

- contract v4（`docs/day14/00_d14a_release_package_contract.md`）已建模四类身份：
  `source_commit`（`5424d28e…`，声明基线）、`tested_runtime_commit`
  （`e3d4b9d…`）、`evidence_commit`（`68bb8f7…`）、`current_pr_head`
  （执行时 `git rev-parse HEAD`，不落库固定 SHA）；
- contract 明确当前 HEAD 相对 `tested_runtime_commit` 为
  `RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED`，需要正式“重新打包 → 重算 hash →
  重跑真实 VM”并回填后方可宣称一致；
- `docs/day14/test_d14a_release_provenance.py` 验证 head 漂移三分类；
- 因此该条件**尚未关闭**：等待 D14D 选定 `tested_commit` 后的正式 VM run。

### 条件 3：包完整性三向闭合 + FULL_COMMIT + 冻结 version/source identity

状态：**ADDRESSED（源码 + L1 实测）**

- `systemd_install.sh`：`SHA256SUMS` 语法/穿越防护、全量 sha256+size 校验、
  `manifest.files == SHA256SUMS == 磁盘实际文件集` 三向闭合、manifest/VERSION 与
  冻结 package/SDK/source identity 精确比对；
- builder 将短 SHA 规范化为 40 位 `FULL_COMMIT` 写入 manifest；
- `test_d14a_package_integrity.py` 覆盖 tamper/delete/extra/mismatch 等失败路径。

### 条件 4：BLOCKER C — runtime/model dependency Gate 口径

状态：**ADJUDICATED（D-03 = HANDOFF_REQUIRED）**

- contract §3/§6bis 已统一为“SDK 全量 fail-closed；runtime/model HANDOFF_REQUIRED”，
  并注明 runtime/model 版本仅为参考值，不伪造/不补写；
- 正式 D14D G0 将采集 `dpkg-query -W` 身份与相关 `.so`/包 SHA，回填后升版；
- 本条件未“解除”，但已不再阻塞 packaging 代码线收敛与第四轮复审范围。

### 条件 5：verify holder/embed PID 收紧 + smoke 默认 prefix

状态：**ADDRESSED（源码 + L1 实测）**

- `systemd_verify.sh`：`--embed-pid` 必填，socket holder PID 无法解析或 !=
  MainPID 均 fail-closed，UID 一致只作附加防线；实际加载 SDK SHA 无条件校验；
- `package_smoke.sh`：`--prefix` 与 `--expect-source-commit`（40 位）显式必填，
  clean / upgrade-rollback 两场景均不回落真实用户默认前缀；
- `test_d14a_verify_smoke.py` 覆盖缺失/解析失败/PID 不等及 smoke 参数缺失负向。

## 3. 仍阻塞第四轮放行的缺口

1. Ducknesses 尚未实际提交第四轮 review；
2. `02ca7a0`/收敛 head 无真实麒麟 V11 clean-VM runtime evidence（contract 已如实标
   stale；正式 G0–G9 等待 D-08 D13D 闭合后执行）；
3. D-05 已裁决正式 package version 固定 `0.1.0-d14a`，`EXPECT_PACKAGE_VERSION`
   与契约保持一致，无需再作版本决策；
4. 本地收敛产物（含本清单、仲裁记录、L0/L1 日志）尚未推送/同步至 PR #152 分支
   （D-13 执行待用户授权）。

## 4. 建议给 D 主审的决策点

- [x] BLOCKER C = HANDOFF_REQUIRED（D-03，已回填）；
- [x] 接受 contract v4 的“RUNTIME_EVIDENCE_STALE + 四身份建模”并升 FROZEN（D-04，已回填）；
- [x] 接受第四轮只审 packaging 代码/L1，真实 VM 证据由 D14D 选定 `tested_commit`
      后另行执行（D-02，已回填）；
- [ ] Ducknesses 实际第四轮 review（外部执行，本清单无法替代）。
