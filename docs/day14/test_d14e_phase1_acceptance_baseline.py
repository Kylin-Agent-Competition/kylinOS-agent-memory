"""D14E 第一阶段验收基线文档确定性静态事实测试。

性质：源码级确定性静态事实守卫（纯 stdlib，无网络、无真实 VM、无跨分支文件、
无 conditional/unconditional skip、不读取不修改历史 evidence、不新增 evidence/
index.yaml 条目）。

方式：基于本文件（__file__）定位仓库根（docs/day14/..）：

- 目标文档固定为 docs/day14/23_d14e_phase1_acceptance_baseline_20260908.md；
- `git rev-parse HEAD` 仅在断言"动态 HEAD 合法且不得与 frozen tested_commit
  伪造相等"时作为执行时真源（命令失败即测试错误，不静默、不伪造）；
- frozen tested_commit / main HEAD 快照 / evidence 路径 / 哈希为已批准
  TASK_JSON 与 plan 中实测核验的历史事实字面量，用于验证文档与既定事实一致。

测试失败即代表文档与既定事实不一致（fail-closed），禁止放宽断言、吞异常或跳过。

覆盖事实（与已批准 plan / TASK_JSON 对应）：
1. 目标文档存在；
2. as-of=2026-09-08 快照身份、分支、main HEAD 2bd5948 与 commit 信息绑定；
3. 独立状态行三条且取值正确（D14E_PHASE1_ACCEPTANCE_BASELINE=READY /
   D14E_FINAL_ACCEPTANCE=BLOCKED / D14E_SIGNOFF_STATUS=BLOCKED）；
4. 全文不得出现最终签署/越级字面量：D14E=PASS、D14E=DONE、
   BUSINESS_SIGNOFF=PASS、SECURITY_SIGNOFF=PASS、HOST_VERIFIED、
   production_ready=true、release_ready=true、D14E_FINAL_ACCEPTANCE=ACCEPTED；
5. 文档显式区分 main HEAD 2bd5948 与 frozen tested_commit ba3b50e1bd…（≠），
   并声明快照可失效、签署前必须 git rev-parse HEAD / git status 重新核验；
6. A–E 五节标题齐全；
7. Acceptance Matrix 恰有 B1..B12 十二行；D14B 相关行状态为 BLOCKED_BY_D14B、
   D14C 相关行状态为 BLOCKED_BY_D14C；
8. D14D 边界保留：L3_READY=true 且 release_ready=false / production_ready=false；
9. D14B / D14C upstream 受控 pending 表述与扫描 refs 齐全（含 BLOCKED /
   UNVERIFIED / 未合入 main / 无 formal evidence root）；
10. C 节 8 类禁止 overclaim 边界标记 BOUND-1…BOUND-8 齐全；
11. 引用 evidence 路径与 evidence/index.yaml 既有条目 id 存在且未被改写；
12. 运行时边界：文档声明 RUNTIME_NOT_REQUIRED，不声明 HOST_VERIFIED、
    不把文档准备等同于最终签署。
"""

import re
import subprocess
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DOC_DIR.parent.parent
_DOC = _DOC_DIR / "23_d14e_phase1_acceptance_baseline_20260908.md"

# 已批准 TASK_JSON / plan 中核验的历史事实字面量（快照身份与冻结 identity）。
_SNAPSHOT_DATE = "as-of=2026-09-08"
_BRANCH = "test/D14E-business-security-final-acceptance"
_MAIN_HEAD_SNAPSHOT = "2bd5948"
_TESTED_COMMIT = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"

_STATUS_LINES = (
    "D14E_PHASE1_ACCEPTANCE_BASELINE=READY",
    "D14E_FINAL_ACCEPTANCE=BLOCKED",
    "D14E_SIGNOFF_STATUS=BLOCKED",
)

# 最终签署 / 越级字面量（全文禁止出现）。
_FORBIDDEN_LITERALS = (
    "D14E=PASS",
    "D14E=DONE",
    "BUSINESS_SIGNOFF=PASS",
    "SECURITY_SIGNOFF=PASS",
    "HOST_VERIFIED",
    "production_ready=true",
    "release_ready=true",
    "D14E_FINAL_ACCEPTANCE=ACCEPTED",
)

_SECTION_HEADINGS = (
    "## A. 当前开工与验收状态",
    "## B. D14E Acceptance Matrix",
    "## C. Claim-to-Evidence 与比赛叙事事实映射",
    "## D. 未闭合 Upstream Dependency 清单",
    "## E. Final Delta Review 与 Signoff 触发条件",
)

# 矩阵行标记：| B1 | … | B12 |（每行单行物理行）。
_MATRIX_ROW_RE = re.compile(r"^\| B([0-9]+) \|")
_MATRIX_ROW_IDS = [f"B{i}" for i in range(1, 13)]

# 引用 evidence 路径 / index.yaml 既有条目（只引用、不改写）。
_EVIDENCE_REFERENCES = (
    "evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/"
    "D13D_FREEZE_RECORD_20260908.md",
    "evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/"
    "evidence/D13E_FORMAL_REPORT_V1.json",
    "evidence/l3-kylin-vm/d14a_final_package_20260908/"
    "D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md",
    "evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/",
    "D14A-FINAL-PACKAGE-FREEZE",
    "D13D-FORMAL-CLOSURE-BA3B50E-20260908",
)

_SHA40 = re.compile(r"\b[0-9a-f]{40}\b")


def _text() -> str:
    assert _DOC.is_file(), f"缺失目标文档: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _assert_all(text: str, tokens, where: str):
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{where} 缺少既定事实 token: {missing}"


def _head_sha() -> str:
    """执行时取得当前 HEAD（git rev-parse HEAD）；失败即测试错误。

    拒绝伪造：返回值必须是 40 位十六进制，否则视为测试失败而非静默通过。
    """
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"git rev-parse HEAD 失败 (rc={proc.returncode}): {proc.stderr.strip()}"
    )
    sha = proc.stdout.strip()
    assert _SHA40.fullmatch(sha), f"git rev-parse HEAD 输出非法: {sha!r}"
    return sha


def _matrix_rows(text: str) -> dict:
    """解析矩阵行：行号 -> 整行文本。仅统计 | B<n> | 开头的物理行。"""
    rows = {}
    for line in text.splitlines():
        m = _MATRIX_ROW_RE.match(line)
        if m:
            rows[int(m.group(1))] = line
    return rows


# ---------- 1. 目标文档存在 ----------

def test_target_document_exists():
    assert _DOC.is_file(), f"缺失目标文档: {_DOC}"
    content = _DOC.read_text(encoding="utf-8")
    assert content.strip(), f"目标文档为空: {_DOC}"


# ---------- 2. 快照身份 ----------

def test_snapshot_identity_present():
    text = _text()
    _assert_all(
        text,
        [_SNAPSHOT_DATE, _BRANCH, _MAIN_HEAD_SNAPSHOT,
         "mark PR165 merged and L3_READY (#168)"],
        "快照身份",
    )
    assert _MAIN_HEAD_SNAPSHOT in text and _TESTED_COMMIT in text


def test_main_head_vs_tested_commit_distinction():
    """main HEAD 2bd5948 与 frozen tested_commit ba3b50e1bd… 必须显式区分（≠）。

    以「≠」为中心取窗口，确认两个身份与『main HEAD』『frozen tested_commit』
    标签在同一区分声明中出现（防止混淆身份或写成相等）。
    """
    text = _text()
    assert "main HEAD" in text
    assert "frozen tested_commit" in text
    idx = text.find("≠")
    assert idx != -1, "缺少身份区分符号 ≠"
    window = text[max(0, idx - 160) : idx + 160]
    for token in (_MAIN_HEAD_SNAPSHOT, _TESTED_COMMIT, "main HEAD",
                  "frozen tested_commit"):
        assert token in window, (
            f"身份区分声明窗口内缺少 token {token!r}（身份可能被混淆/写成相等）"
        )


def test_snapshot_staleness_and_revalidation_declared():
    """快照可失效 + 签署前重新核验声明必须存在（防把 2026-09-08 快照当永远事实）。"""
    text = _text()
    _assert_all(
        text,
        ["可失效", "git rev-parse HEAD", "git status", "重新核验"],
        "快照失效/重核验声明",
    )
    # 动态 HEAD 不得与 frozen tested_commit 伪造相等。
    head = _head_sha()
    assert head != _TESTED_COMMIT, (
        f"动态 HEAD {head[:12]}… 与 frozen tested_commit 伪造相等（fail-closed）"
    )
    print(f"[live] HEAD={head}")


# ---------- 3. 三条状态行 ----------

def test_status_lines_exact():
    text = _text()
    for line in _STATUS_LINES:
        assert line in text, f"缺少状态行: {line}"


# ---------- 4. 禁止最终签署 / 越级字面量 ----------

def test_forbidden_escalation_literals_absent():
    """全文不得出现最终签署/越级字面量（fail-closed 负向断言）。"""
    text = _text()
    hits = [lit for lit in _FORBIDDEN_LITERALS if lit in text]
    assert not hits, f"文档出现禁止越级/最终签署字面量: {hits}"


# ---------- 5. A–E 五节 ----------

def test_sections_a_to_e_present():
    text = _text()
    for heading in _SECTION_HEADINGS:
        assert heading in text, f"缺少章节标题: {heading}"
    # 章节顺序校验。
    positions = [text.find(h) for h in _SECTION_HEADINGS]
    assert all(p != -1 for p in positions)
    assert positions == sorted(positions), "章节 A–E 顺序错误"


# ---------- 6. Acceptance Matrix 十二行 ----------

def test_matrix_has_12_rows():
    rows = _matrix_rows(_text())
    missing = [i for i in range(1, 13) if i not in rows]
    assert not missing, f"矩阵缺少行: {missing}"
    assert len(rows) == 12, f"矩阵行数应为 12，实际 {len(rows)}"


def test_matrix_row_required_fields_present():
    """每行必须提供 owner / evidence path / tested commit / package SHA /
    environment/run ID / status / blocker / reviewer 等字段。"""
    rows = _matrix_rows(_text())
    required = ["owner", "required artifact", "evidence path", "tested commit",
                "package SHA", "environment/run ID", "status", "blocker",
                "reviewer"]
    header = _text().splitlines()
    matrix_header = next(
        (ln for ln in header if ln.startswith("| 行 | 事项 | owner |")), "")
    assert matrix_header, "矩阵缺少表头"
    for token in required:
        assert token in matrix_header, f"矩阵表头缺少字段 {token}"
    for i, line in rows.items():
        assert "|" in line, f"矩阵 B{i} 行异常: 缺分隔"
        # 每行 11 列（表头字段数）以字段结构完整。
        assert len([c for c in line.strip().strip("|").split("|")]) == 11, (
            f"矩阵 B{i} 行列数不是 11"
        )


def test_matrix_d14b_controlled_status():
    text = _text()
    rows = _matrix_rows(text)
    row9 = rows[9]
    assert "BLOCKED_BY_D14B" in row9, "B9(D14B) 行状态必须为 BLOCKED_BY_D14B"


def test_matrix_d14c_controlled_status():
    text = _text()
    rows = _matrix_rows(text)
    row10 = rows[10]
    assert "BLOCKED_BY_D14C" in row10, "B10(D14C) 行状态必须为 BLOCKED_BY_D14C"


def test_matrix_d14b_d14c_not_written_as_complete():
    """B9/B10 行状态字段单元格必须为受控 pending/blocked，不得出现完成态词。

    行结构（11 列）：| B# | 事项 | owner | required artifact | evidence path |
    tested commit | artifact/package SHA | environment/run ID | status |
    blocker | reviewer |，因此状态字段索引为 8。
    """
    rows = _matrix_rows(_text())
    for num, expected in ((9, "BLOCKED_BY_D14B"), (10, "BLOCKED_BY_D14C")):
        line = rows[num]
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 11, f"B{num} 行列数异常: {len(cells)}"
        status_cell = cells[8]
        assert status_cell == expected, (
            f"B{num} 状态字段应为 {expected}，实际 {status_cell!r}"
        )
        for token in ("VERIFIED", "ACCEPT", "FROZEN", "L3_READY"):
            assert token not in status_cell, (
                f"B{num} 状态字段出现完成态词 {token}: {status_cell!r}"
            )


# ---------- 7. D14D 边界 ----------

def test_d14d_boundary_preserved():
    text = _text()
    _assert_all(
        text,
        ["L3_READY", "release_ready=false", "production_ready=false",
         "G7 NOT_RUN", "G8 NOT_RUN"],
        "D14D 边界",
    )
    for forbidden in ("release_ready=true", "production_ready=true"):
        assert forbidden not in text, f"D14D 边界被越级: {forbidden}"


# ---------- 8. D14B / D14C upstream pending ----------

def test_d14b_upstream_pending():
    text = _text()
    _assert_all(
        text,
        ["test/D14B-l3-vm-release-regression", "85a35cd", "6fb057a",
         "15_d14b_l3_formal_harness_contract_20260907.md",
         "16_d14b_formal_execution_runbook.md",
         "D14B_FORMAL_L3=BLOCKED", "D14B_FORMAL_RESULT=UNVERIFIED"],
        "D14B upstream pending",
    )


def test_d14c_upstream_pending():
    text = _text()
    _assert_all(
        text,
        ["test/D14C-l3-clean-vm-release-regression", "ac0c58b", "b2f533e",
         "D14C_FORMAL_L3=BLOCKED", "D14C_FORMAL_RESULT=UNVERIFIED",
         "632b24b", "02-09"],
        "D14C upstream pending",
    )


def test_upstream_not_merged_and_no_evidence_root():
    text = _text()
    _assert_all(
        text,
        ["无 formal evidence root", "未 merge 到 main", "未合入 main"],
        "D14B/D14C 未闭合声明",
    )


def test_d14b_d14c_no_completion_claim():
    """不得把 D14B/D14C 写成已完成（fail-closed 负向断言）。"""
    text = _text()
    forbidden = ("D14B_FORMAL_RESULT=VERIFIED", "D14C_FORMAL_RESULT=VERIFIED",
                 "D14B_FORMAL_L3=PASS", "D14C_FORMAL_L3=PASS")
    hits = [t for t in forbidden if t in text]
    assert not hits, f"文档将 D14B/D14C 写成完成态: {hits}"


# ---------- 9. overclaim 边界标记 ----------

def test_overclaim_boundaries_8_present():
    text = _text()
    for i in range(1, 9):
        marker = f"BOUND-{i}"
        assert marker in text, f"缺少禁止 overclaim 边界标记 {marker}"


def test_overclaim_semantics_present():
    """8 类边界语义关键词必须出现（禁止把负向边界写成达成事实）。"""
    text = _text()
    _assert_all(
        text,
        ["绝对安全", "绝不残留", "已正式通过", "已最终通过",
         "不得混淆", "越级", "production ready", "小样本"],
        "overclaim 语义",
    )


# ---------- 10. evidence 引用 ----------

def test_evidence_paths_referenced():
    text = _text()
    for path in _EVIDENCE_REFERENCES:
        assert path in text, f"文档未引用既定 evidence 路径/条目 id: {path}"


# ---------- 11. Runtime 边界 ----------

def test_runtime_not_required_and_no_host_verified():
    text = _text()
    assert "RUNTIME_NOT_REQUIRED" in text, "文档须声明 RUNTIME_NOT_REQUIRED"
    assert "HOST_VERIFIED" not in text, "文档不得声明 HOST_VERIFIED"


def test_document_prep_not_equal_to_signoff():
    """文档必须显式声明『文档准备 ≠ 最终签署』。"""
    text = _text()
    _assert_all(
        text,
        ["不构成", "最终签署", "BLOCKED"],
        "文档准备≠签署声明",
    )


# ---------- 12. 快照 tip 按扫描快照声明（防误当永久事实） ----------

def test_tips_recorded_as_scan_snapshot():
    text = _text()
    for token in ("2026-09-08 扫描快照", "刷新", "85a35cd", "ac0c58b"):
        assert token in text, f"缺失扫描快照/刷新声明 token: {token}"


# ---------- 运行入口（直接执行时同样可用；pytest 收集上面 test_*） ----------

def _run_all():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001 - 报告形式
                failures += 1
                print(f"FAIL {name}: {exc}")
    if failures:
        raise SystemExit(f"{failures} test(s) failed")
    print("ALL PASS")


if __name__ == "__main__":
    _run_all()
