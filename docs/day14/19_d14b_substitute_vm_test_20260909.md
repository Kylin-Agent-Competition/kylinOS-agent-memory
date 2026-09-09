# D14B 替代版 VM 测试报告（BTrack VM）

> 执行日期：2026-09-09  
> 测试类型：`SUBSTITUTE / ENGINEERING_ACCEPTANCE`  
> 本报告用于在暂时只有 D14B BTrack VM 的条件下验证实现和服务生命周期；不等价于 D14D Formal L3，也不创建 Formal evidence root。

## 1. 环境与身份

| 项目 | 实际替代环境 | D14D Formal 目标 | 结论 |
|---|---|---|---|
| VM | `Kylin-V11-2603-BTrack-Base` | `Kylin-D14D-clean-vdi-20260906` | 不同，限制 |
| VM UUID | `103fb8a8-cc85-4897-836a-70b68edb5745` | `70ca1ea3-c27e-483d-aaba-0cac7dc5c77c` | 不同，限制 |
| 快照 | `D14B-target-prep-ba3b50e-20260909` | `d14d-clean-base-20260907-r4` | 不同，限制 |
| SSH | `127.0.0.1:2222` | `127.0.0.1:2223` | 不同，限制 |
| hostname | `yanmouren778-pc` | `kylin-agent-pc` | 不同，限制 |
| kernel | `6.6.0-63-generic` | `6.6.0-76-generic` | 不同，限制 |
| tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | 同一 40 位 SHA | 一致 |

## 2. 测试结果

### 2.1 D14B harness

执行：

```bash
python3 -m pytest -q tests/retrieval/test_d14b_harness.py
```

结果：

```text
62 passed in 68.95s (0:01:08)
```

runner/fixture SHA：

```text
test_d14b_harness.py:
f4b905f38c2fd206def29d83d91f3f4e0705cf26a34f2fe44db1cb2496e4ce99

d14b_controlled_dataset_v1.json:
130211517a80955dfd8f703e3175ec292c110c49e361547a71aec3999c498619
```

判定：`PASS`（替代版 harness）。

### 2.2 Service restart

执行了：

```bash
systemctl --user restart kylin-memory
systemctl --user restart kylin-ai-vector-engine
```

结果：memory service `active`，MainPID `2318 -> 10061`；Vector Engine `active`，MainPID `10235`；socket 在约 5–15 秒轮询内恢复，日志记录服务约 8 秒就绪，正式 30 秒等待窗口内恢复。

判定：`PASS_WITH_STARTUP_DELAY`。3 秒早期探针未看到 socket，但不构成正式失败。

### 2.3 OS reboot

重启前 boot ID：`fd7007e1-509d-46ab-9744-f20127ad07e8`  
重启后 boot ID：`ce1f5591-5733-4c55-b623-7fa82f26b68b`

重启后：

```text
kylin-memory=active
kylin-ai-vector-engine=active
memory.sock=present
MainPID=1836
HEAD=ba3b50e1bdeea185bca9daee9d1d45958f62a636
worktree=clean
```

期间有短暂黑屏和 SSH banner 延迟，系统完成启动后恢复连接。

判定：`PASS_WITH_BOOT_LATENCY_NOTE`。

## 3. 替代版结论

```text
SUBSTITUTE_RESULT=PASS_WITH_LIMITATIONS
D14B_HARNESS=PASS (62/62)
SERVICE_RESTART=PASS_WITH_STARTUP_DELAY
OS_REBOOT=PASS_WITH_BOOT_LATENCY_NOTE
POST_REBOOT_CHECKOUT=PASS (exact commit + clean)
D14B_FORMAL_L3=NOT_RUN / UNVERIFIED
```

该结果证明当前 commit 在 BTrack VM 上具备可继续推进的实现级回归和生命周期恢复能力。

## 4. 明确局限性

本轮没有取得或执行以下正式输入：

```text
d13d-handoff.json
d14d-handoff.json
d14b-capture-handoff.json
kylin-memory-a-d14a-0.1.0-d14a-ba3b50e.tar.gz
```

另外：

- VM 身份、快照、kernel、hostname、SSH 端口与 D14D Formal 不一致；
- VM 保留源码 checkout，不满足 D14D clean VM 的无个人开发目录要求；
- `kylin-memory-a-d14a` 未安装，冻结包 tar 本体缺失；
- 未执行 package-only install、冻结包 G2/G3/G4、production capture、D14D G7/G8/G9 或独立 Formal review；
- harness 结果证明测试工具和 B 轨逻辑门禁，不等于冻结发布包上的完整生产数据面、跨用户隔离和正式性能阈值通过。

因此本报告可以作为替代工程验收和风险定位材料，但不得升级为 `D14B_FORMAL_L3=PASS` 或 `D14D_L3_READY` 的新证据。

