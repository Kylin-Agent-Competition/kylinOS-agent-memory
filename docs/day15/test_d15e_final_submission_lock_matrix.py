"""D15E 最终提交锁定矩阵 overclaim 确定性 pytest 守卫（module=docs）。

守卫对象：docs/day15/10_d15e_final_submission_lock_matrix_20260909.md
（as-of 2026-09-09，已由同批 doc 任务提交；本测试对其只读，绝不修改）。

性质：
- 纯 stdlib 静态事实测试（pathlib / re / os.path），不修改任何文件、
  不访问网络、不依赖麒麟 Runtime、不启动子进程、不触碰 Git、
  无 skip / xfail、不吞异常、断言不做恒真弱化。
- fail-closed：任何越级 token/短语、E15 锁定状态行篡改与重复、
  关键快照事实缺失、D14D 边界被破坏、evidence 路径不存在、
  L2/L3 或 Runtime 结论表述出现，都会使 pytest 退出码非 0。
- 行级 provenance 绑定守卫（HIGH-03）：对 §6 D14C/D15C 行、§5 C6 行、
  §7 D14C 闭合前置 / D15C handoff 前置行做「必须含 / 禁止含」行级锚定断言，
  并注入反向漂移（D14C 错绑 PR #167、D15C 写成「无该产物」）验证守卫判别力，
  杜绝「token 在某处出现即通过」的全文弱守卫与恒真断言。
- E15 锁定对象 canonical 名称逐字绑定（MEDIUM-01）：E15-1 ~ E15-6 的
  cells[1] 与 E15_EXPECTED_NAME 逐字一致。

本测试本身不宣布 D15E FINAL LOCK、不签署 D14E final acceptance、
不执行 L2/L3、不生成新的 Runtime 结论。
"""
from __future__ import annotations

import re
from pathlib import Path

# 仓库根解析：本文件位于 docs/day15/，parents[0]=day15, parents[1]=docs,
# parents[2]=仓库根。
REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "day15" / "10_d15e_final_submission_lock_matrix_20260909.md"

_TEXT = DOC_PATH.read_text(encoding="utf-8")
_LINES = _TEXT.splitlines()

# 覆盖项 1：9 个章节标题（逐字）。
SECTION_HEADINGS = (
    "## 1. 性质声明与范围边界",
    "## 2. 快照身份与状态行",
    "## 3. E15-1 ~ E15-6 Submission Lock Matrix",
    "## 4. Submission Inventory（提交物清单）",
    "## 5. Claim-to-Evidence Mapping（声明—证据映射）",
    "## 6. Upstream Blocker Matrix（上游阻塞矩阵）",
    "## 7. Final Lock Trigger（最终锁定触发条件）",
    "## 8. 禁止 Overclaim 边界与机器守卫覆盖边界",
    "## 9. 状态词纪律、责任与 Reviewer",
)

# 覆盖项 2：4 条状态行（各须独立成行，逐字）。
D15E_STATUS_LINES = (
    "D15E_PHASE0_PREPARATION=READY",
    "D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ",
    "D15E_FINAL_SUBMISSION_LOCK_DECLARED=false",
    "D15E_SIGNOFF_STATUS=BLOCKED",
)

# 覆盖项 3：E15-1 ~ E15-6 逐字锁点状态绑定。
E15_EXPECTED_STATUS = {
    "E15-1": "WAITING_PREREQ",
    "E15-2": "BLOCKED_BY_D14B",
    "E15-3": "BLOCKED_BY_D14C",
    "E15-4": "WAITING_PREREQ",
    "E15-5": "WAITING_PREREQ",
    "E15-6": "BLOCKED",
}

# 覆盖项 3b：E15-1 ~ E15-6 锁定对象 canonical 名称（MEDIUM-01，逐字绑定 cells[1]）。
E15_EXPECTED_NAME = {
    "E15-1": "技术文档与用户手册口径",
    "E15-2": "功能测试与效果验证报告",
    "E15-3": "真实案例与四项核心指标结论",
    "E15-4": "提交物清单与交付物身份",
    "E15-5": "claim-to-evidence 映射与 overclaim 终检",
    "E15-6": "最终提交口径与签署触发",
}

# 覆盖项 4：越级 token（词边界 \b...\b 匹配）。
ESCALATION_TOKENS = (
    "FINAL_LOCK",
    "LOCKED",
    "SUBMISSION_LOCKED",
    "PRODUCTION_READY",
    "RELEASE_READY",
    "HOST_VERIFIED",
    "RUNTIME_VERIFIED",
    "PRODUCTION_E2E_PASS",
    "D14E_SIGNED",
    "SIGNOFF_APPROVED",
)

# 覆盖项 4：越级短语（子串缺席断言）。
ESCALATION_PHRASES = (
    "production_ready=true",
    "release_ready=true",
    "D14B_FORMAL_L3=PASS",
    "D14C_FORMAL_L3=PASS",
    "D14E_FINAL_ACCEPTANCE=PASS",
    "D14E_SIGNOFF_STATUS=SIGNED",
    "production ready",
    "release ready",
    "production E2E PASS",
)

# 覆盖项 4：受控词必须仍在场（且 \bLOCKED\b 缺席断言不误伤它们）。
CONTROLLED_WORDS = (
    "BLOCKED",
    "BLOCKED_BY_D14B",
    "BLOCKED_BY_D14C",
    "BLOCKED_PENDING_D15C_HANDOFF",
    "L3_READY",
    "NOT_FROZEN",
    "RUNTIME_UNVERIFIED",
    "WAITING_PREREQ",
)

# 覆盖项 5：关键快照事实（逐字子串在场）。
SNAPSHOT_FACTS = (
    "as-of=2026-09-09",
    "3ef0ce518844749f14aa384790efbcde5af39ec9",
    "a7abb1e71c03c4f1558e5c6a9eff2b9f36437993",
    "ba3b50e1bdeea185bca9daee9d1d45958f62a636",
    "fb4531e673bb5f02d6a109ec0f467cb6d384e927",
    "77319aa4ce75d7f7fe4d7ed64f7332cffdb88441",
    "2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401",
    "76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0",
    "8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67",
    "dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee",
    "0.1.0-d14a",
    "NON_MAIN_BRANCH",
    "PR_OPEN",
    "2/11",
    "D14B_FORMAL_L3=NOT_RUN/UNVERIFIED",
    "D14B_FORMAL_RESULT=UNVERIFIED",
    "D14C_FORMAL_L3=BLOCKED",
    "D14C_FORMAL_RESULT=UNVERIFIED",
    "BLOCKED_PENDING_D15C_HANDOFF",
    "RUNTIME_NOT_REQUIRED",
    "72950fd59bf5fddbfe12d4daad9f040ea227e5f9",
    "b5f8154b9e510c10124e84ecf70d608e4fee7896",
    "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
)

# 覆盖项 12：current main identity / PR #171 historical merge identity（HIGH-01/HIGH-02）。
CURRENT_MAIN_SHA = "a7abb1e71c03c4f1558e5c6a9eff2b9f36437993"
PR171_MERGE_SHA = "3ef0ce518844749f14aa384790efbcde5af39ec9"

# 覆盖项 13：MEDIUM-01 canonical 状态词收口。
NON_CANONICAL_D15E_STATE_ALIASES = ("D15E_FINAL_LOCK", "D15E_FINAL_COMPLETION_CLAIM")

# 覆盖项 14：MEDIUM-02 D15E guard 的 CI 边界（manual static guard，非 CI gate）。
D15E_GUARD_CI_BOUNDARY_PHRASES = (
    "executable / manual static guard",
    "GitHub merge CI enforced gate",
    "它**不是** GitHub merge CI enforced gate",
)

# 覆盖项 9：文档引用的 evidence 路径（fail-closed 磁盘存在性检查）。
EVIDENCE_REL_PATHS = (
    "evidence/index.yaml",
    "evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/D13D_FREEZE_RECORD_20260908.md",
    "evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json",
    "evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md",
    "evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e",
)


def _section_block(start_heading: str, end_heading: str) -> str:
    """按章节标题提取两标题之间的文档块（re.S，含中间全部内容）。"""
    m = re.search(
        re.escape(start_heading) + r".*?(?=" + re.escape(end_heading) + r")",
        _TEXT,
        re.S,
    )
    assert m is not None, "未找到章节块: {0} ... {1}".format(start_heading, end_heading)
    return m.group(0)


def _table_rows(block: str) -> list[list[str]]:
    """解析 markdown 表格为 cells 列表。

    规则（与已批准方案一致，禁止字符级预过滤）：
    1. 取 strip 后以 '|' 开头的物理行；
    2. cells = [c.strip() for c in row.strip().strip('|').split('|')]；
    3. 删除首尾空 cell；
    4. cells 全部由 '-'/':' 组成 → 分隔行，跳过（表头与数据行保留）。
    """
    rows: list[list[str]] = []
    for raw_line in block.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and not cells[0]:
            cells.pop(0)
        if cells and not cells[-1]:
            cells.pop()
        if cells and all(re.fullmatch(r"[-:]+", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def _section_block_in(text: str, start_heading: str, end_heading: str) -> str:
    """按章节标题提取入参 text 中两标题之间的文档块（re.S，含中间全部内容）。

    与 _section_block 同逻辑，但以入参 text 而非模块 _TEXT 为输入，
    便于反向漂移注入后的派生文本复用同一解析路径。
    """
    m = re.search(
        re.escape(start_heading) + r".*?(?=" + re.escape(end_heading) + r")",
        text,
        re.S,
    )
    assert m is not None, "未找到章节块: {0} ... {1}".format(start_heading, end_heading)
    return m.group(0)


def _upstream_row(text: str, upstream: str) -> str:
    """在 §6 Upstream Blocker Matrix 内按行首 `| <upstream> |` 定位上游行。

    断言恰好 1 行并返回该行原文（strip 后）；0 行或多行均 fail-closed。
    """
    block = _section_block_in(
        text,
        "## 6. Upstream Blocker Matrix（上游阻塞矩阵）",
        "## 7. Final Lock Trigger（最终锁定触发条件）",
    )
    pattern = r"^\|\s*" + re.escape(upstream) + r"\s*\|"
    matches = [
        line.strip()
        for line in block.splitlines()
        if re.match(pattern, line.strip())
    ]
    assert len(matches) == 1, (
        "§6 上游 {0} 行应恰好 1 行，实际 {1} 行".format(upstream, len(matches))
    )
    return matches[0]


def _c6_row(text: str) -> str:
    """在 §5 Claim-to-Evidence Mapping 内按行首 `| C6` 定位 C6 行。

    断言恰好 1 行并返回该行原文；供行级 provenance 绑定断言使用。
    """
    block = _section_block_in(
        text,
        "## 5. Claim-to-Evidence Mapping（声明—证据映射）",
        "## 6. Upstream Blocker Matrix（上游阻塞矩阵）",
    )
    matches = [
        line.strip()
        for line in block.splitlines()
        if re.match(r"^\|\s*C6\b", line.strip())
    ]
    assert len(matches) == 1, "§5 C6 行应恰好 1 行，实际 {0} 行".format(len(matches))
    return matches[0]


def _final_lock_d14c_line(text: str) -> str:
    """在 §7 内按行首有序列表标记定位 D14C 闭合前置行（断言恰好 1 行）。

    不能用裸子串 `D14C 闭合前置`——D15C handoff 行尾部含「D14C 闭合前置不得推进」，
    裸子串会同时命中两行；必须锚定行首 `N. **D14C 闭合前置`。
    """
    block = _section_block_in(
        text,
        "## 7. Final Lock Trigger（最终锁定触发条件）",
        "## 8. 禁止 Overclaim 边界与机器守卫覆盖边界",
    )
    matches = [
        line.strip()
        for line in block.splitlines()
        if re.match(r"^\d+\.\s+\*\*D14C 闭合前置", line.strip())
    ]
    assert len(matches) == 1, (
        "§7 D14C 闭合前置行应恰好 1 行，实际 {0} 行".format(len(matches))
    )
    return matches[0]


def _final_lock_d15c_line(text: str) -> str:
    """在 §7 内按行首嵌套列表标记定位 D15C handoff 前置行（断言恰好 1 行）。"""
    block = _section_block_in(
        text,
        "## 7. Final Lock Trigger（最终锁定触发条件）",
        "## 8. 禁止 Overclaim 边界与机器守卫覆盖边界",
    )
    matches = [
        line.strip()
        for line in block.splitlines()
        if re.match(r"^[-+*]\s+\*\*D15C handoff 前置", line.strip())
    ]
    assert len(matches) == 1, (
        "§7 D15C handoff 前置行应恰好 1 行，实际 {0} 行".format(len(matches))
    )
    return matches[0]


def _expect_assertion_error(fn, text: str) -> None:
    """断言 fn(text) 确实抛出 AssertionError（反向漂移预期路径，非吞异常）。

    若 fn 未抛 AssertionError，则显式 raise AssertionError 使测试失败，
    防止注入失效 / 守卫失效演变为恒真。
    """
    try:
        fn(text)
    except AssertionError:
        return
    raise AssertionError(
        "{0} 未对反向漂移输入抛出 AssertionError（守卫失效或注入未生效）".format(
            getattr(fn, "__name__", repr(fn))
        )
    )


def _assert_d14c_association(text: str) -> None:
    """HIGH-03：§6 D14C 行级 provenance 绑定。

    必须绑定 PR #156 / test/D14C-l3-clean-vm-release-regression / 77319aa4…；
    禁止错绑 PR #167 / feat/C-hook-evidence / D15C current SHA。
    """
    row = _upstream_row(text, "D14C")
    for token in (
        "PR #156",
        "77319aa4ce75d7f7fe4d7ed64f7332cffdb88441",
        "test/D14C-l3-clean-vm-release-regression",
    ):
        assert token in row, "§6 D14C 行缺少绑定 token {0}: {1}".format(token, row)
    for token in (
        "PR #167",
        "404c7e1cadd188d8e64547c992a77bec28e457e2",
        "feat/C-hook-evidence",
        "b5f8154b9e510c10124e84ecf70d608e4fee7896",
        "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
    ):
        assert token not in row, "§6 D14C 行出现禁止 token（错绑）{0}: {1}".format(token, row)


def _assert_d14b_association(text: str) -> None:
    """PR #124 已合入 main 后的 §6 D14B 行级 provenance 绑定。"""
    row = _upstream_row(text, "D14B")
    for token in (
        "PR #124",
        "test/D14B-l3-vm-release-regression",
        "fb4531e673bb5f02d6a109ec0f467cb6d384e927",
        "a7abb1e71c03c4f1558e5c6a9eff2b9f36437993",
        "已合入 main",
    ):
        assert token in row, "§6 D14B 行缺少绑定 token {0}: {1}".format(token, row)
    for token in (
        "PR_OPEN",
        "NON_MAIN_BRANCH",
        "7445c2ee2753100f46d0d8062f28ccf0aed22aad",
        "8fbc705c6b9d1e8966ec688d0dfda9a509dc0f20",
        "2/27",
        "未合入 main",
        "NOT_MERGED",
    ):
        assert token not in row, "§6 D14B 行出现禁止 token（旧快照/错绑）{0}: {1}".format(
            token, row
        )


def _assert_d14b_formal_boundary(text: str) -> None:
    """D14B merged 后必须保留 Formal L3 debt 与 owner waiver 边界。"""
    row = _upstream_row(text, "D14B")
    for token in (
        "D14B_FORMAL_L3=NOT_RUN/UNVERIFIED",
        "D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS",
        "WAIVED_BY_OWNER",
    ):
        assert token in row, "§6 D14B 行缺少 Formal debt 边界 {0}: {1}".format(token, row)


def _assert_d15c_association(text: str) -> None:
    """HIGH-03：§6 D15C 行级 provenance 绑定。

    必须绑定 PR #167 / feat/C-hook-evidence / b5f8154… / a4034c9…；禁止写成
    「无该产物」「NON_MAIN_BRANCH」「review 未闭合」。
    """
    row = _upstream_row(text, "D15C")
    for token in (
        "PR #167",
        "feat/C-hook-evidence",
        "b5f8154b9e510c10124e84ecf70d608e4fee7896",
        "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
        "HANDOFF_SUBMITTED",
        "已合入 main",
    ):
        assert token in row, "§6 D15C 行缺少绑定 token {0}: {1}".format(token, row)
    for token in ("无该产物", "NON_MAIN_BRANCH", "review 未闭合", "NOT_MERGED"):
        assert token not in row, "§6 D15C 行出现禁止 token {0}: {1}".format(token, row)


def _assert_c6_association(text: str) -> None:
    """HIGH-03：§5 C6 行级 provenance 绑定。

    必须绑定 PR #156 / test/D14C-l3-clean-vm-release-regression / 77319aa4…；
    禁止错绑 PR #167 / feat/C-hook-evidence / D15C current SHA。
    """
    row = _c6_row(text)
    for token in (
        "PR #156",
        "77319aa4ce75d7f7fe4d7ed64f7332cffdb88441",
        "test/D14C-l3-clean-vm-release-regression",
    ):
        assert token in row, "§5 C6 行缺少绑定 token {0}: {1}".format(token, row)
    for token in (
        "PR #167",
        "404c7e1cadd188d8e64547c992a77bec28e457e2",
        "feat/C-hook-evidence",
        "b5f8154b9e510c10124e84ecf70d608e4fee7896",
        "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
    ):
        assert token not in row, "§5 C6 行出现禁止 token（错绑）{0}: {1}".format(token, row)


def _assert_final_lock_trigger_association(text: str) -> None:
    """HIGH-03：§7 触发条件行级 provenance 绑定。

    D14C 闭合前置行只绑定 PR #156 / test/D14C… / 77319aa4…（禁止 PR #167 /
    feat/C-hook-evidence / D15C current SHA）；D15C handoff 前置行必须绑定
    PR #167 / feat/C-hook-evidence / b5f8154… / a4034c9…。
    """
    d14c_line = _final_lock_d14c_line(text)
    for token in (
        "PR #156",
        "77319aa4ce75d7f7fe4d7ed64f7332cffdb88441",
        "test/D14C-l3-clean-vm-release-regression",
    ):
        assert token in d14c_line, (
            "§7 D14C 闭合前置行缺少绑定 token {0}: {1}".format(token, d14c_line)
        )
    for token in (
        "PR #167",
        "404c7e1cadd188d8e64547c992a77bec28e457e2",
        "feat/C-hook-evidence",
        "b5f8154b9e510c10124e84ecf70d608e4fee7896",
        "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
    ):
        assert token not in d14c_line, (
            "§7 D14C 闭合前置行出现禁止 token（错绑）{0}: {1}".format(token, d14c_line)
        )
    d15c_line = _final_lock_d15c_line(text)
    for token in (
        "PR #167",
        "feat/C-hook-evidence",
        "b5f8154b9e510c10124e84ecf70d608e4fee7896",
        "a4034c9cdab1de31f70bced73dcab8ff2b18407c",
        "HANDOFF_SUBMITTED",
    ):
        assert token in d15c_line, (
            "§7 D15C handoff 前置行缺少绑定 token {0}: {1}".format(token, d15c_line)
        )


def _scan_time_main_head(text: str) -> str:
    """HIGH-02：结构化读取 §2.1 表格中的 scan_time_main_head=<40-hex>（恰好一项）。"""
    block = _section_block_in(text, "## 2. 快照身份与状态行", "## 3.")
    matches = re.findall(r"scan_time_main_head=([0-9a-f]{40})", block)
    assert len(matches) == 1, (
        "§2.1 scan_time_main_head 应恰好 1 项，实际 {0} 项".format(len(matches))
    )
    return matches[0]


def _bound7_block(text: str) -> str:
    """HIGH-02：定位 BOUND-7 段落（【BOUND-7】 到 【BOUND-8】 之前，恰好一条）。"""
    count = text.count("【BOUND-7】")
    assert count == 1, "【BOUND-7】应恰好 1 处，实际 {0} 处".format(count)
    m = re.search(r"【BOUND-7】.*?(?=【BOUND-8】)", text, re.S)
    assert m is not None, "未找到 BOUND-7 段落"
    return m.group(0)


def _assert_current_main_association(text: str) -> None:
    """HIGH-02：§2.1 current main 与 BOUND-7 current main 必须一致且为 a7abb1e…。

    PR #171 的 3ef0ce… 只能作为 historical merge identity 出现，
    不得冒充 current scan-time main。
    """
    scan = _scan_time_main_head(text)
    assert scan == CURRENT_MAIN_SHA, (
        "§2.1 scan_time_main_head 不是 current main: {0}".format(scan)
    )
    block = _bound7_block(text)
    assert CURRENT_MAIN_SHA in block, (
        "BOUND-7 缺少 current main {0}".format(CURRENT_MAIN_SHA)
    )
    for forbidden in (
        "scan-time main HEAD（3ef0ce",
        "scan-time main HEAD(3ef0ce",
        "current scan-time main=3ef0ce",
        "main HEAD=3ef0ce",
    ):
        assert forbidden not in block, (
            "BOUND-7 把 historical 3ef0ce 标为 current main（禁止）: {0}".format(forbidden)
        )
    if PR171_MERGE_SHA in block:
        assert ("historical" in block) or ("历史" in block), (
            "BOUND-7 出现 3ef0ce… 但未标注 historical merge identity"
        )


def _assert_d14e_row_association(text: str) -> None:
    """HIGH-02：§6 D14E 行必须绑定 PR #171 ↔ merge commit=3ef0ce…。

    禁止把 3ef0ce… 写成 main HEAD=…；若该行出现 current main，必须是 a7abb1e…。
    """
    row = _upstream_row(text, "D14E")
    assert "PR #171" in row, "§6 D14E 行缺少 PR #171: {0}".format(row)
    assert PR171_MERGE_SHA in row, (
        "§6 D14E 行缺少 PR #171 merge commit: {0}".format(row)
    )
    assert ("merge commit" in row) or ("historical merge identity" in row), (
        "§6 D14E 行缺少 merge commit / historical merge identity 语义: {0}".format(row)
    )
    assert "main HEAD=" + PR171_MERGE_SHA not in row, (
        "§6 D14E 行把 PR #171 merge commit 错标为 main HEAD（禁止）: {0}".format(row)
    )
    if "current scan-time main" in row:
        assert CURRENT_MAIN_SHA in row, (
            "§6 D14E 行声明 current main 但不是 {0}: {1}".format(CURRENT_MAIN_SHA, row)
        )

def _e15_matrix_status() -> dict[str, str]:
    """覆盖项 3：解析 §3 块内 E15 锁点行，返回 {锁点: 状态} 并完成全部绑定断言。"""
    block = _section_block("## 3. E15-1 ~ E15-6 Submission Lock Matrix", "## 4.")
    rows = _table_rows(block)
    # 兜底：非分隔行必须 >= 7（1 表头 + 6 数据行），防止解析退化得到 0 行。
    assert len(rows) >= 7, "E15 矩阵非分隔行数异常（解析退化）: {0}".format(len(rows))
    occurrence: dict[str, int] = {}
    parsed: dict[str, str] = {}
    parsed_names: dict[str, str] = {}
    for cells in rows:
        assert len(cells) == 5, "E15 矩阵行 cell 数错误（必须严格 5 列）: {0}".format(cells)
        lock = cells[0]
        if re.fullmatch(r"E15-\d+", lock):
            occurrence[lock] = occurrence.get(lock, 0) + 1
            parsed[lock] = cells[2]
            parsed_names[lock] = cells[1]
    assert set(occurrence) == set(E15_EXPECTED_STATUS), (
        "E15 锁点集合不匹配: {0}".format(sorted(occurrence))
    )
    for lock, count in occurrence.items():
        assert count == 1, "锁点 {0} 出现 {1} 次（必须恰好一行，fail-closed）".format(lock, count)
    assert parsed == E15_EXPECTED_STATUS, (
        "E15 锁定状态与预期不一致: {0}".format(parsed)
    )
    assert parsed_names == E15_EXPECTED_NAME, (
        "E15 锁定对象 canonical 名称与预期不一致（MEDIUM-01）: {0}".format(parsed_names)
    )
    return parsed


# 覆盖项 1：9 个章节标题逐字在场。
def test_nine_section_headings_present() -> None:
    for heading in SECTION_HEADINGS:
        assert heading in _TEXT, "缺少章节标题: {0}".format(heading)


# 覆盖项 2：4 条状态行各自独立成行且逐字存在。
def test_d15e_status_lines_each_on_own_line() -> None:
    stripped_lines = {line.strip() for line in _LINES}
    for status_line in D15E_STATUS_LINES:
        assert status_line in stripped_lines, (
            "状态行缺失或未独立成行（逐字）: {0}".format(status_line)
        )


# 覆盖项 3：E15-1 ~ E15-6 锁定矩阵行级解析与逐字状态绑定。
def test_e15_submission_lock_matrix_binding() -> None:
    parsed = _e15_matrix_status()
    assert parsed == E15_EXPECTED_STATUS


# 覆盖项 4：越级 token / 短语缺席，受控词在场且未被误伤。
def test_escalation_tokens_absent() -> None:
    for token in ESCALATION_TOKENS:
        pattern = re.compile(r"\b" + re.escape(token) + r"\b")
        assert pattern.search(_TEXT) is None, "发现越级 token: {0}".format(token)


def test_escalation_phrases_absent() -> None:
    for phrase in ESCALATION_PHRASES:
        assert phrase not in _TEXT, "发现越级短语: {0}".format(phrase)


def test_controlled_words_still_present() -> None:
    for word in CONTROLLED_WORDS:
        assert word in _TEXT, "受控词缺失: {0}".format(word)


# 覆盖项 5：关键快照事实全部在场。
def test_snapshot_facts_present() -> None:
    for fact in SNAPSHOT_FACTS:
        assert fact in _TEXT, "关键快照事实缺失: {0}".format(fact)


# 覆盖项 6：D14D L3_READY 边界（=false 在场，=true 缺席）。
def test_d14d_l3_ready_boundary() -> None:
    assert "L3_READY=true" in _TEXT
    assert "release_ready=false" in _TEXT
    assert "production_ready=false" in _TEXT
    assert "release_ready=true" not in _TEXT, "D14D 边界被破坏: release_ready=true 在场"
    assert "production_ready=true" not in _TEXT, "D14D 边界被破坏: production_ready=true 在场"


# 覆盖项 7：D15E 未宣布最终锁、D14E 未签署。
def test_d15e_not_declared_and_d14e_not_signed() -> None:
    assert "D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ" in _TEXT
    assert "D15E_FINAL_SUBMISSION_LOCK_DECLARED=false" in _TEXT
    assert "D14E_FINAL_ACCEPTANCE=BLOCKED" in _TEXT
    assert "D14E_SIGNOFF_STATUS=BLOCKED" in _TEXT


# 覆盖项 8：C1~C8 与 BOUND-1~BOUND-8 全部在场，claim mapping 含允许性判定列。
def test_claim_mapping_c1_to_c8() -> None:
    block = _section_block("## 5. Claim-to-Evidence Mapping（声明—证据映射）", "## 6.")
    rows = _table_rows(block)
    claim_codes = {
        m.group(1)
        for cells in rows
        if (m := re.match(r"^C([1-8])\s", cells[0]))
    }
    assert claim_codes == {"1", "2", "3", "4", "5", "6", "7", "8"}, (
        "claim 码不齐全: {0}".format(sorted(claim_codes))
    )
    assert "是否允许作为最终比赛事实" in _TEXT, "claim mapping 缺少允许性判定列"
    assert "当前是否允许作为最终比赛事实" in _TEXT, "claim mapping 表头列名缺失"


def test_bound_1_to_8_present() -> None:
    for i in range(1, 9):
        assert "BOUND-{0}".format(i) in _TEXT, "BOUND-{0} 缺失".format(i)


# 覆盖项 9：文档引用的 evidence 路径在磁盘真实存在（fail-closed，缺失即失败）。
def test_evidence_paths_exist_on_disk() -> None:
    for rel in EVIDENCE_REL_PATHS:
        path = REPO_ROOT / rel
        assert path.exists(), "evidence 路径不存在（fail-closed）: {0}".format(rel)


# 覆盖项 10：无 L2/L3 已执行或 Runtime 结论表述；显式声明在场；矩阵线状态不与 E15 行混标。
def test_no_l2_l3_runtime_conclusion_statements() -> None:
    for phrase in ("已执行 L2", "L3 已通过", "Runtime 结论已生成"):
        assert phrase not in _TEXT, "发现越级 Runtime/L2/L3 表述: {0}".format(phrase)


def test_explicit_boundary_declarations_present() -> None:
    for phrase in (
        "不宣布 D15E FINAL LOCK",
        "不签署 D14E final acceptance",
        "不执行 L2/L3",
        "不生成新的 Runtime 结论",
    ):
        assert phrase in _TEXT, "缺少显式边界声明: {0}".format(phrase)


def test_matrix_line_status_not_mixed_with_e15_rows() -> None:
    assert "DOCUMENTATION_PREPARATION" in _TEXT, "矩阵线状态 DOCUMENTATION_PREPARATION 缺失"
    assert "READY_FOR_REVIEW" in _TEXT, "矩阵线状态 READY_FOR_REVIEW 缺失"
    parsed = _e15_matrix_status()
    e15_status_values = set(parsed.values())
    matrix_line_tokens = {"DOCUMENTATION_PREPARATION", "READY_FOR_REVIEW"}
    assert not (e15_status_values & matrix_line_tokens), (
        "矩阵线状态与 E15 行混标，E15 状态值={0}".format(sorted(e15_status_values))
    )


# 覆盖项 11：provenance 行级绑定与反向漂移守卫（HIGH-03 补强）。
def test_d14c_d15c_provenance_association() -> None:
    """真实文档快照：D14C / D15C / C6 / §7 行级 provenance 绑定全部成立。

    §6 D14C 行与 §5 C6 行只绑定 PR #156 / test/D14C… / 77319aa4…；
    §6 D15C 行与 §7 D15C handoff 前置行绑定 PR #167 / feat/C-hook-evidence /
    b5f8154… / a4034c9…；§7 D14C 闭合前置行只绑定 PR #156 / test/D14C… /
    77319aa4…。
    """
    _assert_d14c_association(_TEXT)
    _assert_d15c_association(_TEXT)
    _assert_c6_association(_TEXT)
    _assert_final_lock_trigger_association(_TEXT)


def test_d14b_merged_row_binding_and_formal_boundary() -> None:
    """PR #124 已合入 main，D14B row 必须绑定 merge identity 并保留 Formal debt。"""
    _assert_d14b_association(_TEXT)
    _assert_d14b_formal_boundary(_TEXT)


def test_reverse_drift_d14c_row_bound_to_pr167_rejected() -> None:
    """反向漂移 1：把 §6 D14C 行错绑为 PR #167 / 404c7e1… 后守卫必须抛 AssertionError。

    先自检注入真实生效（漂移后 D14C 行确实含 PR #167），再断言守卫判别力。
    """
    row = _upstream_row(_TEXT, "D14C")
    drifted_row = row.replace("PR #156", "PR #167").replace(
        "77319aa4ce75d7f7fe4d7ed64f7332cffdb88441",
        "404c7e1cadd188d8e64547c992a77bec28e457e2",
    )
    drifted = _TEXT.replace(row, drifted_row)
    drifted_upstream = _upstream_row(drifted, "D14C")
    assert "PR #167" in drifted_upstream, "反向漂移注入未生效（自检失败），测试空转"
    _expect_assertion_error(_assert_d14c_association, drifted)


def test_reverse_drift_d15c_row_no_artifact_rejected() -> None:
    """反向漂移 2：把 §6 D15C 行写成「不适用（无该产物）」后守卫必须抛 AssertionError。

    漂移行仍保留 PR #167 / feat/C-hook-evidence / b5f8154… / a4034c9… 绑定，仅把产物
    状态写成无产物；先自检注入真实生效，再断言守卫判别力。
    """
    row = _upstream_row(_TEXT, "D15C")
    drifted_row = row.replace("EXISTS", "不适用（无该产物）")
    drifted = _TEXT.replace(row, drifted_row)
    drifted_upstream = _upstream_row(drifted, "D15C")
    assert "无该产物" in drifted_upstream, "反向漂移注入未生效（自检失败），测试空转"
    _expect_assertion_error(_assert_d15c_association, drifted)


def test_reverse_drift_d14b_row_stale_snapshot_rejected() -> None:
    """把 D14B row 回退为 PR_OPEN/NON_MAIN_BRANCH 旧快照后守卫必须失败。"""
    row = _upstream_row(_TEXT, "D14B")
    drifted_row = (
        row.replace(
            "fb4531e673bb5f02d6a109ec0f467cb6d384e927",
            "7445c2ee2753100f46d0d8062f28ccf0aed22aad",
        )
        .replace(
            "a7abb1e71c03c4f1558e5c6a9eff2b9f36437993",
            "8fbc705c6b9d1e8966ec688d0dfda9a509dc0f20",
        )
        .replace("是（PR #124 已合入 main", "否（NON_MAIN_BRANCH；PR_OPEN")
    )
    drifted = _TEXT.replace(row, drifted_row)
    drifted_upstream = _upstream_row(drifted, "D14B")
    assert "PR_OPEN" in drifted_upstream, "反向漂移注入未生效（自检失败），测试空转"
    _expect_assertion_error(_assert_d14b_association, drifted)


def test_reverse_drift_d14b_formal_debt_removed_rejected() -> None:
    """删除或提升 D14B Formal debt 边界后守卫必须失败。"""
    row = _upstream_row(_TEXT, "D14B")
    drifted_row = row.replace(
        "D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS",
        "D14B_TASK=COMPLETE",
    )
    drifted = _TEXT.replace(row, drifted_row)
    drifted_upstream = _upstream_row(drifted, "D14B")
    assert "D14B_TASK=COMPLETE" in drifted_upstream, "反向漂移注入未生效（自检失败），测试空转"
    _expect_assertion_error(_assert_d14b_formal_boundary, drifted)


# 覆盖项 12：current main identity / D14E historical merge association（HIGH-01/HIGH-02）。
def test_current_main_and_d14e_historical_merge_association() -> None:
    """§2.1 / BOUND-7 current main 一致为 a7abb1e…；D14E 行绑定 PR #171 merge commit。"""
    _assert_current_main_association(_TEXT)
    _assert_d14e_row_association(_TEXT)


def test_reverse_drift_bound7_current_main_reverted_rejected() -> None:
    """反向漂移 A：BOUND-7 current main 回退成 3ef0ce… 后守卫必须抛 AssertionError。"""
    block = _bound7_block(_TEXT)
    drifted_block = block.replace(CURRENT_MAIN_SHA, PR171_MERGE_SHA)
    assert drifted_block != block, "反向漂移注入未生效（自检失败），测试空转"
    assert CURRENT_MAIN_SHA not in drifted_block, "反向漂移注入未生效（自检失败），测试空转"
    drifted = _TEXT.replace(block, drifted_block)
    _expect_assertion_error(_assert_current_main_association, drifted)


def test_reverse_drift_d14e_row_main_head_label_rejected() -> None:
    """反向漂移 B：D14E 行 merge commit 改写成 main HEAD=3ef0ce… 后必须抛 AssertionError。"""
    row = _upstream_row(_TEXT, "D14E")
    drifted_row = row.replace(
        "merge commit=" + PR171_MERGE_SHA, "main HEAD=" + PR171_MERGE_SHA
    )
    assert drifted_row != row, "反向漂移注入未生效（自检失败），测试空转"
    assert "main HEAD=" + PR171_MERGE_SHA in drifted_row, (
        "反向漂移注入未生效（自检失败），测试空转"
    )
    drifted = _TEXT.replace(row, drifted_row)
    _expect_assertion_error(_assert_d14e_row_association, drifted)


# 覆盖项 13：MEDIUM-01 canonical 状态词收口。
def test_d14b_formal_status_token_canonical() -> None:
    assert "D14B_FORMAL_L3=NOT_RUN/UNVERIFIED" in _TEXT
    assert "D14B_FORMAL_L3=UNVERIFIED" not in _TEXT, (
        "D14B_FORMAL_L3 存在非 canonical 独立写法（MEDIUM-01）"
    )


def test_no_non_canonical_d15e_state_aliases() -> None:
    for alias in NON_CANONICAL_D15E_STATE_ALIASES:
        assert alias not in _TEXT, "存在非 canonical D15E 状态别名: {0}".format(alias)


# 覆盖项 14：MEDIUM-02 D15E guard 的 CI 边界声明。
def test_d15e_guard_ci_boundary_declared() -> None:
    for phrase in D15E_GUARD_CI_BOUNDARY_PHRASES:
        assert phrase in _TEXT, "缺少 D15E guard CI 边界声明: {0}".format(phrase)
