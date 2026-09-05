# D13D P0-I2：Forget 五模式执行语义裁决请求

## 请求目的

D 轨已承担 D13D 的四类 raw 集成责任。为完成封存集中的 `topic`、`time_window`、
`full_reset` 三种 Forget 模式，需要先冻结其真实删除范围与可观测检查点；不能由评测
adapter 根据样本名称、测试断言或 Gold 自行推断。

请 Reviewer D / 项目负责人对下列三项作出书面裁决。裁决会形成新的生产实现任务；其合并
commit 将替代现有 D13D 被测基线，随后才可重新冻结 VM。

## 已有事实

- `ForgetPlan` 已冻结五种 mode，但 domain 明确标注 `full_reset` 的 target type 与级联范围
  “待 E/D 书面确认”（`memory-service/domain/forgetting.py`）。
- 当前真实 resolver 只实现 `single_item`、`session`；其余三种显式 fail-closed。
- `memory_entries` 没有结构化 topic 字段；`memory_items` 也不保存与封存集 `topic` selector
  的可验证归属。
- `source_events` 没有删除/遗忘生命周期列。将 `target_type=all` 直接报告为已执行会遗漏
  可检索或可审计的 source event，违反 Forget 的残留检查要求。
- 既有 D10D 任务卡禁止在未批准时变更冻结 IPC、既有 DB 字段或错误码。

## 待裁决项

### F-01：topic 的权威关联

请选择一个可审计的归属真源：

1. 新增经过迁移管理的结构化 `topic_id`/`topic_key`，由受控 ingress 写入，Forget 仅按
   `user_id + topic_key` 解析；或
2. 明确指定现有不可变字段作为 topic 真源，并给出精确字段、规范化规则、索引和跨用户过滤；或
3. 本轮正式封存集不接受 `topic`，由 D13E 替换数据集和 Gold 后重启冻结。

不得对 `content`、`conditions` 或自然语言 selector 做模糊匹配删除。

### F-02：time_window 的权威时间

请确定范围使用下列哪个经时区归一化的时间事实：

1. 被删除 memory 的可信 source event `occurred_at`；
2. memory 的 `created_at`；或
3. 另行新增的事件时间字段。

同时冻结边界为半开区间 `[from, to)`、ISO-8601 带时区输入、UTC 归一化，以及无法关联可信
source event 时的 fail-closed 行为。不得按本机时钟或 adapter 执行时间推断历史范围。

### F-03：full_reset 的数据边界

请在以下互斥选项中指定一项：

1. `full_reset` 只重置可删除的 Memory Service 记忆实体（knowledge/preference），并正式将
   `target_type=all` 从该模式禁止；
2. `full_reset` 必须覆盖 source events，则批准新增 source event 的遗忘/tombstone 生命周期、
   Repository 过滤、迁移和审计策略；或
3. 本轮正式封存集不接受 `full_reset`，由 D13E 替换数据集和 Gold 后重启冻结。

无论选择何项，都必须保留 preview → confirmation token → execute 的既有事务边界，且对所有
受影响实体完成实时查询与全量重建后的残留检查。

## 裁决后实现与验收

获批后，D 轨将实现 user-scoped resolver、soft-delete/tombstone dispatcher、事务后观测接口及
L1 用例。每个 mode 均须覆盖：零命中、跨用户同名对象、重复 execute、凭据重放、边界时间、
漏删、错误删除、实时残留、重建残留和 trace 脱敏。未获批前，当前 fail-closed 行为保留，
D13D 不得生成 Forget formal raw 或进入 Seal。
