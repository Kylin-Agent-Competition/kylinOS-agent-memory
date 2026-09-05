"""D14A 发布契约与 provenance 溯源文档确定性静态事实测试（v3）。

性质：源码级确定性静态事实测试（纯 stdlib，无网络、无真实 VM、无跨分支文件、
无 stash/pyc 依赖、无 conditional/unconditional skip）。

方式：基于本文件（__file__）定位同目录两份 D14A markdown 文档，对既定事实做
字符串/语义断言。测试失败即代表文档与既定事实不一致（CODE_FAILURE / 文档未对齐），
禁止放宽断言、吞异常或跳过。

覆盖事实（与已批准 plan 对应）：
1. 四身份字段齐全且互不相同（source_commit / tested_runtime_commit /
   evidence_commit / current_pr_head，各 40 位 SHA，去重后数量为 4，标签与值绑定）；
2. 文档明确"不得互相伪造相等 / 不得把 tested_runtime_commit 写成当前 PR head"；
3. 后续 packaging/runtime 变更须"重新打包 → 重算 hash → 重跑真实 VM"；
4. git diff 复核结论：e3d4b9d..15de7c6 范围无 D14A packaging/runtime 行为文件变化；
5. 安装架构：整包复制 install_prefix + ~/.local/bin launcher symlink + unit
   ExecStart 安装前缀 launcher；
6. verify 架构：SDK 经独立 embedding server PID 实际加载校验（maps 生效路径+hash），
   非 gateway 单 PID 自加载；
7. Contract 保持 FROZEN_DRAFT，D Reviewer 会签前不得升 FROZEN；
8. Report 保持 PACKAGE_IMPLEMENTATION_CANDIDATE；两文档全文不出现 HOST_VERIFIED、
   L3 PASS 字面量与状态越级声明；
9. BLOCKER C fail-closed：DEPENDENCY_BLOCKED / HANDOFF_REQUIRED，且文档声明不得伪造
   runtime/model version/hash/vendor lock/D Reviewer 会签/麒麟 evidence。
"""

import re
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_DOC00 = _DOC_DIR / "00_d14a_release_package_contract.md"
_DOC01 = _DOC_DIR / "01_d14a_implementation_report_20260905.md"

# 四身份：标签 -> 40 位 SHA（与文档与 plan 接口约束一致）。
_IDENTITIES = {
    "source_commit": "5424d28e1178d3d16764ad7c050b878bc8981583",
    "tested_runtime_commit": "e3d4b9d565e2c3c153973125b3c071225e1b9e4d",
    "evidence_commit": "68bb8f764e204818759fceae0616cac0048753a2",
    "current_pr_head": "15de7c67426909c7c872f9cb3f9a04a2575753fd",
}

# diff 复核范围（tested_runtime_commit..R2 开工基线），40 位 SHA 字面量。
_DIFF_RANGE = (
    "e3d4b9d565e2c3c153973125b3c071225e1b9e4d.."
    "15de7c67426909c7c872f9cb3f9a04a2575753fd"
)

_SHA40 = re.compile(r"\b[0-9a-f]{40}\b")


def _docs() -> dict:
    """读取两份文档原文；文件缺失即失败（确定性事实测试前提）。"""
    assert _DOC00.is_file(), f"缺失文档: {_DOC00}"
    assert _DOC01.is_file(), f"缺失文档: {_DOC01}"
    return {
        "contract": _DOC00.read_text(encoding="utf-8"),
        "report": _DOC01.read_text(encoding="utf-8"),
    }


def _assert_all(text: str, tokens, where: str):
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{where} 缺少既定事实 token: {missing}"


# ---------- 1. 四身份字段齐全且互不相同 ----------

def test_four_identities_distinct():
    """四个身份字段去重后数量必须为 4（禁止互相伪造相等）。"""
    assert len(set(_IDENTITIES.values())) == 4
    for label, sha in _IDENTITIES.items():
        assert _SHA40.fullmatch(sha), f"{label} 不是 40 位 SHA: {sha}"


def _assert_bound(text: str, label: str, sha: str, where: str):
    """断言 label 与其 SHA 在文档中绑定：SHA 首次出现处前 120 字符窗口内含 label。"""
    assert label in text, f"{where} 缺少标签 {label}"
    assert sha in text, f"{where} 缺少 {label} 的 SHA"
    idx = text.find(sha)
    window_start = max(0, idx - 120)
    bound_window = text[window_start : idx + len(sha) + 30]
    assert label in bound_window, f"{where} 中 {label} 未与 {sha[:12]}… 绑定"


def test_four_identities_present_in_contract():
    """契约文档必须同时出现四个身份标签及其值，且标签与值绑定。"""
    text = _docs()["contract"]
    for label, sha in _IDENTITIES.items():
        _assert_bound(text, label, sha, "contract")


def test_four_identities_present_in_report():
    """报告文档必须同时出现四个身份标签及其值，且标签与值绑定。"""
    text = _docs()["report"]
    for label, sha in _IDENTITIES.items():
        _assert_bound(text, label, sha, "report")


# ---------- 2. 禁止互相伪造相等 / 不得把 tested_runtime_commit 写成当前 PR head ----------

def test_no_forged_equality_semantics():
    for name, text in _docs().items():
        _assert_all(
            text,
            ["不得互相伪造相等", "不得把", "tested_runtime_commit", "写成当前 PR head"],
            name,
        )


# ---------- 3. 重打包规则 ----------

def test_repackaging_rule_contract():
    _assert_all(
        _docs()["contract"],
        ["重新打包", "重算 hash", "重跑真实 VM"],
        "contract",
    )


def test_repackaging_rule_report():
    _assert_all(
        _docs()["report"],
        ["重新打包", "重算 hash", "重跑真实 VM"],
        "report",
    )


# ---------- 4. diff 复核事实 ----------

def test_diff_review_fact_contract():
    _assert_all(
        _docs()["contract"],
        ["git diff --name-only", _DIFF_RANGE, "无 D14A packaging/runtime 行为文件变化"],
        "contract",
    )


def test_diff_review_fact_report():
    _assert_all(
        _docs()["report"],
        ["git diff --name-only", _DIFF_RANGE, "无 D14A packaging/runtime 行为文件变化"],
        "report",
    )


# ---------- 5. 安装架构 ----------

def test_install_architecture_contract():
    _assert_all(
        _docs()["contract"],
        [
            "整包复制",
            "install_prefix",
            "symlink",
            "ExecStart=<install_prefix>/bin/kylin-memory-server",
            "安装前缀 launcher",
        ],
        "contract",
    )
    # ~/.local/bin 或 $HOME/.local/bin 至少出现其一（同义路径表达）。
    text = _docs()["contract"]
    assert "~/.local/bin" in text or "$HOME/.local/bin" in text


def test_install_architecture_report():
    _assert_all(
        _docs()["report"],
        [
            "整包复制",
            "install_prefix",
            "symlink",
            "ExecStart=<install_prefix>/bin/kylin-memory-server",
            "安装前缀 launcher",
        ],
        "report",
    )
    text = _docs()["report"]
    assert "~/.local/bin" in text or "$HOME/.local/bin" in text


# ---------- 6. verify 架构（独立 embedding server PID 实际加载校验） ----------

def test_verify_embedding_pid_contract():
    _assert_all(
        _docs()["contract"],
        [
            "独立 embedding server",
            "embedding_pid",
            "/proc/<embedding_pid>/maps",
            "非 gateway 单 PID 自加载",
        ],
        "contract",
    )


def test_verify_embedding_pid_report():
    _assert_all(
        _docs()["report"],
        [
            "独立 embedding server PID",
            "embedding_pid",
            "/proc/<embedding_pid>/maps",
            "非 gateway 单 PID 自加载",
        ],
        "report",
    )


# ---------- 7. Contract 状态：FROZEN_DRAFT，会签前不得升 FROZEN ----------

def test_contract_status_frozen_draft():
    _assert_all(
        _docs()["contract"],
        ["FROZEN_DRAFT", "会签前不得升 FROZEN"],
        "contract",
    )


# ---------- 8. Report 状态与全文禁止越级字面量 ----------

def test_report_status_candidate():
    text = _docs()["report"]
    assert "PACKAGE_IMPLEMENTATION_CANDIDATE" in text


def test_forbidden_escalation_literals_absent():
    """两文档全文不得出现 HOST_VERIFIED / L3 PASS 字面量（允许一般性 L3 提及）。"""
    for name, text in _docs().items():
        assert "HOST_VERIFIED" not in text, f"{name} 出现 HOST_VERIFIED"
        assert "L3 PASS" not in text, f"{name} 出现 L3 PASS"


# ---------- 9. BLOCKER C fail-closed ----------

def test_blocker_c_fail_closed_contract():
    _assert_all(
        _docs()["contract"],
        [
            "BLOCKER C",
            "DEPENDENCY_BLOCKED",
            "HANDOFF_REQUIRED",
            "fail-closed",
            "不得伪造 runtime/model version、hash、vendor lock、D Reviewer 会签或麒麟 evidence",
        ],
        "contract",
    )


def test_blocker_c_fail_closed_report():
    _assert_all(
        _docs()["report"],
        [
            "BLOCKER C",
            "DEPENDENCY_BLOCKED",
            "HANDOFF_REQUIRED",
            "fail-closed",
            "不得伪造 runtime/model version、hash、vendor lock、D Reviewer 会签或麒麟 evidence",
        ],
        "report",
    )


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