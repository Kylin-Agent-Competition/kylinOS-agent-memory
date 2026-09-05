# D13D 正式冻结：外部工件与 Reviewer 协作申请单

## 目的

本申请单用于关闭 D13D 当前无法由普通 VM 执行用户自行取得的门禁。D13D 已完成
`4a32e5c948a968f3bd4409d91deac320002baea1` 的隔离部署、迁移、UDS 预检和测试；
不得因后续缺失材料而伪造签名、公钥、Trust Root 或逐样本执行结果。

## 已核验的冻结候选

- VM：`Kylin-desktop-neo D12-TDR`；D13D 回滚快照
  `d13d-pre-4a32e5c-20260905-2320`，UUID
  `458b6763-5015-404f-a961-cd4a1899232d`。
- 候选工作树：`/home/kylin-agent/kylinOS-agent-memory-d13d-4a32e5c`。
- VM 内 commit：`4a32e5c948a968f3bd4409d91deac320002baea1`，工作树 clean。
- D Reviewer 已批准 PR #148：Reviewer `Ducknesses`，Review
  <https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-5121766539>，
  reviewed commit `aa6564a3fa544ab01302adf0b1598436c97f88c0`。
- VM 内复算的候选工件哈希：

```text
9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b  D13E_FORMAL_TESTSET_V1.jsonl
aeea9beab5d25461083bb693424014a813cd91bae6b0d7b60443f817f33c6be0  D13E_GOLD_V1.jsonl
561034df97ee5c73675784a40b18726c51f3ff1120022ad04f2c66b0366c7ff9  D13E_FORMAL_THRESHOLDS_V1.json
0690663406a1dc8cfbd1cdd8150e16db53375a1417984e437b67cf742af56fd1  D13E_FORMAL_MANIFEST_V1.json
297d534a4c1a4a3009942cc90a7614dc17eaec5843656d9b50ba601028a3036f  scripts/run_d13e_formal_eval.py
```

上述哈希仅可在 Linux/VM 的目标字节流上复核。Windows checkout 的换行转换不得作为 Seal 输入。
其中 Manifest hash 是仓库候选 Manifest（`PENDING_D13D`）的观测值，**不能**直接写入正式
Review Seal；D13D 写入 provenance 后，D Reviewer 必须对 evidence root 内最终
`FROZEN_BY_D13D` Manifest 重新复算并签发其 hash。

## Reviewer D 密钥责任（2026-09-06 决定）

Reviewer D 是唯一签名保管人，密钥物料分离：

| 用途 | key ID | 私钥保管位置 | 可交付物 |
| --- | --- | --- | --- |
| D13E Review Seal | `d13e-review-rd-20260906-v1` | Windows 受限目录，仅 Reviewer D | public PEM、Review Seal、detached signature |
| D13D Execution Seal | `d13d-execution-rd-20260906-v1` | Windows 受限目录，仅 Reviewer D | public PEM、Execution Seal、detached signature |

私钥不得复制到 VM、证据目录、Git、CI 或任何工作树。D13D 负责准备可验证的最终
Manifest、raw、attestation 和 Seal payload；Reviewer D 在 Windows 受控边界中独立签名。

## 申请 A：D Reviewer / 签名保管人

Reviewer D 按上述责任提供 D13E Review Seal 的公开交付物，不提供 Review 私钥：

```text
D13E_REVIEW_SEAL_V1.json
D13E_REVIEW_SEAL_V1.sig
d13e-review-public.pem
```

Review Seal 必须使用 Ed25519 detached signature，含以下事实：

- `seal_version=d13e-review-seal/v1`、`signature_scheme=ed25519`；
- PR #148、实际作者 `gaoyizhe934`、Reviewer `Ducknesses`、track `D`、state `APPROVED`；
- 上述 Review URL 与 reviewed commit；
- Dataset、Gold、Threshold、Runner 四组与上述 VM 值一致，及 evidence root 内最终
  `FROZEN_BY_D13D` Manifest 的完整 SHA-256；
- 与 Trust Root 中 `review.key_id` 一致的 `key_id`。

交付时请同时给出公钥 SHA-256 和公钥来源确认。**禁止**通过仓库、PR、证据目录、CI、聊天记录或本申请单传递私钥。

## 申请 B：VM 管理员 / 系统授权人

当前 VM 用户 `kylin-agent` 属于 sudo 组，但 `sudo -n` 不可用；`/etc/kylin-memory/trust`
不存在。请在收到申请 A 的 review 公钥和申请 C 的 D13D execution 公钥后，以 root 权限预置：

```text
/etc/kylin-memory/trust/
  D13E_TRUST_ROOTS_V1.json
  d13e-review-public.pem
  d13d-execution-public.pem
```

固定契约：目录和三个文件均须 non-symlink；owner `root:root`；目录/文件的
`mode & 0o022 == 0`；Trust Root JSON 使用 `trust_store_version=d13e-trust-roots/v1` 与
`signature_scheme=ed25519`，并分别登记 `review`、`d13d_execution` 的 `key_id`、
`public_key_file`（仅 basename）和 `public_key_sha256`。

请只回传以下非敏感核验结果：`ls -ld`、`stat`、三个文件 SHA-256、Trust Root JSON 内容。
不得回传任何私钥或 sudo 密码。

## 申请 C：D13D 签名保管人

Reviewer D 已按上述职责建立 D13D 受控 Ed25519 signing key，并仅交付：

```text
d13d-execution-public.pem
key_id
public_key_sha256
受控签名接口或在 VM 外签名的流程说明
```

私钥必须留在 D13D 受控边界外，不能进入 VM 工作树、evidence root、Git、CI 或 E 轨。
在 D13D 生成真实 execution attestation 后，请返回：

```text
D13D_EXECUTION_SEAL_V1.json
D13D_EXECUTION_SEAL_V1.sig
```

Seal 要绑定 attestation SHA-256、implementation commit、environment ID、dependency/data
reference、evidence root/reference、`frozen_by_track=D`、approval reference 和 `key_id`。

## 申请 D：D13E / D13B 执行责任方

请提供在冻结 VM 上产生 17 条逐样本正式 raw JSONL 的受批准执行步骤或执行人员：

- Preference 4 条，Conflict 4 条，Safety 4 条，Forget 5 条；
- 每条含对应 `sample_id`、`metric`、`actual`，与 Dataset/Gold 一一对应；
- Safety 明确包含四个 hard-zero counter，Forget 明确包含五个 hard-zero counter；
- 结果不得来自 Mock、手工构造或旧 commit；失败样本不得删除；
- raw、命令输出、execution log、`SHA256SUMS` 与 `evidence/index.yaml` 必须进入同一唯一 evidence root。

当前仓库仅提供候选 Dataset/Gold、验证 Runner 和正式合同；它不包含可自行伪造的真实 raw
生成器。因此 D13D 需要 D13E/B 方确认真实链路与运行职责，之后才能生成 attestation 和 Seal。

## 申请 E：D13A 代码责任方（非 D13D 冻结门禁）

请单独处理 VM pytest 的 4 个 D13A 测试维护失败：

```text
memory-service/tests/test_day13a_benchmarks.py::test_full_run_rejects_incomplete_real_index_evidence
```

当前 `validate_run_completeness()` 已要求 `expected_commit`/`expected_branch` 并输出完整路径错误，
但该测试未传入前述参数并将旧短文本作列表精确匹配。请由 D13A 责任方修正测试/合同一致性并在
`4a32e5c...` 后代上复跑；D13D 不修改 D13A 代码或跳过测试。该项登记为并行技术债，
不阻塞 D13D Trust Root、Seal、raw、attestation 与正式 runner 冻结闭环。

## D13D 收件后的执行顺序

1. 在 VM 核验申请 B 的 owner、mode、symlink 与三项 hash。
2. 建立唯一 formal evidence root，复制候选工件，在 VM 复算 hash，并填写最终 D13D provenance。
3. 请申请 A 对最终 Manifest 复算 hash 后签发 Review Seal；不得重用候选 Manifest hash。
4. 以申请 D 的真实执行结果建立 raw、execution log、SHA256SUMS、evidence index 与 attestation。
5. 由申请 C 的受控流程签发 D13D Execution Seal；将两份 Seal/.sig 放入 evidence root。
6. 在冻结 VM 调用正式 runner。仅 Gate 0--10 全部通过且 summary 落盘后，D13D 才可标记 `FROZEN`。
