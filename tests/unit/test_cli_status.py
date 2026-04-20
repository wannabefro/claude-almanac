"""Tests for the richer `claude-almanac status` output."""
from __future__ import annotations

from unittest.mock import MagicMock

from claude_almanac.cli import status as cli_status


def test_status_full_render(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import archive, paths
    g_db = paths.global_memory_dir() / "archive.db"
    archive.init(g_db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(g_db, text="t", kind="user", source="md:user_a.md",
                         pinned=True, embedding=[0.0, 1.0])
    (paths.digests_dir() / "2026-04-19.md").parent.mkdir(parents=True, exist_ok=True)
    (paths.digests_dir() / "2026-04-19.md").write_text("x")
    from claude_almanac.platform.base import SchedulerStatus
    fake_sched = MagicMock()
    fake_sched.status.return_value = SchedulerStatus(
        name="com.claude-almanac.digest", running=True, last_exit_code=None,
    )
    monkeypatch.setattr(cli_status, "get_scheduler", lambda: fake_sched)
    monkeypatch.setattr(cli_status, "_ollama_reachable", lambda endpoint: True)
    cli_status.run()
    out = capsys.readouterr().out
    assert "claude-almanac" in out
    assert "data_dir:" in out
    assert "archive" in out
    assert "global:" in out
    assert "1 entries" in out
    assert "1 pinned" in out
    assert "digest" in out
    assert "embedder" in out
    assert "ollama" in out
    assert "reachable: yes" in out


def test_status_flags_embedder_mismatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import archive, paths
    g_db = paths.global_memory_dir() / "archive.db"
    archive.init(g_db, embedder_name="voyage", model="voyage-3-large",
                 dim=1024, distance="cosine")
    from claude_almanac.platform.base import SchedulerStatus

    def _fake_scheduler():
        sched = MagicMock()
        sched.status = lambda name: SchedulerStatus(name=name, running=False, last_exit_code=None)
        return sched

    monkeypatch.setattr(cli_status, "get_scheduler", _fake_scheduler)
    monkeypatch.setattr(cli_status, "_ollama_reachable", lambda endpoint: False)
    cli_status.run()
    out = capsys.readouterr().out
    assert "warnings" in out
    assert "mismatch" in out.lower()
