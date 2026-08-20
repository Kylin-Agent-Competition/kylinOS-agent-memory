"""D4D 配置测试：FRZ-CFG-001 / FR-DB-006（8 键默认值 / env 覆盖 / fail-fast / 文件缺失 WARN）"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config import MemoryConfig, load_config


@pytest.fixture()
def clear_env():
    keys = [
        "KYLIN_MEMORY_SOCKET", "KYLIN_MEMORY_DB", "KYLIN_MEMORY_DEADLINE_MS",
        "KYLIN_MEMORY_RETRIEVE_DEADLINE_MS", "KYLIN_MEMORY_OUTBOX_POLL_INTERVAL_S",
        "KYLIN_MEMORY_OUTBOX_MAX_RETRIES", "KYLIN_MEMORY_EMBEDDING_MODEL",
        "KYLIN_MEMORY_LOG_LEVEL",
    ]
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_defaults_no_file_no_env(clear_env, tmp_path, monkeypatch):
    # 默认配置路径不存在 → 默认值 + WARN（不 fail-fast）
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    cfg, warnings = load_config(config_file=str(tmp_path / "absent.toml"))
    assert cfg.deadline_default_ms == 5000
    assert cfg.retrieve_deadline_ms == 150
    assert cfg.outbox_poll_interval_s == 1
    assert cfg.outbox_max_retries == 3
    assert cfg.embedding_model == "default"
    assert cfg.log_level == "INFO"
    assert any("配置文件不存在" in w for w in warnings)


def test_toml_values_loaded(clear_env, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        "[socket]\npath = '/tmp/kylin-memory/memory.sock'\n"
        "[database]\npath = '/tmp/kylin-memory/test.db'\n"
        "[deadline]\ndefault_ms = 3000\n"
        "[retrieve]\ndeadline_ms = 200\n"
        "[outbox]\npoll_interval_s = 2\nmax_retries = 5\n"
        "[embedding]\nmodel = 'gte'\n"
        "[log]\nlevel = 'DEBUG'\n",
        encoding="utf-8",
    )
    cfg, _ = load_config(config_file=str(cfg_file))
    assert cfg.socket_path == "/tmp/kylin-memory/memory.sock"
    assert cfg.database_path == "/tmp/kylin-memory/test.db"
    assert cfg.deadline_default_ms == 3000
    assert cfg.retrieve_deadline_ms == 200
    assert cfg.outbox_poll_interval_s == 2
    assert cfg.outbox_max_retries == 5
    assert cfg.embedding_model == "gte"
    assert cfg.log_level == "DEBUG"


def test_env_overrides_file(clear_env, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[deadline]\ndefault_ms = 1000\n", encoding="utf-8")
    os.environ["KYLIN_MEMORY_DEADLINE_MS"] = "7000"
    os.environ["KYLIN_MEMORY_LOG_LEVEL"] = "ERROR"
    cfg, _ = load_config(config_file=str(cfg_file))
    assert cfg.deadline_default_ms == 7000  # env 优先于 file
    assert cfg.log_level == "ERROR"


def test_cli_override_top_priority(clear_env, tmp_path):
    os.environ["KYLIN_MEMORY_SOCKET"] = "/tmp/from-env.sock"
    cfg, _ = load_config(config_file=str(tmp_path / "absent.toml"), socket_override="/tmp/from-cli.sock")
    assert cfg.socket_path == "/tmp/from-cli.sock"  # CLI > env


def test_cli_db_override(clear_env, tmp_path):
    # --db CLI 覆盖最高优先级（app.py 接线，冒烟测试暴露）
    os.environ["KYLIN_MEMORY_DB"] = "/tmp/from-env.db"
    cfg, _ = load_config(
        config_file=str(tmp_path / "absent.toml"),
        db_override=str(tmp_path / "from-cli.db"),
    )
    assert cfg.database_path == str(tmp_path / "from-cli.db")  # CLI > env


def test_invalid_file_value_fail_fast(clear_env, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[deadline]\ndefault_ms = 0\n", encoding="utf-8")  # 非法：非正整数
    with pytest.raises(ValueError, match="配置非法"):
        load_config(config_file=str(cfg_file))


def test_invalid_env_value_fail_fast(clear_env, tmp_path):
    os.environ["KYLIN_MEMORY_LOG_LEVEL"] = "VERBOSE"  # 不在枚举内
    with pytest.raises(ValueError, match="配置非法"):
        load_config(config_file=str(tmp_path / "absent.toml"))


def test_xdg_runtime_expansion(clear_env, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run_dir))
    cfg, _ = load_config(config_file=str(tmp_path / "absent.toml"))
    assert cfg.socket_path.startswith(str(run_dir))


def test_parent_dir_created(clear_env, tmp_path):
    db_parent = tmp_path / "deep" / "nested"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f"[database]\npath = '{db_parent}/kylin_memory.db'\n", encoding="utf-8")
    cfg, _ = load_config(config_file=str(cfg_file))
    assert Path(cfg.database_path).parent.exists()


def test_memory_config_model_extra_forbidden():
    with pytest.raises(Exception):
        MemoryConfig(socket_path="a", unknown_key=1)
