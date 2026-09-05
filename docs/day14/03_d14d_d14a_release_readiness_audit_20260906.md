# D14D P1：D14A 发布包可用性审计

## 范围与结论

- 审计对象：`kylin-mem/release/D14A-clean-vm-package@e3d4b9d565e2c3c153973125b3c071225e1b9e4d`。
- 审计日期：2026-09-06。
- 审计类型：静态实现审计。未在本轮重新执行麒麟 VM 安装或 SDK 测试，不能代替 L3 证据。
- 初始结论：`NOT_READY_FOR_D14D_INTEGRATION`。该分支的 package-only SDK 冒烟是有价值的
  准备证据，但初始脚本无法满足 D14D 的完整性、可回退和升级 Gate，且不包含 D13E 主线。
- 整改状态：`fix/d14a-release-lifecycle@9536746` 已修复 P1-01 至 P1-04，并补充安装失败清理与
  替换 unit/服务/路径的所有权守卫与 tar/manifest 身份绑定；本地发布代码候选 `35b4804` 已包含这些修复和 L0 守卫测试。
  该候选尚未独立审查或选定为最终被测提交，故 D14D 总体结论仍为 `NOT_READY_FOR_D14D_INTEGRATION`。

## 已确认项

| 项 | 证据 | 结论 |
| --- | --- | --- |
| 发布包身份 Gate | builder 要求 `--source-commit == HEAD` 且 worktree clean | 设计方向正确；最终集成提交重新构建时可复用 |
| 不依赖开发目录 | launcher 由自身路径推导 prefix；verify 检查 gateway cmdline | 可作为 D14D G2/G3 的输入，但需实测 |
| 真 SDK 验证设计 | verify 可检查 embedding server `/proc/<PID>/maps`、SDK hash、`memory.embed` dim=768 | 可作为 D14D G4 的候选实现，但需实测 |

## 阻断问题

| ID | 级别 | 证据 | 风险 | D14D 解除标准 |
| --- | --- | --- | --- | --- |
| D14D-P1-01 | Critical | install 只校验三个硬编码文件，未执行 `sha256sum -c SHA256SUMS`；bridge 文件名固定为 `cpython-312` | package 中的其他应用、迁移、unit 或脚本可被篡改而继续安装；Python 版本变化会产生错误或 KeyError | 安装前以 manifest 和 `SHA256SUMS` 对所有受管普通文件 fail-closed 校验；从 manifest/实际唯一 glob 获取 bridge 路径，不硬编码 ABI 后缀 |
| D14D-P1-02 | Critical | install 覆盖 unit 前没有创建 `$UNIT_DST.bak.*`；后续时间戳检查不会创建备份 | rollback 可能删除用户既有 `kylin-memory.service`，无法恢复部署前状态 | 安装前对现有 unit、symlink、prefix 和 service enable/active 状态建立带 hash 的回滚清单；rollback 只能按清单恢复 |
| D14D-P1-03 | Critical | uninstall 与 smoke 对 `INSTALL_PREFIX` 使用无保护 `rm -rf`；smoke 也删除 socket | 路径误配可导致用户目录中不属于 D14D 的数据或运行资源被删除，且没有白名单/realpath 边界 | 仅允许删除本次 run 创建且在 D14D 专用允许根下、realpath 已验证的路径；socket 仅在确认 owner/PID/namespace 后处理；默认保留数据目录 |
| D14D-P1-04 | High | smoke 在 `set -u` 下执行 `INSTALL_PREFIX="$INSTALL_PREFIX"`，未传 `--prefix` 会立即退出；失败路径没有 trap 清理 embedding server | 默认示例命令不可运行，失败时可能遗留进程/socket，污染干净快照 | 使用确定的默认隔离 prefix；添加 `trap` 清理本脚本创建的进程/临时 socket，且清理失败应记录 |
| D14D-P1-05 | High | package contract 规定升级，但脚本只提供 install/rollback，无第二包、版本顺序、数据保留或 migration rollback 契约 | D14D G7 无法执行，不能宣称完成完整发布生命周期 | 提供经批准的 upgrade package、from/to identity、数据保留/清除策略、前后 schema/version 检查和失败回退流程；否则 G7 必须 `NOT_RUN` |
| D14D-P1-06 | Critical | D14A head 不包含 `kylin-mem/main@4a32e5c`（D13E 门禁），其 package contract 固定 source commit `5424d28` | D13D、D14A、D14B 不会绑定同一被测实现 | 在一个经过审查的最终集成 SHA 上重建 D14A；D13D `FROZEN`、包 manifest、VM HEAD 和 D14B 输入必须均使用该 SHA |

## 整改候选（`f32429e`；本地集成候选代码为 `35b4804`）

| 原问题 | 状态 | 实现与 L0 证据 |
| --- | --- | --- |
| P1-01 包完整性 | `FIXED_CANDIDATE` | install 现在要求 manifest 与 `SHA256SUMS` 完全同集、逐文件 hash 一致，并额外执行 `sha256sum -c`；builder 改为 `venv --copies`，避免包内 Python symlink 逃逸。 |
| P1-02 覆盖/回退 | `FIXED_CANDIDATE` | install 对已有 prefix/unit/launcher/state fail-closed；成功安装写受限 state JSON 和 owner marker，rollback 还核验 unit 的 `ExecStart` 与 launcher 指向，防止删除已被替换的 unit。 |
| P1-03 删除边界 | `FIXED_CANDIDATE` | rollback 仅在固定专用 prefix、state JSON、owner marker 三项均匹配时才删除；install 在创建 prefix 后、解包前记录所有权，失败清理仅删除仍指向该受管 prefix 的 launcher/unit/state。 |
| P1-04 smoke 默认/清理 | `FIXED_CANDIDATE` | smoke 设定固定默认 prefix，拒绝任意其他 prefix；embedding socket 使用 PID 唯一路径，并以 trap 只清理由本次启动的进程和当前用户 socket。 |

`bash -n` 覆盖 build/install/uninstall/smoke/guard 脚本，
`bash packaging/release/test_release_script_guards.sh` 通过。以上是 WSL L0 证据，尚未替代
最终集成提交上的麒麟 L3 安装、真实 SDK、重启和回退验证。

候选发布代码提交 `35b48040c78ee39ad6dd693a87d0c4ea5eed78fd` 已包含 D13E 主线 `4a32e5c`、
D14A release head、修复后的 cherry-pick `df5f4af`/`13c43f8`，以及清理所有权守卫；`git diff --check`
和 release L0 守卫测试均通过。在该候选工作树用 CPython 3.13 执行
`python -m unittest memory-service.tests.test_d13e_formal_eval -v` 得到 48 passed、1 skipped
（非 POSIX 元数据项）、28.132s 的可复核本地契约结果；这不替代最终集成环境或麒麟 L3 验证。

## 逐项证据

- `systemd_install.sh:45-60`：只计算 `VERSION`、固定 CPython 3.12 bridge 和 `app.py`，未使用
  已存在的 `SHA256SUMS` 做全量校验。
- `systemd_install.sh:63-87`：prefix 会移到带时间戳备份，但 unit 在第 86 行直接覆盖；第 87 行
  只是测试一个新的时间戳路径，未保存现有 unit。
- `systemd_uninstall.sh:54-60`：无 realpath/allowlist/ownership run manifest 保护地删除 prefix 与
  同前缀备份。
- `package_smoke.sh:39-46`：未初始化 `INSTALL_PREFIX` 的情况下读取变量，并删除 prefix 和 socket。
- `build_release_package.sh:51-58`：Git identity gate 存在；`build_release_package.sh:189-228`
  生成 manifest/SHA256SUMS，因此完整性 Gate 可以在最终集成版本中补全。

## 后续实施顺序

1. D 主审选择最终集成 SHA，确保它是 D13E 当前主线与经过整改的 D14A 的共同后代。
2. 在该 SHA 上独立复核 P1-01 至 P1-04 及其 shell/合同测试；D14D 不在旧 D14A 分支上做
   临时 VM 手工绕过。
3. 审批升级输入和数据策略，关闭 P1-05；未批准时在 D14D 任务卡中保留 G7=`NOT_RUN`。
4. D13D 进入 `FROZEN` 后，才创建 D14D 专用干净快照并执行 G0--G9。

## 非结论

本审计不否定 D14A 已记录的真实 SDK 冒烟，也不声称 D14A 在最终集成提交失败。它只证明：
现有静态发布脚本尚不具备 D14D 完整生命周期所要求的安全边界和版本一致性。
