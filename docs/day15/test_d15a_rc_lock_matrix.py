"""D15A A 轨发布候选锁定矩阵与状态基线文档确定性静态事实测试。

性质：源文档级确定性静态事实测试（纯 stdlib，只读文档原文，不修改任何文件、
不访问网络、不依赖麒麟 Runtime、无 conditional/unconditional skip）。测试自行
读取 `docs/day15/00_d15a_rc_lock_matrix_20260906.md` 后断言既定事实，不做实现
猜测；文档缺失或事实漂移即测试失败（fail-closed），禁止通过删除矩阵事实或
改写状态来让测试通过。

覆盖断言（与已批准 plan / Task 约束对应）：
1. 两个允许文件（本测试与其守卫文档）存在且文档含全部 7 个必需章节标题；
2. A15-1/A15-2/A15-3 每个锁点**恰好一个**完整表格行（M-2b：该行必须**严格三列**
   lock-id | 锁定内容 | 状态）：以多行正则整行定位 `| A15-x | ... |`，要求恰好
   命中一行；解析该行全部 cells 后先断言 `len(cells) == 3`（第四列 / 额外
   status cell / 混合状态一律 fail-closed），再断言首列 `cells[0]` 精确等于锁点
   id，最后在受控 markdown-backtick normalization 后断言第三状态列 `cells[2]`
   精确等于 `WAITING_PREREQ`；不使用 `any(WAITING_PREREQ)` 接受重复/冲突行，
   也**不**在断言列数前用 `cells[-1]` 验证状态；
3. 全文不出现越级词（FINAL_LOCK / LOCKED / L3_READY / HOST_VERIFIED /
   RUNTIME_VERIFIED / D14A complete / production ready / release ready 等），
   其中 LOCKED 等以独立 token（词边界）判定，BLOCKED / NOT_FROZEN /
   RUNTIME_UNVERIFIED 等受控词不受影响；
4. 文档包含关键仓库事实字符串（preparation_base_commit 固定 SHA、历史 runtime
   被测提交 SHA、current_head / current_tested_runtime_commit 动态语义、0.1.0-d14a、
   PENDING_P0_I3_RESELECTION、RUNTIME_EVIDENCE_STALE、NOT_FROZEN、
   HANDOFF_REQUIRED、formal_baseline_complete=false 等）；
5. 交付物身份明确为发布包内 `kylin_embedding*.so`（runtime/bridge/），
   wheel / Kaiming 明确排除且未新增构建体系；
6. 刷新规则（git rev-parse HEAD / git status --porcelain /
   git diff --name-only current_tested_runtime_commit..HEAD 三分类）与版本一致性
   程序（EXPECT_SOURCE_COMMIT / EXPECT_PACKAGE_VERSION / manifest.source_commit）
   写入文档；
7. M2-A 溯源语义：preparation_base_commit（历史固定卡点）与 current_head（动态
   git rev-parse HEAD，fail-closed、不 Mock、绑定窗口内不硬编码 40 位 SHA）分离；
   历史/当前 tested runtime commit 身份分离且 current_tested_runtime_commit 当前
   未选择；
8. M2-A 机器守卫边界：仅覆盖受控英文 sentinel、结构化状态行与已定义
   provenance/state token，不覆盖中文/自然语言同义越级与 evidence 真实性；
9. M3-A 外部施工台账非仓库权威发布契约来源，且 15_DAY_PLAN.md / pseudo-repo 路径
   在文档与测试中均被负向守卫去除；
10. M4-A 实际 PR #164 文件范围为两个**新增 docs 文件**（本守卫文档、本测试）
    加一个**既有 workflow 修改**（.github/workflows/baseline-check.yml，仅把守卫
    接入既有 d14a-packaging-provenance job、保持 fetch-depth: 0、不新增
    job/runner），且文档不含过时的 blanket `.github/**` 排除。
"""

import re
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_DOC_FILE = _DOC_DIR / "00_d15a_rc_lock_matrix_20260906.md"

# 仓库事实（Task 已批准并核实的 as-of 2026-09-06 快照）。
# preparation_base_commit：锁准备基线的历史固定 SHA（随 preparation HEAD 前移不更新，
# 不作为 current_head）。current_head 为执行时 git rev-parse HEAD 动态事实，不在此落库。
_PREP_BASE_SHA = "3138e942770ec1f9863e86c03da4df9dd1ad8703"
# historical_tested_runtime_commit（历史 runtime 包真实执行提交，D14A 契约 §1.1 现行值）。
_BASELINE_SHA = "e3d4b9d565e2c3c153973125b3c071225e1b9e4d"
_VERSION = "0.1.0-d14a"

# 7 个必需章节标题（文档中的实际标题）。
_REQUIRED_SECTIONS = [
    "## 1. 目的与范围",
    "## 2. 交付物身份判定",
    "## 3. 锁定状态机与 A15 锁点状态表",
    "## 4. 仓库事实快照与刷新规则",
    "## 5. 正式锁验收门禁与版本一致性检查程序",
    "## 6. 已知限制与 blockers",
    "## 7. 状态词纪律与责任",
]

# 越级状态词（独立 token，词边界匹配；受控词 BLOCKED/NOT_FROZEN/
# RUNTIME_UNVERIFIED/RUNTIME_EVIDENCE_STALE 等不在名单内，不受影响）。
_FORBIDDEN_TOKENS = [
    "FINAL_LOCK",
    "LOCKED",
    "L3_READY",
    "HOST_VERIFIED",
    "RUNTIME_VERIFIED",
]

# 越级英文短语（原词整体缺席断言）。
_FORBIDDEN_PHRASES = [
    "D14A complete",
    "production ready",
    "release ready",
]

# 文档必须包含的关键仓库事实字符串。
_KEY_FACTS = [
    _PREP_BASE_SHA,
    _BASELINE_SHA,
    _VERSION,
    "current_head",
    "preparation_base_commit",
    "historical_tested_runtime_commit",
    "current_tested_runtime_commit",
    "PENDING_P0_I3_RESELECTION",
    "RUNTIME_EVIDENCE_STALE",
    "NOT_FROZEN",
    "WAITING_PREREQ",
    "HANDOFF_REQUIRED",
    "PACKAGE_IMPLEMENTATION_CANDIDATE",
    "formal_baseline_complete",
    "formal_baseline_complete=false",
    "DOCUMENTATION_PREPARATION",
    "READY_FOR_REVIEW",
    "TD-061",
    "D14D_ENV_PREPARED",
    "READY(r3)",
    "D14D_FORMAL_L3",
    "BLOCKED / NOT_STARTED",
    "G8",
    "INVALIDATED",
    "外部施工台账",
]

# 刷新规则与版本一致性程序关键字（M2-A：刷新基线改为
# current_tested_runtime_commit..HEAD，不永久绑定历史 e3d4 基线）。
_REFRESH_RULES = [
    "git rev-parse HEAD",
    "git status --porcelain",
    "git diff --name-only",
    "current_tested_runtime_commit..HEAD",
    "EVIDENCE_CURRENT",
    "DOCS_EVIDENCE_ONLY",
    "RUNTIME_EVIDENCE_STALE",
    "重新打包",
    "重算 hash",
    "重跑真实 VM",
]

_VERSION_CONSISTENCY = [
    "VERSION",
    "manifest.package_version",
    "EXPECT_SOURCE_COMMIT",
    "EXPECT_PACKAGE_VERSION",
    "manifest.source_commit",
    "40 位完整",
    "build_release_package.sh",
    "systemd_install.sh",
]

# 交付物身份断言关键字。
_DELIVERY_IDENTITY = [
    "dist/kylin-memory-a-d14a-0.1.0-d14a",
    "kylin_embedding*.so",
    "runtime/bridge",
    "pybind11",
    "CMake",
]


def _doc_text() -> str:
    assert _DOC_FILE.is_file(), f"缺失文档: {_DOC_FILE}"
    return _DOC_FILE.read_text(encoding="utf-8")


def _assert_all_present(text: str, tokens, where: str):
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{where} 缺少既定事实 token: {missing}"


# ---------- 1. 章节齐全 ----------

def test_required_sections_present():
    text = _doc_text()
    missing = [s for s in _REQUIRED_SECTIONS if s not in text]
    assert not missing, f"文档缺少必需章节标题: {missing}"


# ---------- 2. A15 表格严格三列唯一状态行精确绑定 WAITING_PREREQ ----------

def test_a15_rows_waiting_prereq():
    text = _doc_text()
    for lock in ("A15-1", "A15-2", "A15-3"):
        # M-1 保留：A15-x 状态行与 WAITING_PREREQ 的行级绑定断言。
        # M-2 收紧：每个锁点在表格中必须**恰好一行**，且该唯一行必须**严格三列**。
        # M-2b：列结构守卫——用多行正则整行定位形如 | A15-x | ... | 的表格行；
        # 要求 len(rows) == 1，否则 fail-closed 报重复/歧义；解析该行全部 cells
        # 后**先**断言恰好三列（lock-id | 锁定内容 | 状态），任何第四列 / 额外
        # status cell / 行内多余分隔一律 fail-closed；随后断言首列 cells[0]
        # 精确等于锁点 id；最后在受控 markdown-backtick normalization 后精确校验
        # 第三状态列 cells[2] 等于 WAITING_PREREQ。**禁止**在断言列数前用 cells[-1]
        # 取状态，也**不**使用 any(WAITING_PREREQ) 接受重复/冲突行。
        pattern = re.compile(
            rf"^\|\s*{re.escape(lock)}\s*\|.*\|\s*$", re.MULTILINE
        )
        rows = pattern.findall(text)
        assert len(rows) == 1, (
            f"锁点 {lock} 表格必须恰好一行（现状 {len(rows)}，重复/歧义应 fail-closed）"
            f": {rows!r}"
        )
        row = rows[0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        # M-2b：列结构守卫——先解析全部 cells 并断言恰好三列
        # （lock-id | 锁定内容 | 状态）；任何第四列 / 额外 status cell /
        # 行内多余分隔一律 fail-closed；禁止在列数断言前用 cells[-1] 取状态。
        assert len(cells) == 3, (
            f"锁点 {lock} 唯一表格行必须严格三列；现状 {len(cells)} 列，"
            f"额外状态列应 fail-closed: {row!r}"
        )
        assert cells[0] == lock, (
            f"锁点 {lock} 唯一行首列 cells[0] 必须精确等于锁点 id；"
            f"实际 {cells[0]!r}"
        )
        # 受控 markdown-backtick normalization 后精确校验第三状态列（cells[2]）。
        status = cells[2].strip().strip("`").strip()
        assert status == "WAITING_PREREQ", (
            f"锁点 {lock} 唯一行第三状态列 cells[2] 必须精确等于 "
            f"WAITING_PREREQ；实际 {status!r}"
        )
        # 既有断言保留（不删除、不弱化）。
        assert lock in text, f"缺少锁点行 {lock}"
        assert "WAITING_PREREQ" in text, f"锁点 {lock} 状态行缺少 WAITING_PREREQ"
    # 本矩阵线独立状态（DOCUMENTATION_PREPARATION / READY_FOR_REVIEW），
    # 且明确声明与其他三行不混标。
    assert "DOCUMENTATION_PREPARATION" in text
    assert "READY_FOR_REVIEW" in text
    assert "混标" in text, "文档必须明确本矩阵线不得与其他锁点行混标"


# ---------- 3. 越级词缺席（独立 token / 词边界，受控词不受影响） ----------

def test_forbidden_tokens_absent():
    text = _doc_text()
    for token in _FORBIDDEN_TOKENS:
        pattern = re.compile(rf"\b{re.escape(token)}\b")
        m = pattern.search(text)
        assert m is None, f"文档出现越级状态词 {token!r}"


def test_forbidden_phrases_absent():
    text = _doc_text()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in text, f"文档出现越级短语 {phrase!r}"


# ---------- 4. 关键仓库事实字符串 ----------

def test_key_facts_present():
    text = _doc_text()
    _assert_all_present(text, _KEY_FACTS, "文档")


def test_controlled_status_words_allowed():
    """受控状态词必须可用（越级词检查不得误伤受控词）。"""
    text = _doc_text()
    for controlled in (
        "BLOCKED",
        "NOT_FROZEN",
        "RUNTIME_UNVERIFIED",
        "RUNTIME_EVIDENCE_STALE",
        "NOT_STARTED",
        "PENDING_P0_I3_RESELECTION",
        "WAITING_PREREQ",
        "HANDOFF_REQUIRED",
        "INVALIDATED",
        "NOT_RUN",
    ):
        assert controlled in text, f"受控状态词 {controlled} 不应被删除"


# ---------- 5. 交付物身份：so 为交付物，wheel/Kaiming 排除 ----------

def test_delivery_identity_so():
    text = _doc_text()
    _assert_all_present(text, _DELIVERY_IDENTITY, "文档")
    # 交付物身份必须明确：Bridge = kylin_embedding*.so（pybind11 产物）。
    assert "正式交付物" in text or "正式交付物身份" in text


def test_wheel_kaiming_not_deliverable():
    """wheel / Kaiming 只以『不在 A15 交付范围』等排除语义出现，不得写成交付物。"""
    text = _doc_text()
    for word in ("wheel", "Kaiming"):
        assert word in text, f"文档应登记 {word} 的排除语义"
    # 排除语义必须与交付物身份隔离：不含『wheel 是正式交付物』类表述。
    assert "不在 A15 交付范围" in text, "文档缺少 wheel/Kaiming 不在 A15 交付范围的排除声明"
    assert "kylin_embedding*.so" in text
    # 明确无 wheel 构建体系（不得把 wheel 写成 A15 交付物）。
    assert "wheel 构建体系" in text


# ---------- 6. 刷新规则与版本一致性程序 ----------

def test_refresh_rules_present():
    text = _doc_text()
    _assert_all_present(text, _REFRESH_RULES, "刷新规则")


def test_version_consistency_procedure_present():
    text = _doc_text()
    _assert_all_present(text, _VERSION_CONSISTENCY, "版本一致性程序")
    # 版本一致性等式：VERSION == manifest.package_version == 0.1.0-d14a。
    assert "VERSION" in text and "manifest.package_version" in text
    assert "0.1.0-d14a" in text


def test_no_fabricated_execution_result():
    """版本一致性检查程序仅作为『正式锁时执行』的定义写入，不得虚构已执行结果。"""
    text = _doc_text()
    assert "正式锁时执行" in text or "正式锁时执行的程序" in text, (
        "版本一致性程序须声明为正式锁时执行"
    )
    assert "不虚构任何已执行结果" in text, "文档必须声明不虚构已执行结果"


# ---------- 7. M2-A 溯源身份分离与机器守卫边界 ----------

def test_preparation_base_fixed_and_current_head_dynamic():
    """M2-A：preparation_base_commit 为历史固定 SHA；current_head 为动态
    git rev-parse HEAD（fail-closed、不 Mock、不默认伪造），绑定窗口不得硬编码
    40 位 SHA。"""
    text = _doc_text()
    assert "preparation_base_commit" in text
    assert _PREP_BASE_SHA in text
    idx = text.find("current_head")
    assert idx != -1, "文档缺少 current_head 标签"
    window = text[idx : idx + 300]
    assert "git rev-parse HEAD" in window, (
        "current_head 未与 git rev-parse HEAD 动态事实表达绑定"
    )
    assert "fail-closed" in window, "current_head 定义窗口缺少 fail-closed 语义"
    assert "Mock" in window, "current_head 定义窗口缺少不得 Mock/默认伪造约束"
    # 禁止硬编码赋值行：HEAD = [40 hex] / current_head = [40 hex]。
    hardcoded = re.compile(
        r"^\s*(HEAD|current_head)\s*=\s*[0-9a-f]{40}\s*$", re.MULTILINE
    )
    m = hardcoded.search(text)
    assert m is None, f"文档存在硬编码 current_head/HEAD 赋值行: {m.group(0)!r}"


def test_runtime_identity_split():
    """M2-A：historical_tested_runtime_commit 保留固定 e3d4；current_tested_runtime_commit
    为当前声明（as-of 未选择）；刷新基线为 current_tested_runtime_commit..HEAD，
    永久 e3d4 基线（e3d4b9d...）..HEAD 全文缺席。"""
    text = _doc_text()
    assert "historical_tested_runtime_commit" in text
    assert _BASELINE_SHA in text
    assert "current_tested_runtime_commit" in text
    assert "未选择" in text, "current_tested_runtime_commit 当前必须声明为未选择"
    assert "current_tested_runtime_commit..HEAD" in text
    assert f"{_BASELINE_SHA}..HEAD" not in text, (
        "不得存在永久绑定历史 e3d4 基线的刷新范围（e3d4b9d.....HEAD）"
    )
    assert "不永久绑定历史基线 e3d4" in text, "刷新规则必须声明不永久绑定历史 e3d4 基线"


def test_machine_guard_boundary_declared():
    """M2-A：机器守卫仅覆盖受控英文 sentinel、结构化状态行与已定义 provenance/state
    token；不覆盖中文/自然语言同义越级与 evidence 真实性；不得引入 NLP/LLM 检测。"""
    text = _doc_text()
    _assert_all_present(
        text,
        (
            "机器守卫",
            "受控英文 sentinel",
            "结构化状态行",
            "provenance/state token",
            "NLP",
            "LLM",
            "独立 Reviewer",
            "人工审查",
            "不引入",
        ),
        "机器守卫边界",
    )


def test_external_ledger_not_repo_contract():
    """M-3：外部 D15-A project / construction ledger（外部施工台账）不是仓库权威发布
    契约来源；文档不得再出现 `docs/project/15_DAY_PLAN.md:1021` 这类 pseudo-repo 施工
    台账路径。负向守卫：15_DAY_PLAN / docs/project 伪仓库路径不得重新出现。"""
    text = _doc_text()
    _assert_all_present(
        text,
        (
            "外部施工台账",
            "D15-A project / construction",
            "锁定 Bridge so/wheel、依赖清单和构建说明",
            "仓库权威发布契约",
            "docs/day14/00_d14a_release_package_contract.md",
            "packaging/release",
        ),
        "外部施工台账澄清",
    )
    assert "不属于本仓库版本化的权威发布契约来源" in text, (
        "文档必须明确外部施工台账不属于本仓库版本化的权威发布契约来源"
    )
    # 负向守卫：pseudo-repo 施工台账路径 token 不得重新出现（fail-closed）。
    assert "15_DAY_PLAN" not in text, (
        "文档不得再出现 15_DAY_PLAN.md 或类似 pseudo-repo 施工台账 token"
    )
    assert "docs/project" not in text, (
        "文档不得再出现 docs/project/ 伪仓库路径"
    )
    assert r"15_DAY_PLAN.md" not in text
    assert "15_DAY_PLAN.md:1021" not in text


# ---------- 10. M4-A 三文件 PR 范围与无 stale .github/** 排除 ----------

# 实际 PR #164 涉及的文件（三个）。
_PR_SCOPE_FILES = [
    "00_d15a_rc_lock_matrix_20260906.md",
    "test_d15a_rc_lock_matrix.py",
    ".github/workflows/baseline-check.yml",
]


def test_pr_scope_three_files():
    """M-4：§1.2 必须准确列出三个实际 PR 文件；workflow 仅把守卫接入既有
    d14a-packaging-provenance job（保持 fetch-depth: 0、不新增 job/runner）；
    且不得再存在过时的 blanket `.github/**` 排除。"""
    text = _doc_text()
    for f in _PR_SCOPE_FILES:
        assert f in text, f"§1.2 必须列出实际 PR 文件 {f!r}"
    # workflow 接入语义：既有 d14a-packaging-provenance job、fetch-depth: 0、
    # 不新增 job、不新增 runner。
    _assert_all_present(
        text,
        (
            "d14a-packaging-provenance",
            "fetch-depth: 0",
            "不新增 job",
            "不新增",
        ),
        "workflow 接入语义",
    )
    assert "runner" in text, "文档应声明不新增 runner"
    # 负向守卫：不得再存在独立 blanket 排除 `.github/**`（排除列表语境）。
    # 文档中 `.github` 仅以 workflow 文件路径 / 有限接入声明形式出现；若某个
    # 「不修改 …」排除列表项仍包含 `.github`，即为过时 blanket 排除，fail-closed。
    for line in text.splitlines():
        stripped = line.strip()
        if "不修改" in stripped and stripped.startswith("-"):
            assert ".github" not in stripped, (
                f"排除列表不得再含 blanket `.github/**` 项: {line!r}"
            )
    assert "不整体排除 `.github/**`" in text, (
        "文档应明确不再整体排除 .github/**"
    )


# ---------- 运行入口（直接执行时同样可用） ----------

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
