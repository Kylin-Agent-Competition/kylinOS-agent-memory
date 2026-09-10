# D15D 锁定后一致性核验 Runbook（草稿）

> 日期：2026-09-06
> 目的：在最终 Release Commit 与提交包产生后，逐项核验“main ↔ 发布包 ↔ 版本清单 ↔ D14D 证据 ↔ E 签署”一致。
> 约定：所有检查 fail-closed——任一检查失败立即停止，保留原始输出，不开新结论、不改旧记录。
> 本文件先于最终输入存在；`release_commit`、包路径、证据根以 `<post-D14D-formal>` 占位，正式执行时由 D15D 重建版本后填入。

## 1. 输入变量

```bash
RELEASE_COMMIT="<post-D14D-formal: 最终 main/release commit，40 位>"
REPO_DIR="<E:\Kylin-memory-dev\main 或等价干净 checkout>"
PACKAGE_TAR="<重建发布包 tar 绝对路径>"
PACKAGE_DIR="<tar 解包目录绝对路径>"
VERSION_MANIFEST="<D15D_VERSION_MANIFEST.json 绝对路径>"
D14D_EVIDENCE_ROOT="<D14D 正式 G0–G9 evidence root>"
```

任一路径为空、`RELEASE_COMMIT` 非 40 位小写 hex、包缺失 manifest/SHA256SUMS/VERSION 时，直接非零退出。

## 2. 一致性检查表

| # | 检查 | 命令/断言（Linux/WSL 口径，Windows 执行时等价转换） | 通过条件 |
| --- | --- | --- | --- |
| C1 | Release Commit 与 main 关系 | `git -C "$REPO_DIR" rev-parse HEAD`；`git -C "$REPO_DIR" status --porcelain`；`git merge-base --is-ancestor "$RELEASE_COMMIT" main` | HEAD == RELEASE_COMMIT；工作树空；RELEASE_COMMIT 是 main 祖先 |
| C2 | 锁定后 main 无发布路径漂移 | `git -C "$REPO_DIR" diff --name-only "$RELEASE_COMMIT" main -- packaging/ memory-service/ cpp-bridge/ migrations/ config/ docs/day14/00_d14a_release_package_contract.md` | diff 为空（或仅明确批准的 docs/evidence 且已在版本清单登记） |
| C3 | 包内 install 脚本一致 | 见下方“C3–C6 命令块”（`assert_same`） | 两值相等 |
| C4 | 包内 uninstall 脚本一致 | 同上 | 两值相等 |
| C5 | 包内 verify 脚本一致 | 同上 | 两值相等 |
| C6 | 包内 unit 一致（安装前） | 同上 | 两值相等 |
| C7 | 安装后 unit 渲染 | `grep ExecStart "$HOME/.config/systemd/user/kylin-memory.service"` | 值为 `<INSTALL_PREFIX>/bin/kylin-memory-server`，且不含 `%h/.local/bin` |
| C8 | 包完整性 | 在 `$PACKAGE_DIR` 下 `sha256sum -c SHA256SUMS`；并校验 manifest.source_commit == RELEASE_COMMIT、package_version == `0.1.0-d14a` | 全部 PASS，identity 一致。若本地因宿主缺 `/usr/bin/python3.12` 导致仅三个包内 `runtime/python/bin/python*` symlink 无法 open/read，且 tar SHA-256 与 D14D G2 已验证的 frozen tar 完全相等、其余 regular files 全部 OK，可记录为 `PASS_INHERITED_FROZEN_TAR_IDENTITY`；不允许把其他 mismatch、missing file 或 rebuild 掩盖为环境 note |
| C9 | 版本清单与包一致 | `python -m json.tool "$VERSION_MANIFEST"` 后逐项断言 manifest/tar/SHA256SUMS/脚本/unit SHA 相等 | 无任何不一致字段 |
| C10 | VERSION_MAP/宿主身份一致 | 版本清单中 SDK/runtime/model 与 D14D G0 采集（`dpkg-query -W` + `.so`/包 SHA）相等；VERSION_MAP 参考值不冲突 | 正式 G0 回填后无 `HANDOFF_REQUIRED` 遗留（遗留则结论最高 PARTIAL） |
| C11 | D14D 证据绑定 | `$D14D_EVIDENCE_ROOT` 存在，G0–G9/checksums/index 存在，其中 release_commit/tar/manifest 与 C1/C8 相等 | 证据链完整且一致 |
| C12 | 提交包一一对应 | 提交包文件清单（tar、解包目录、版本清单、契约、证据索引）与 main 锁定清单比较：`comm -3 <expected> <actual>` | 无多余、无缺失 |
| C13 | 签署 Gate | Reviewer E APPROVE 记录在 D15D PR/材料上；任务卡升 `SIGNED_PREPARED`；台账 H→I→J 顺序可核验 | E 签署存在；D 轨无自签 |

## 3. 输出与证据布局

```text
docs/day15/
  D15D_VERSION_MANIFEST.json      # release_commit/package hash/scripts+unit SHA/宿主版本/evidence 引用
evidence/d15d-lock/<run-id>/      # 正式锁定证据（入 PR 阶段）
  checksums.txt
  consistency_*.log               # C1–C13 每项命令/stdout/stderr/exit code
  gate_matrix.json
  summary.json
  E_SIGN_OFF.md
```

## 4. 失效与处置

- C1/C2 失败：main 已前进且触及锁定路径 → 重建 release_commit/包，不沿用旧包。
- C3–C8 任一失败：包与 main 不一致 → 从 release_commit 重建包、重算 hash、重跑全部检查。
- C9/C10 失败：版本清单或宿主身份与包/证据矛盾 → 修正清单后重新会签。
- C11/C12 失败：D14D 证据或提交包不完整 → 补全材料或重跑，禁止缺件签署。
- C13 未通过：D15D 结论最高 `PENDING_E_SIGN / PARTIAL`，不写 READY/LOCKED。

### C3–C6 命令块（shell 管道按原文执行，禁止手工改值）

```bash
assert_same() {
  local src_path="$1"
  local pkg_rel="$2"
  local want got
  want="$(git -C "$REPO_DIR" show "$RELEASE_COMMIT:$src_path" | sha256sum | awk '{print $1}')"
  got="$(sha256sum "$PACKAGE_DIR/$pkg_rel" | awk '{print $1}')"
  [ "$want" = "$got" ] || { echo "MISMATCH: $src_path"; exit 1; }
  echo "PASS: $src_path -> $pkg_rel ($want)"
}
assert_same packaging/release/systemd_install.sh   systemd/install.sh
assert_same packaging/release/systemd_uninstall.sh systemd/uninstall.sh
assert_same packaging/release/systemd_verify.sh    systemd/verify.sh
assert_same packaging/systemd/kylin-memory.service systemd/kylin-memory.service
```
