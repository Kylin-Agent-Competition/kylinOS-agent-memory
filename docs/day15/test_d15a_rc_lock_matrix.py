"""D15A A 轨发布候选锁定矩阵与状态基线文档确定性静态事实测试。

性质：源文档级确定性静态事实测试（纯 stdlib，只读文档原文，不修改任何文件、
不访问网络、不依赖麒麟 Runtime、无 conditional/unconditional skip）。测试自行
读取 `docs/day15/00_d15a_rc_lock_matrix_20260906.md` 后断言既定事实，不做实现
猜测；文档缺失或事实漂移即测试失败（fail-closed），禁止通过删除矩阵事实或
改写状态来让测试通过。

覆盖断言（与已批准 plan / Task 约束对应）：
1. 两允许文件存在且文档含全部 7 个必需章节标题；
2. A15-1/A15-2/A15-3 表格状态行均绑定 `WAITING_PREREQ`（以多行正则整行定位
   `| A15-x | ... |` 表格行，再断言行内包含 WAITING_PREREQ，属行级绑定断言）；
3. 全文不出现越级词（FINAL_LOCK / LOCKED / L3_READY / HOST_VERIFIED /
   RUNTIME_VERIFIED / D14A complete / production ready / release ready 等），
   其中 LOCKED 等以独立 token（词边界）判定，BLOCKED / NOT_FROZEN /
   RUNTIME_UNVERIFIED 等受控词不受影响；
4. 文档包含关键仓库事实字符串（HEAD SHA、基线 SHA、0.1.0-d14a、
   PENDING_P0_I3_RESELECTION、RUNTIME_EVIDENCE_STALE、NOT_FROZEN、
   HANDOFF_REQUIRED、formal_baseline_complete=false 等）；
5. 交付物身份明确为发布包内 `kylin_embedding*.so`（runtime/bridge/），
   wheel / Kaiming 明确排除且未新增构建体系；
6. 刷新规则（git rev-parse HEAD / git status --porcelain /
   git diff --name-only 三分类）与版本一致性程序（EXPECT_SOURCE_COMMIT /
   EXPECT_PACKAGE_VERSION / manifest.source_commit）写入文档。
"""

import re
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_DOC_FILE = _DOC_DIR / "00_d15a_rc_lock_matrix_20260906.md"

# 仓库事实（Task 已批准并核实的 as-of 2026-09-06 快照）。
_HEAD_SHA = "3138e942770ec1f9863e86c03da4df9dd1ad8703"
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
    _HEAD_SHA,
    _BASELINE_SHA,
    _VERSION,
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
]

# 刷新规则与版本一致性程序关键字。
_REFRESH_RULES = [
    "git rev-parse HEAD",
    "git status --porcelain",
    "git diff --name-only",
    f"{_BASELINE_SHA}..HEAD",
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


# ---------- 2. A15 表格状态行均绑定 WAITING_PREREQ ----------

def test_a15_rows_waiting_prereq():
    text = _doc_text()
    for lock in ("A15-1", "A15-2", "A15-3"):
        # M-1 修复：A15-x 状态行与 WAITING_PREREQ 的行级绑定断言。
        # 用多行正则定位 A15-x 的表格状态行（形如 | A15-x | ... | 的整行，
        # re.MULTILINE），要求每个锁点至少命中一行，且命中行文本内必须
        # 包含 WAITING_PREREQ；不再以与行无关的全文存在性检查充当绑定断言。
        pattern = re.compile(
            rf"^\|\s*{re.escape(lock)}\s*\|.*\|\s*$", re.MULTILINE
        )
        rows = pattern.findall(text)
        assert rows, f"锁点 {lock} 未定位到表格状态行（应形如 | {lock} | ... |）"
        assert any("WAITING_PREREQ" in row for row in rows), (
            f"锁点 {lock} 状态行未绑定 WAITING_PREREQ；实际定位行: {rows!r}"
        )
        # 既有断言保留（不删除、不弱化）：全局存在检查被行级绑定严格蕴含，
        # 显式保留以满足既有断言不变量。
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
