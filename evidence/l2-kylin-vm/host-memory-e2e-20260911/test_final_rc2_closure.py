from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "final-rc2"

EXPECTED = {
    "active-context.txt":
        "ebe8195870645ceb0ccce3e36cc591e91ac15f8e4b1a49feb4f3a1b1b6243ceb",
    "assistant-hook-env.txt":
        "6891044745f8b465d53b362140a33439299fe2c531f182cd8e32837930be3481",
    "assistant-identity.txt":
        "0f2230d3b24e3242ec8ef71df0695c6c433335994df53ec54877f82499aa8a13",
    "chat-db-tail.txt":
        "75b65ca3bab502f07955effa9f794025224b6235ff95170a82e5aede2c146cbd",
    "db-leak-check.txt":
        "49d15a52260f36f9bd6ca065e5d391bcf3f904ed85f172d548346f4fdda37ee6",
    "install-final.log":
        "cd12d625702d6db3ed82515621ac134fedd3c7a1db799b42e06151158c0e0171",
    "memory-execstart.txt":
        "bb08e36d68c75b5434f9e13d81726669b650d4d59863f24b1da2736b14c66778",
    "prechat-final-login.txt":
        "c5266eb2ed1a63e1886adf82d5eb050c039ffac577695e14099891d460b71b6e",
    "prechat.log":
        "cca770e70a64891eff133613e69417f8f8b212996336725c954b879b450cfc1c",
    "runtime-verify.txt":
        "0e0225db3fda7cc53af7be2745736715e437e048d39fc4e30fbee138f770f55e",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)

    return h.hexdigest()


def parse_manifest(root: Path) -> dict[str, str]:
    manifest = root / "SHA256SUMS"

    if not manifest.is_file():
        raise AssertionError("SHA256SUMS missing")

    result: dict[str, str] = {}

    for line in manifest.read_text(
        encoding="ascii"
    ).splitlines():
        match = re.fullmatch(
            r"([0-9a-f]{64})  ([^/]+)",
            line,
        )

        if match is None:
            raise AssertionError(
                f"invalid manifest line: {line!r}"
            )

        digest, name = match.groups()

        if name in result:
            raise AssertionError(
                f"duplicate manifest entry: {name}"
            )

        result[name] = digest

    return result


def verify_package(root: Path) -> None:
    manifest = parse_manifest(root)

    # Manifest content itself is part of the sealed baseline:
    # no adopting new hashes during verification.
    assert manifest == EXPECTED

    actual_files = {
        path.name
        for path in root.iterdir()
        if path.is_file()
        and path.name != "SHA256SUMS"
    }

    assert actual_files == set(EXPECTED)

    for name, expected_digest in EXPECTED.items():
        path = root / name

        assert path.is_file(), name
        assert sha256_file(path) == expected_digest, name


def test_final_rc2_package_closure():
    verify_package(PACKAGE)


def test_final_rc2_tamper_is_rejected(tmp_path):
    copy = tmp_path / "final-rc2"
    shutil.copytree(PACKAGE, copy)

    target = copy / "active-context.txt"

    with target.open("ab") as fh:
        fh.write(b"\nTAMPER\n")

    try:
        verify_package(copy)
    except AssertionError:
        pass
    else:
        raise AssertionError(
            "tampered evidence was accepted"
        )


def test_final_rc2_missing_file_is_rejected(tmp_path):
    copy = tmp_path / "final-rc2"
    shutil.copytree(PACKAGE, copy)

    (
        copy / "runtime-verify.txt"
    ).unlink()

    try:
        verify_package(copy)
    except AssertionError:
        pass
    else:
        raise AssertionError(
            "missing evidence file was accepted"
        )
