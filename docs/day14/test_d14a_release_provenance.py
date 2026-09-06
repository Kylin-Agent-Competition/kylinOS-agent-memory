"""D14A 发布契约与 provenance 溯源文档确定性静态事实测试（v4）。

性质：源码级确定性静态事实测试（纯 stdlib，无网络、无真实 VM、无跨分支文件、
无 stash/pyc 依赖、无 conditional/unconditional skip、不读取不修改历史 evidence）。

方式：基于本文件（__file__）定位仓库根（docs/day14/..）：

- `current_pr_head` **不再**硬编码任何固定 SHA 字面量，执行时以
  `git rev-parse HEAD` 为唯一真源（命令失败即测试错误，不静默、不伪造）；
- 以历史 `tested_runtime_commit` 为证据身份，执行
  `git diff --name-only tested_runtime_commit..HEAD` 做三分类：
  `EVIDENCE_CURRENT`（diff 空）/ `DOCS_EVIDENCE_ONLY`（无 packaging/runtime
  前缀）/ `RUNTIME_EVIDENCE_STALE`（含 packaging/、memory-service/、
  cpp-bridge/、migrations/、config/ 任一前缀）。

测试失败即代表文档与既定事实不一致（CODE_FAILURE / 文档未对齐），禁止放宽断言、
吞异常或跳过。

覆盖事实（与已批准 plan 对应）：
1. 四身份字段齐全且互不相同：source_commit / tested_runtime_commit /
   evidence_commit 为历史字面量，current_pr_head 为 git rev-parse HEAD 执行时
   动态事实（动态 HEAD 不得与三个静态 SHA 伪造相等）；
2. current_pr_head 动态事实绑定：文档 current_pr_head 标签绑定窗口内必须含
   `git rev-parse HEAD` 命令文本且不得出现任何 40 位十六进制字面量（防回退
   硬编码；该规则永久成立、不随 commit 过期）；
3. 文档明确"不得互相伪造相等 / 不得把 tested_runtime_commit 写成当前 PR head"；
4. 三分类规则必须写入文档（EVIDENCE_CURRENT / DOCS_EVIDENCE_ONLY /
   RUNTIME_EVIDENCE_STALE）；任何 packaging/runtime 行为变更必须
   "重新打包 → 重算 hash → 重跑真实 VM"；文档不得再含旧固定 diff 范围
   （e3d4b9d..15de7c6）与"无 D14A packaging/runtime 行为文件变化"陈旧结论；
5. live 门禁：以 tested_runtime_commit..HEAD 真实 diff 为事实，分类器输出与
   直接前缀扫描一致，并把分类与命中前缀打印到测试日志；接受真实
   RUNTIME_EVIDENCE_STALE 为已声明中间态（PASS），但错误分类、越级声明、
   伪造相等/伪造身份、缺失重打包/VM 规则等负向断言仍 fail-closed；
6. 安装架构：整包复制 install_prefix + ~/.local/bin launcher symlink + unit
   ExecStart 安装前缀 launcher；
7. verify 架构：SDK 经独立 embedding server PID 实际加载校验
   （/proc/<embedding_pid>/maps 生效路径+hash），非 gateway 单 PID 自加载；
8. Contract 保持 FROZEN_DRAFT，D Reviewer 会签前不得升 FROZEN；
9. Report 保持 PACKAGE_IMPLEMENTATION_CANDIDATE；两文档全文不出现 HOST_VERIFIED、
   L3 PASS 字面量与状态越级声明；
10. BLOCKER C fail-closed：DEPENDENCY_BLOCKED / HANDOFF_REQUIRED，且文档声明
    不得伪造 runtime/model version、hash、vendor lock、D Reviewer 会签或麒麟
    evidence。
"""

import re
import subprocess
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DOC_DIR.parent.parent
_DOC00 = _DOC_DIR / "00_d14a_release_package_contract.md"
_DOC01 = _DOC_DIR / "01_d14a_implementation_report_20260905.md"

# 历史事实字面量（保持不变；current_pr_head 为执行时动态事实，不在此落库）。
_SOURCE_COMMIT = "5424d28e1178d3d16764ad7c050b878bc8981583"
_TESTED_RUNTIME_COMMIT = "e3d4b9d565e2c3c153973125b3c071225e1b9e4d"
_EVIDENCE_COMMIT = "68bb8f764e204818759fceae0616cac0048753a2"
_STATIC_IDENTITIES = {
    "source_commit": _SOURCE_COMMIT,
    "tested_runtime_commit": _TESTED_RUNTIME_COMMIT,
    "evidence_commit": _EVIDENCE_COMMIT,
}

# packaging/runtime 行为路径前缀（命中任一即 RUNTIME_EVIDENCE_STALE）。
_RUNTIME_PREFIXES = (
    "packaging/",
    "memory-service/",
    "cpp-bridge/",
    "migrations/",
    "config/",
)

# 旧实现遗留的固定 current_pr_head 字面量与旧固定 diff 范围（禁止回退出现）。
_LEGACY_CURRENT_PR_HEAD = "15de7c67426909c7c872f9cb3f9a04a2575753fd"

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


def _head_sha() -> str:
    """执行时取得 current PR head（git rev-parse HEAD）；失败即测试错误。

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


def _four_identities() -> dict:
    """组成四身份字典：三静态历史字面量 + 动态执行时 HEAD。"""
    return {**_STATIC_IDENTITIES, "current_pr_head": _head_sha()}


def _diff_name_only() -> list:
    """git diff --name-only <tested_runtime_commit>..HEAD 的真实变更路径列表。"""
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{_TESTED_RUNTIME_COMMIT}..HEAD"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"git diff --name-only 失败 (rc={proc.returncode}): {proc.stderr.strip()}"
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def classify_changed_paths(changed) -> tuple:
    """对 git diff --name-only 输出做三分类。

    语义（本任务权威定义）：
    - diff 空        -> ("EVIDENCE_CURRENT", [])
    - 含 runtime 前缀 -> ("RUNTIME_EVIDENCE_STALE", hits)
    - 其余            -> ("DOCS_EVIDENCE_ONLY", [])
    """
    if not changed:
        return "EVIDENCE_CURRENT", []
    hits = [p for p in changed if p.startswith(_RUNTIME_PREFIXES)]
    if hits:
        return "RUNTIME_EVIDENCE_STALE", hits
    return "DOCS_EVIDENCE_ONLY", []


def _current_pr_head_window(text: str, where: str) -> str:
    """定位 current_pr_head 标签绑定窗口：标签处向后 200 字符。

    不从标签前延伸（避免吸入前一行 evidence_commit 等静态 SHA 字面量，
    破坏"窗口内不得出现 40 位十六进制字面量"的反回退断言）。
    """
    idx = text.find("current_pr_head")
    assert idx != -1, f"{where} 缺少标签 current_pr_head"
    return text[idx : idx + 200]


# ---------- 1. 四身份字段齐全且互不相同 ----------

def test_four_identities_distinct():
    """四身份去重后必须为 4（禁止互相伪造相等）；动态 HEAD 不得等于静态身份。"""
    identities = _four_identities()
    assert len(set(identities.values())) == 4, (
        f"四身份去重后必须为 4（禁止互相伪造相等）: {identities}"
    )
    for label, sha in identities.items():
        assert _SHA40.fullmatch(sha), f"{label} 不是 40 位 SHA: {sha}"
    head = identities["current_pr_head"]
    assert head not in _STATIC_IDENTITIES.values(), (
        f"动态 HEAD {head[:12]}… 与静态身份伪造相等（fail-closed）"
    )


def _assert_bound(text: str, label: str, sha: str, where: str):
    """断言 label 与其 SHA 在文档中绑定：SHA 首次出现处前 120 字符窗口内含 label。"""
    assert label in text, f"{where} 缺少标签 {label}"
    assert sha in text, f"{where} 缺少 {label} 的 SHA"
    idx = text.find(sha)
    window_start = max(0, idx - 120)
    bound_window = text[window_start : idx + len(sha) + 30]
    assert label in bound_window, f"{where} 中 {label} 未与 {sha[:12]}… 绑定"


def _assert_dynamic_head_bound(text: str, where: str):
    """current_pr_head 动态绑定断言：标签绑定窗口内含 git rev-parse HEAD 动态
    事实表达，且不得出现任何 40 位十六进制字面量（防回退硬编码）。"""
    window = _current_pr_head_window(text, where)
    assert "git rev-parse HEAD" in window, (
        f"{where} 中 current_pr_head 未与 'git rev-parse HEAD' 动态事实表达绑定"
    )
    assert not _SHA40.search(window), (
        f"{where} 中 current_pr_head 绑定窗口内出现 40 位十六进制字面量"
        f"（回退硬编码）: {_SHA40.search(window).group()}"
    )


def test_four_identities_present_in_contract():
    """契约文档必须同时出现四个身份标签；三个静态身份绑定字面量，
    current_pr_head 走动态绑定断言。"""
    text = _docs()["contract"]
    for label, sha in _STATIC_IDENTITIES.items():
        _assert_bound(text, label, sha, "contract")
    _assert_dynamic_head_bound(text, "contract")


def test_four_identities_present_in_report():
    """报告文档必须同时出现四个身份标签；三个静态身份绑定字面量，
    current_pr_head 走动态绑定断言。"""
    text = _docs()["report"]
    for label, sha in _STATIC_IDENTITIES.items():
        _assert_bound(text, label, sha, "report")
    _assert_dynamic_head_bound(text, "report")


# ---------- 2. current_pr_head 动态事实（防回退硬编码） ----------

def test_current_pr_head_dynamic_fact():
    """两文档 current_pr_head 标签绑定窗口内必须含 git rev-parse HEAD 命令文本
    且不得出现任何 40 位十六进制字面量；旧固定 SHA 字面量全文禁止复现。"""
    for name, text in _docs().items():
        _assert_dynamic_head_bound(text, name)
        assert _LEGACY_CURRENT_PR_HEAD not in text, (
            f"{name} 仍含旧固定 current_pr_head SHA 字面量 {_LEGACY_CURRENT_PR_HEAD[:12]}…"
        )


# ---------- 3. 禁止互相伪造相等 / 不得把 tested_runtime_commit 写成当前 PR head ----------

def test_no_forged_equality_semantics():
    for name, text in _docs().items():
        _assert_all(
            text,
            ["不得互相伪造相等", "不得把", "tested_runtime_commit", "写成当前 PR head"],
            name,
        )


# ---------- 4. 重打包规则 ----------

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


# ---------- 5. 三分类规则与旧结论禁止 ----------

def test_three_classification_rule_in_contract():
    _assert_all(
        _docs()["contract"],
        ["git diff --name-only", "tested_runtime_commit..HEAD",
         "EVIDENCE_CURRENT", "DOCS_EVIDENCE_ONLY", "RUNTIME_EVIDENCE_STALE"],
        "contract",
    )


def test_three_classification_rule_in_report():
    _assert_all(
        _docs()["report"],
        ["git diff --name-only", "tested_runtime_commit..HEAD",
         "EVIDENCE_CURRENT", "DOCS_EVIDENCE_ONLY", "RUNTIME_EVIDENCE_STALE"],
        "report",
    )


def test_no_stale_conclusion_literals():
    """两文档不得再含旧固定 diff 范围与『无 D14A packaging/runtime 行为文件
    变化』陈旧结论（随动态 HEAD 语义永久成立，不会过期）。"""
    for name, text in _docs().items():
        assert "无 D14A packaging/runtime 行为文件变化" not in text, (
            f"{name} 仍含旧结论『无 D14A packaging/runtime 行为文件变化』"
        )
        assert "15de7c67426909c7c872f9cb3f9a04a2575753fd" not in text, (
            f"{name} 仍含旧固定 current_pr_head SHA 字面量"
        )


# ---------- 6. 安装架构 ----------

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


# ---------- 7. verify 架构（独立 embedding server PID 实际加载校验） ----------

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


# ---------- 8. Contract 状态：FROZEN_DRAFT，会签前不得升 FROZEN ----------

def test_contract_status_frozen_draft():
    _assert_all(
        _docs()["contract"],
        ["FROZEN_DRAFT", "会签前不得升 FROZEN"],
        "contract",
    )


# ---------- 9. Report 状态与全文禁止越级字面量 ----------

def test_report_status_candidate():
    text = _docs()["report"]
    assert "PACKAGE_IMPLEMENTATION_CANDIDATE" in text


def test_forbidden_escalation_literals_absent():
    """两文档全文不得出现 HOST_VERIFIED / L3 PASS 字面量（允许一般性 L3 提及）。"""
    for name, text in _docs().items():
        assert "HOST_VERIFIED" not in text, f"{name} 出现 HOST_VERIFIED"
        assert "L3 PASS" not in text, f"{name} 出现 L3 PASS"


# ---------- 10. BLOCKER C fail-closed ----------

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


# ---------- 11. 分类器确定性负向单测（错误分类必红） ----------

def test_classifier_negative_cases():
    """分类器负向样例：空 diff、docs-only、evidence-only、各 runtime 前缀、
    docs+packaging 混合，错误分类/错误 hits 必红。"""
    cases = [
        ([], "EVIDENCE_CURRENT", []),
        (["docs/day14/00_d14a_release_package_contract.md"], "DOCS_EVIDENCE_ONLY", []),
        (["evidence/l3-kylin-vm/d14a_20260905/summary.json"], "DOCS_EVIDENCE_ONLY", []),
        (["packaging/release/build_release_package.sh"],
         "RUNTIME_EVIDENCE_STALE", ["packaging/release/build_release_package.sh"]),
        (["memory-service/app.py"], "RUNTIME_EVIDENCE_STALE", ["memory-service/app.py"]),
        (["migrations/versions/20260906_add_forget_topic_key.py"],
         "RUNTIME_EVIDENCE_STALE", ["migrations/versions/20260906_add_forget_topic_key.py"]),
        (["config/config.toml"], "RUNTIME_EVIDENCE_STALE", ["config/config.toml"]),
        (["cpp-bridge/src/bridge.cpp"], "RUNTIME_EVIDENCE_STALE", ["cpp-bridge/src/bridge.cpp"]),
        (["docs/day14/00_d14a_release_package_contract.md",
          "packaging/release/systemd_install.sh"],
         "RUNTIME_EVIDENCE_STALE", ["packaging/release/systemd_install.sh"]),
    ]
    for changed, expected_cls, expected_hits in cases:
        cls, hits = classify_changed_paths(changed)
        assert cls == expected_cls, f"{changed} -> 分类 {cls}，期望 {expected_cls}"
        assert hits == expected_hits, f"{changed} -> 命中 {hits}，期望 {expected_hits}"


# ---------- 12. live 门禁：真实 diff 三分类 + 文档一致性（接受真实 STALE 为 PASS） ----------

def _assert_documentation_consistency(cls: str):
    """按 live 判定的分类对两文档做一致性断言（fail-closed 负向断言全部生效）：

    - 任意分类下：重打包/重算 hash/重跑真实 VM 规则必须存在；report 必须为
      PACKAGE_IMPLEMENTATION_CANDIDATE；contract 必须含 FROZEN_DRAFT + BLOCKER C
      + DEPENDENCY_BLOCKED + HANDOFF_REQUIRED；两文档不得含 HOST_VERIFIED /
      L3 PASS / 旧『无 D14A packaging/runtime 行为文件变化』结论。
    - 接受真实 RUNTIME_EVIDENCE_STALE 为已声明中间态（PASS），不因"确实 stale"
      红门禁；错误分类、越级声明、伪造相等/伪造身份、缺失重打包/VM 规则仍失败。
    """
    texts = _docs()
    for name, text in texts.items():
        _assert_all(text, ["重新打包", "重算 hash", "重跑真实 VM"], name)
        assert "HOST_VERIFIED" not in text, f"{name} 出现 HOST_VERIFIED"
        assert "L3 PASS" not in text, f"{name} 出现 L3 PASS"
        assert "无 D14A packaging/runtime 行为文件变化" not in text, (
            f"{name} 仍含旧结论『无 D14A packaging/runtime 行为文件变化』"
        )
    assert "PACKAGE_IMPLEMENTATION_CANDIDATE" in texts["report"], (
        "report 必须保持 PACKAGE_IMPLEMENTATION_CANDIDATE（不得越级 READY）"
    )
    _assert_all(
        texts["contract"],
        ["FROZEN_DRAFT", "BLOCKER C", "DEPENDENCY_BLOCKED", "HANDOFF_REQUIRED"],
        "contract",
    )
    _assert_all(
        texts["report"],
        ["BLOCKER C", "DEPENDENCY_BLOCKED", "HANDOFF_REQUIRED"],
        "report",
    )
    # 分类具体语义（供日志记录；不额外断言——分类本身由 live 事实决定）。
    print(f"[live] 文档一致性校验通过，classification={cls}")


def test_live_diff_fail_closed():
    """live 门禁：以 tested_runtime_commit..HEAD 真实 git diff 为事实，断言
    分类器输出与直接前缀扫描一致，并把真实分类与命中前缀打印到测试日志。

    当前分支真实分类为 RUNTIME_EVIDENCE_STALE（本批次 Task1/2b/2/3 已引入
    packaging/memory-service/migrations 等变更；正式重打包→hash→真实 VM 刷新
    明确超出本 Task 且尚未执行）时，测试记录并接受该分类为 PASS——
    不因"当前确实 stale"红门禁；负向断言仍 fail-closed。
    """
    head = _head_sha()
    changed = _diff_name_only()
    cls, hits = classify_changed_paths(changed)

    # 独立事实复核：直接前缀扫描，保证分类器与 git diff 事实一致。
    direct_hits = [p for p in changed if p.startswith(_RUNTIME_PREFIXES)]
    if not changed:
        direct_cls = "EVIDENCE_CURRENT"
    elif direct_hits:
        direct_cls = "RUNTIME_EVIDENCE_STALE"
    else:
        direct_cls = "DOCS_EVIDENCE_ONLY"
    assert cls == direct_cls, (
        f"分类器({cls})与直接前缀扫描({direct_cls})不一致（错误分类 fail-closed）"
    )
    assert hits == direct_hits, f"分类器命中({hits})与直接扫描({direct_hits})不一致"

    # 记录执行时事实到测试日志。
    print(f"[live] HEAD={head}")
    print(f"[live] tested_runtime_commit={_TESTED_RUNTIME_COMMIT}")
    print(f"[live] changed_files={len(changed)}")
    print(f"[live] classification={cls}")
    print(f"[live] runtime_prefix_hits={hits}")

    # 文档一致性（负向 fail-closed 断言恒生效；真实 STALE 作为已声明中间态 PASS）。
    _assert_documentation_consistency(cls)


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