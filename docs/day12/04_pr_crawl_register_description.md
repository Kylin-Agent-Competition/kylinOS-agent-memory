# PR 描述：历史 PR 技术债爬取补登（TD-047~052）

## 背景

按 Day11 跨轨对接需求（`Day11跨轨依赖与需求清单_对接版_20260901.md`）与 D12 功能冻结阶段要求，爬取 GitHub 全量历史 PR（70 个），对照 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 技术债总账，核查是否存在「声称已登记 / 已声明已知限制」但实际从未写入总账的技术债。

## 发现并补登的技术债

| TD | 来源 | 标题 | 严重度 |
|---|---|---|---|
| TD-047 | 对接版 A-REQ-01（P1） | production `app.py` OutboxWorker 未注入 deletion consumer（删除事件生产组装缺口） | Medium |
| TD-048 | 对接版 A-REQ-02 | TD-A-D10-CACHE-INVALIDATION 代码/PR 声称「已关闭」但总账仍 Open（D11A #84 未回写；time_window 未实现）——治理不一致 | Low |
| TD-049 | PR #57 | 声明登记的 TD-1~3（/tmp 固定跨用户路径 / L2-C1 sudo mv 测试设施风险 / evidence metadata 精化）从未写入总账 | Medium |
| TD-050 | PR #36 LOW-01 | implicit 隐式偏好推断未实现（explicitness 仅保留枚举/接口，规则路径恒 explicit） | Low |
| TD-051 | PR #42 | 声称「登记 TD 前置项」的 cmake 系统包未安装（C++ Bridge 编译阻塞）未入账 | Medium |
| TD-052 | PR #100（D12A） | `_embed_hang_threshold_ms` 默认 60s 进程级硬编码未参数化到 config.toml | Low |

## 修改范围

- `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`：新增 TD-047~052（6 行），与既有 74 行格式一致，无重复 ID。

## 明确不修改范围

- 不修改任何生产代码（本次为纯文档/治理补登）。
- 不关闭任何既有 TD（仅补登缺失记录）。
- TD-046 属 D12A PR #100 内容，不在本 PR。

## 验证

- 注册表 12 列结构合法；TD-047~052 均唯一存在；`evidence/index.yaml` 解析通过（未改动）。
- 纯文档改动，无代码/测试影响。

## 关联

- 关联 PR：#100（D12A，含 TD-046）
- 关联文档：`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
