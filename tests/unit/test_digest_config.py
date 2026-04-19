from pathlib import Path

import pytest

from claude_almanac.digest import config as dcfg


def test_from_core_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path=str(tmp_path / "r"), alias="r")]
    rt = dcfg.from_core_config(cfg)
    assert rt.repos[0].name == "r"
    assert rt.repos[0].path == str(tmp_path / "r")
    assert rt.window_hours == 24
    assert rt.retention_days == 30
    assert rt.haiku_model == "haiku"
    assert rt.notification is True
    assert rt.digest_dir == str(tmp_path / "data" / "digests")


def test_from_core_config_rejects_empty_repos(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    with pytest.raises(dcfg.ConfigError):
        dcfg.from_core_config(cfg)
