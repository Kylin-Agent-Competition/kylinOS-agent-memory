# W5 Trust Root candidate / 重验证入口（ENV_PREPARED）

> 依据：D13E formal eval 第 3/4 轮返工（`docs/day13/05_d13e_formal_eval_worklist_20260905.md`）。

## 1. Candidate 形态

```text
D13E_TRUST_ROOTS_V1.json
+ Reviewer D 与独立 Execution Reviewer 的 public PEM（两个）
```

Trust Root 目录与文件已实现系统权限 Gate（symlink/owner/group-other 写拒绝），
正式 Runner 通过冻结 `--trust-roots` 契约使用。

## 2. 本机状态

- 实际 PEM / `D13E_TRUST_ROOTS_V1.json` 由 D13E/D Reviewer 侧持有与签署
  （W6），本工作区不代持、不伪造。
- 重验证入口（可执行检查）：
  - 目录/文件 owner 与权限；
  - `D13E_TRUST_ROOTS_V1.json` 与两个 public PEM 的 SHA-256 锚定；
  - 正式双 Seal（`.sig`）使用该 trust root 验签；
  - symlink / owner / group-other 写拒绝负测。

## 3. 边界

Trust Root **重验完成 + 授权**属于 D13D I3d / W6 正式运行阶段；本文件只登记
candidate 与入口，不构成 Trust Root 已冻结或 Seal 已签发。
