"""D14A 发布契约与 provenance 溯源文档确定性静态事实测试（v5 + D15D v2）。

性质：源码级确定性静态事实测试（纯 stdlib，无网络、无真实 VM、无跨分支文件、
无 stash/pyc 依赖、无 conditional/unconditional skip、不读取不修改历史 evidence）。

方式：基于本文件（__file__）定位仓库根（docs/day14/..）：

- 当前 contract/package identity 继续绑定 D14D formal evidence `ba3b50e`，
  并标记 historical scope；D14A v4 identity 只允许作为 historical/superseded 记录；
- D15D current release identity 绑定 `4a6323f`，由 D15D manifest v2 承载，
  不改写 Reviewer E 已专项裁定的 D14D contract historical identity；
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
1. 当前三身份与动态 head 齐全：source_commit == tested_runtime_commit（D14D
   formal evidence 的真实事实），evidence_commit 为 D14D evidence root 入库 commit，
   current_pr_head 为 git rev-parse HEAD 执行时动态事实（动态 HEAD 不得与静态
   SHA 伪造相等）；
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
8. Contract v5 historical 身份与 D14D evidence 一致；D15D manifest v2 当前
   release identity 与 package evidence 一致，且新旧身份不混写；
9. Report 保持 PACKAGE_IMPLEMENTATION_CANDIDATE；两文档全文不出现 HOST_VERIFIED、
   L3 PASS 字面量与状态越级声明；
10. BLOCKER C fail-closed：§6bis G0 identity value-matched；既有 PR author
     授权评论仅保留为 invalid historical record，专项 authority 由 Reviewer E
     identity adjudication 闭合；最终 D15D 签署仍分离待办；文档声明不得伪造
     runtime/model
     version、hash、vendor lock、reviewer 会签或麒麟 evidence。
"""

import json
import re
import subprocess
from pathlib import Path

_DOC_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DOC_DIR.parent.parent
_DOC00 = _DOC_DIR / "00_d14a_release_package_contract.md"
_DOC01 = _DOC_DIR / "01_d14a_implementation_report_20260905.md"

# D14D formal identity（current_pr_head 为执行时动态事实，不在此落库）。
_SOURCE_COMMIT = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"
_TESTED_RUNTIME_COMMIT = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"
_EVIDENCE_COMMIT = "ec7a66b3e52f8d76b156300d375467290fdc42b6"
_FROZEN_TAR_SHA256 = "2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401"
_FROZEN_MANIFEST_SHA256 = "76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0"
_FROZEN_SHA256SUMS_SHA256 = "8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67"
_STATIC_IDENTITIES = {
    "source_commit": _SOURCE_COMMIT,
    "tested_runtime_commit": _TESTED_RUNTIME_COMMIT,
    "evidence_commit": _EVIDENCE_COMMIT,
}

# D15D 当前 release identity：由 D15D manifest v2 承载，不替换 D14D contract。
_CURRENT_RELEASE_COMMIT = "4a6323fb3a8c73e0b15f1f3629d28dfc12071541"
_NEW_TAR_SHA256 = "974c2584a08bc2ae5277a8526ce3c5dbd711bc0d54c9844e99d658892cca9f28"
_NEW_MANIFEST_SHA256 = "4b42d9281e1fac269bc0e0ba43d831317424fc6200a751380ebf985241124ec4"
_NEW_SHA256SUMS_SHA256 = "9d1ac01fab8a2a876b97ffc5ffd375085661c78029b03a35c6984b7c91f4d9f4"
_NEW_EVIDENCE_ROOT = "evidence/d15d-lock/20260910T205300Z"

# D14A v4 历史身份：仅允许保留为 historical/superseded，不参与当前 live 门禁。
_HISTORICAL_IDENTITIES = {
    "source_commit": "5424d28e1178d3d16764ad7c050b878bc8981583",
    "tested_runtime_commit": "e3d4b9d565e2c3c153973125b3c071225e1b9e4d",
    "evidence_commit": "68bb8f764e204818759fceae0616cac0048753a2",
}

_D15D_MANIFEST = _REPO_ROOT / "docs/day15/D15D_VERSION_MANIFEST.json"
_TASK_CARD = _REPO_ROOT / "docs/D15D_TaskCard_20260906.md"
_ROUND4_C2_EVIDENCE = (
    _REPO_ROOT / "evidence/d15d-lock/"
    "20260910T105245Z/c2_main_drift_invalidation.md"
)
_RUNBOOK = _REPO_ROOT / "docs/D15D_PostLock_Consistency_Runbook_20260906.md"
_ROUND2_REWORK = (
    _REPO_ROOT / "evidence/d15d-lock/20260910T090314Z/round2_rework.md"
)
_D14D_SUMMARY = (
    _REPO_ROOT / "evidence/l3-kylin-vm/"
    "d14d_20260907T141000Z_ba3b50e/summary.json"
)
_D14D_BUILD_IDENTITY = (
    _REPO_ROOT / "evidence/l3-kylin-vm/"
    "d14d_20260907T141000Z_ba3b50e/package_build_identity.json"
)

# packaging/runtime 行为路径前缀（命中任一即 RUNTIME_EVIDENCE_STALE）。
_RUNTIME_PREFIXES = (
    "packaging/",
    "memory-service/",
    "cpp-bridge/",
    "migrations/",
    "config/",
)

_CURRENT_MAIN_SHA = "4a6323fb3a8c73e0b15f1f3629d28dfc12071541"

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


def _load_json(path: Path) -> dict:
    """读取正式机器可读事实；缺失/损坏即失败，不静默降级。"""
    assert path.is_file(), f"缺失 JSON: {path}"
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    assert isinstance(value, dict), f"JSON 顶层必须是 object: {path}"
    return value


def _identity_ssot() -> dict:
    """分别收敛 historical D14D identity 与 D15D current release identity。"""
    manifest = _load_json(_D15D_MANIFEST)
    summary = _load_json(_D14D_SUMMARY)
    build = _load_json(_D14D_BUILD_IDENTITY)
    contract = manifest["contract"]
    return {
        "current_release_commit": manifest["release_commit"],
        "current_main_sha": manifest["current_main"]["sha"],
        "current_main_release_commit_is_current_main":
            manifest["current_main"]["release_commit_is_current_main"],
        "current_main_drift": manifest["current_main"]["runtime_sensitive_drift_since_release_commit"],
        "new_package_tar_sha256": manifest["package"]["tar_sha256"],
        "new_package_manifest_sha256": manifest["package"]["manifest_sha256"],
        "new_package_sha256sums_sha256": manifest["package"]["sha256sums_sha256"],
        "new_evidence_root": manifest["new_release_evidence"]["root"],
        "d14d_evidence_commit": manifest["d14d_evidence"]["evidence_commit"],
        "d14d_package_tar_sha256": manifest["d14d_evidence"]["package_tar_sha256"],
        "d14d_package_manifest_sha256": manifest["d14d_evidence"]["package_manifest_sha256"],
        "d14d_package_sha256sums_sha256": manifest["d14d_evidence"]["package_sha256sums_sha256"],
        "release_commit": manifest["release_commit"],
        "manifest_source_commit": build["source_commit"],
        "manifest_tested_commit": summary["tested_commit"],
        "contract_source_commit": contract["package_identity"]["source_commit"],
        "contract_tested_runtime_commit": contract["package_identity"]["tested_runtime_commit"],
        "contract_evidence_commit": contract["package_identity"]["evidence_commit"],
        "manifest_evidence_commit": manifest["d14d_evidence"]["evidence_commit"],
        "package_tar_sha256": summary["package_tar_sha256"],
        "build_package_tar_sha256": build["package_tar_sha256"],
        "manifest_package_tar_sha256": manifest["package"]["tar_sha256"],
        "manifest_sha256": build["manifest_sha256"],
        "manifest_manifest_sha256": manifest["package"]["manifest_sha256"],
        "sha256sums_sha256": build["sha256sums_sha256"],
        "manifest_sha256sums_sha256": manifest["package"]["sha256sums_sha256"],
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


# ---------- 1. 当前身份与 D14A historical/superseded 身份 ----------

def test_current_identities_valid():
    """当前身份齐全；D14D source/tested 相等是真实事实，head 不得混写。"""
    identities = _four_identities()
    for label, sha in identities.items():
        assert _SHA40.fullmatch(sha), f"{label} 不是 40 位 SHA: {sha}"
    assert identities["source_commit"] == identities["tested_runtime_commit"], (
        "D14D formal evidence 的 source/tested commit 必须一致"
    )
    assert identities["evidence_commit"] != identities["source_commit"], (
        "evidence_commit 不得与被测 commit 伪造相等"
    )
    head = identities["current_pr_head"]
    assert head not in _STATIC_IDENTITIES.values(), (
        f"动态 HEAD {head[:12]}… 与静态身份伪造相等（fail-closed）"
    )
    assert head not in _HISTORICAL_IDENTITIES.values(), (
        f"动态 HEAD {head[:12]}… 不得与 historical/superseded 身份伪造相等"
    )


def _assert_bound(text: str, label: str, sha: str, where: str):
    """断言 label 与其 SHA 在某个出现处绑定（兼容 source/tested 同 commit）。"""
    assert label in text, f"{where} 缺少标签 {label}"
    assert sha in text, f"{where} 缺少 {label} 的 SHA"
    start = 0
    while True:
        idx = text.find(sha, start)
        if idx == -1:
            break
        window_start = max(0, idx - 120)
        bound_window = text[window_start : idx + len(sha) + 30]
        if label in bound_window:
            return
        start = idx + 1
    raise AssertionError(f"{where} 中 {label} 未与 {sha[:12]}… 绑定")


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
    text = _docs()["contract"]
    for label, sha in _STATIC_IDENTITIES.items():
        _assert_bound(text, label, sha, "contract")
    _assert_dynamic_head_bound(text, "contract")
    assert "Historical / superseded D14A v4 identity" in text
    assert "historical / superseded" in text
    for label, sha in _HISTORICAL_IDENTITIES.items():
        assert sha in text, f"historical contract 缺少 {label}: {sha[:12]}…"


def test_four_identities_present_in_report():
    text = _docs()["report"]
    for label, sha in _HISTORICAL_IDENTITIES.items():
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


# ---------- 8. Contract 状态：Reviewer E adjudication approved / final sign pending ----------

def test_contract_status_proposed_v5_pending_final_sign():
    _assert_all(
        _docs()["contract"],
        ["PROPOSED v5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / "
         "PENDING_FINAL_D15D_SIGN",
         "溯源收口 v5", "pull/175#issuecomment-5615523980",
         "PR author `Ducknesses`", "invalid historical authority record",
         "ReviewerE identity adjudication", "PENDING_FINAL_D15D_SIGN"],
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

def test_blocker_c_identity_frozen_contract():
    _assert_all(
        _docs()["contract"],
        [
            "BLOCKER C",
            "PR author `Ducknesses`",
            "ReviewerE identity adjudication",
            "PENDING_FINAL_D15D_SIGN",
            "d14d_20260907T141000Z_ba3b50e/dependency_identity.json",
            "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48",
            "b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225",
            "cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1",
            "release_ready=false",
            "production_ready=false",
            "fail-closed",
            "不得伪造 runtime/model version、hash、vendor lock、reviewer 会签或麒麟 evidence",
        ],
        "contract",
    )


def test_blocker_c_fail_closed_report():
    _assert_all(
        _docs()["report"],
        [
            "BLOCKER C",
            "HANDOFF_REQUIRED",
            "fail-closed",
            "不得伪造 runtime/model version、hash、vendor lock、reviewer 会签或麒麟 evidence",
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


# ---------- 12. contract ↔ D15D manifest ↔ D14D evidence 三方一致 ----------

def test_contract_manifest_d14d_three_way_identity():
    """contract 与 D14D evidence 保持 historical identity 一致；
    D15D manifest 承载 current release identity，且新旧身份不得混写。"""
    values = _identity_ssot()
    historical_commit = _SOURCE_COMMIT
    evidence_commit = _EVIDENCE_COMMIT
    assert values["current_release_commit"] == _CURRENT_RELEASE_COMMIT
    assert values["current_main_sha"] == _CURRENT_RELEASE_COMMIT
    assert values["current_main_release_commit_is_current_main"] is True
    assert values["current_main_drift"] is False
    assert values["new_package_tar_sha256"] == _NEW_TAR_SHA256
    assert values["new_package_manifest_sha256"] == _NEW_MANIFEST_SHA256
    assert values["new_package_sha256sums_sha256"] == _NEW_SHA256SUMS_SHA256
    assert values["new_evidence_root"] == _NEW_EVIDENCE_ROOT

    assert values["manifest_source_commit"] == historical_commit
    assert values["manifest_tested_commit"] == historical_commit
    assert values["contract_source_commit"] == historical_commit
    assert values["contract_tested_runtime_commit"] == historical_commit
    assert values["contract_evidence_commit"] == evidence_commit
    assert values["package_tar_sha256"] == _FROZEN_TAR_SHA256
    assert values["build_package_tar_sha256"] == _FROZEN_TAR_SHA256
    assert values["manifest_sha256"] == _FROZEN_MANIFEST_SHA256
    assert values["sha256sums_sha256"] == _FROZEN_SHA256SUMS_SHA256
    assert values["d14d_evidence_commit"] == evidence_commit
    assert values["d14d_package_tar_sha256"] == _FROZEN_TAR_SHA256
    assert values["d14d_package_manifest_sha256"] == _FROZEN_MANIFEST_SHA256
    assert values["d14d_package_sha256sums_sha256"] == _FROZEN_SHA256SUMS_SHA256

    governance = _load_json(_D15D_MANIFEST)["contract"]
    assert governance["status"] == (
        "PROPOSED_V5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / "
        "PENDING_FINAL_D15D_SIGN"
    )
    assert governance["final_d15d_sign"] == "PENDING"
    assert governance["authorization"]["authority_valid"] is False
    assert governance["authorization"]["record_disposition"] == (
        "HISTORICAL_INVALID_NOT_AN_ACTIVE_BLOCKER"
    )
    assert governance["identity_adjudication"]["status"] == "APPROVED"
    assert governance["identity_adjudication"]["authority_comment_id"] == 5616426125

    contract = _docs()["contract"]
    for value in (
        historical_commit,
        evidence_commit,
        _FROZEN_TAR_SHA256,
        _FROZEN_MANIFEST_SHA256,
        _FROZEN_SHA256SUMS_SHA256,
        "docs/day15/D15D_VERSION_MANIFEST.json",
    ):
        assert value in contract, f"contract 缺少当前三方身份值: {value}"
    assert governance["package_identity"].get("historical_scope_only") is True


# ---------- 13. live 门禁：current release 无 runtime drift + 文档一致性 ----------

def _assert_documentation_consistency(cls: str):
    """按 live 判定的分类对两文档做一致性断言（fail-closed 负向断言全部生效）：

    - 任意分类下：重打包/重算 hash/重跑真实 VM 规则必须存在；report 必须为
      PACKAGE_IMPLEMENTATION_CANDIDATE；contract 必须含 PROPOSED v5 + BLOCKER C
      + 当前 D14D G0 身份闭合；两文档不得含 HOST_VERIFIED /
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
        ["PROPOSED v5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / "
         "PENDING_FINAL_D15D_SIGN", "BLOCKER C",
         "溯源收口 v5", "release_ready=false", "production_ready=false"],
        "contract",
    )
    _assert_all(
        texts["report"],
        ["BLOCKER C", "HANDOFF_REQUIRED"],
        "report",
    )
    # 分类具体语义（供日志记录；不额外断言——分类本身由 live 事实决定）。
    print(f"[live] 文档一致性校验通过，classification={cls}")


def _current_main_ref() -> str:
    """选择可用的 current main ref；本地与 CI 的 remote 名不同。"""
    for candidate in ("origin/main", "kylin-mem/main"):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            assert _SHA40.fullmatch(sha), f"{candidate} 输出非法: {sha!r}"
            assert sha == _CURRENT_MAIN_SHA, (
                f"{candidate}={sha} 不是登记的 current main {_CURRENT_MAIN_SHA}"
            )
            return candidate
    raise AssertionError("current main ref 不存在：origin/main 或 kylin-mem/main")


def _release_runtime_drift_hits(main_ref: str) -> list:
    """检查 current release commit 到 current main 的 runtime-sensitive paths。"""
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{_CURRENT_RELEASE_COMMIT}..{main_ref}",
         "--", *_RUNTIME_PREFIXES],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"git diff current release drift 失败 (rc={proc.returncode}): "
        f"{proc.stderr.strip()}"
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def test_live_diff_fail_closed():
    """live 门禁：D15D current release `4a6323f` 到 current main 的 diff 不得
    命中 packaging/runtime 前缀；D14D contract 的 historical 三分类保留，
    但不再替代当前 release 的新鲜性判定。
    """
    head = _head_sha()
    main_ref = _current_main_ref()
    hits = _release_runtime_drift_hits(main_ref)
    assert not hits, (
        f"current release `4a6323f` 到 {main_ref} 出现 runtime drift: {hits}"
    )

    # 记录执行时事实到测试日志。
    print(f"[live] HEAD={head}")
    print(f"[live] current_release_commit={_CURRENT_RELEASE_COMMIT}")
    print(f"[live] current_main_ref={main_ref}")
    print(f"[live] runtime_prefix_hits={hits}")

    # 文档一致性（负向 fail-closed 断言恒生效）。
    _assert_documentation_consistency("CURRENT_RELEASE_NO_RUNTIME_DRIFT")


def test_governance_ssot_after_identity_adjudication():
    """专项 identity authority 已由 E 裁定，旧 ReviewerD 状态不得回潮。"""
    manifest = _load_json(_D15D_MANIFEST)
    governance = manifest["contract"]
    assert governance["status"] == (
        "PROPOSED_V5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / "
        "PENDING_FINAL_D15D_SIGN"
    )
    assert governance["final_d15d_sign"] == "PENDING"

    for path in (_TASK_CARD, _ROUND2_REWORK):
        assert path.is_file(), f"缺失治理 SSOT 文件: {path}"
        text = path.read_text(encoding="utf-8")
        assert "PENDING_INDEPENDENT_D_REVIEW" not in text, (
            f"{path.name} 仍保留旧非作者 ReviewerD active gate 状态"
        )
        assert "non-author ReviewerD record is still pending" not in text, (
            f"{path.name} 仍声明等待非作者 ReviewerD record"
        )
        assert "REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED" in text, (
            f"{path.name} 缺少 Reviewer E identity adjudication approved 状态"
        )
        assert "PENDING_FINAL_D15D_SIGN" in text, (
            f"{path.name} 缺少 final sign pending 状态"
        )


def test_current_main_drift_invalidation_ssot():
    """第 4 轮旧包失效记录必须保留，且当前 main 已由 4a6323f 新链闭合。"""
    manifest = _load_json(_D15D_MANIFEST)
    consistency = manifest["post_lock_consistency"]
    historical = consistency["historical_lock_invalidation"]
    assert manifest["current_main"]["sha"] == _CURRENT_MAIN_SHA
    assert manifest["current_main"]["release_commit_is_current_main"] is True
    assert manifest["current_main"]["runtime_sensitive_drift_since_release_commit"] is False
    assert manifest["release_classification"] == (
        "NEW_RELEASE_IDENTITY_BUILT_AND_VM_VERIFIED"
    )
    assert consistency["gate"] == "C2"
    assert consistency["status"] == "PASS_CURRENT_MAIN_NO_RUNTIME_SENSITIVE_DRIFT"
    assert consistency["current_main_sha"] == _CURRENT_MAIN_SHA
    assert tuple(consistency["locked_runtime_prefix_hits"]) == ()
    assert consistency["frozen_package_lock_valid"] is False
    assert consistency["comparison"] == f"{_CURRENT_MAIN_SHA}..kylin-mem/main"
    assert consistency["rebuild_required"] is True
    assert consistency["rebuild_completed"] is True
    assert consistency["host_vm_required"] is True
    assert consistency["host_vm_completed"] is True

    assert historical["release_commit"] == _SOURCE_COMMIT
    assert historical["status"] == "FAIL_INVALIDATED"
    assert historical["conclusion"] == "TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY"
    assert manifest["new_release_evidence"]["root"] == _NEW_EVIDENCE_ROOT
    assert manifest["new_release_evidence"]["release_commit"] == _CURRENT_MAIN_SHA
    assert manifest["new_release_evidence"]["c1_clean_detached_worktree"]["status"] == "PASS"
    assert manifest["new_release_evidence"]["c3_c6_source_blob_consistency"]["status"] == "PASS"
    assert manifest["new_release_evidence"]["c7_clean_package_smoke"]["status"] == "PASS"
    assert manifest["new_release_evidence"]["c8_package_integrity"]["status"] == "PASS"
    assert manifest["package"]["runtime_app_pyc"] == 0
    assert manifest["package"]["runtime_app_pycache_dirs"] == 0
    assert manifest["c11"]["status"] == (
        "HISTORICAL_PASS_AT_ba3b50e / NOT_SUFFICIENT_FOR_NEW_RELEASE"
    )
    assert manifest["c11"]["old_root_accepted_as_final_for_new_release"] is False
    assert manifest["c11"]["current_release_binding_closed"] is True
    assert consistency["rebuild_required"] is True
    assert consistency["host_vm_required"] is True

    task_card = _TASK_CARD.read_text(encoding="utf-8")
    assert _CURRENT_MAIN_SHA in task_card
    assert "TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY" in task_card
    assert "NEW_RELEASE_IDENTITY_BUILT_AND_VM_VERIFIED" in task_card

    assert _ROUND4_C2_EVIDENCE.is_file(), f"缺失 C2 失效证据: {_ROUND4_C2_EVIDENCE}"
    evidence = _ROUND4_C2_EVIDENCE.read_text(encoding="utf-8")
    assert _CURRENT_MAIN_SHA in evidence
    assert "FAIL_INVALIDATED" in evidence
    assert "TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY" in evidence
    assert "does not claim a new L2/L3 PASS" in evidence

    runbook = _RUNBOOK.read_text(encoding="utf-8")
    c2_line = next(
        line for line in runbook.splitlines() if line.startswith("| C2 |")
    )
    assert "config/" in c2_line, "Runbook C2 scope 必须包含 config/"


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
