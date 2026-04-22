from unittest.mock import patch

from claude_almanac.cli import main as cli_main


def test_parser_accepts_content_subcommands():
    p = cli_main.build_parser()
    ns = p.parse_args(["content", "init"])
    assert ns.cmd == "content"
    assert ns.ci_cmd == "init"


def test_parser_codeindex_refresh_with_repo():
    p = cli_main.build_parser()
    ns = p.parse_args(["content", "refresh", "--repo", "/tmp/r"])
    assert ns.ci_cmd == "refresh"
    assert ns.repo == "/tmp/r"


def test_dispatch_init_calls_init_main():
    with patch("claude_almanac.codeindex.init.main", return_value=0) as m:
        cli_main.main(["content", "init", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r")


def test_dispatch_status_calls_status_main():
    with patch("claude_almanac.codeindex.status.main", return_value=0) as m:
        cli_main.main(["content", "status", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r")


def test_dispatch_arch_passes_global_flag():
    with patch("claude_almanac.codeindex.arch.main", return_value=0) as m, \
         patch("claude_almanac.core.config.load") as cfg_load:
        cfg_load.return_value.content_index.send_code_to_llm = True
        cli_main.main(["content", "arch", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r", global_send_code_to_llm=True)


def test_parser_refresh_accepts_all_flag():
    p = cli_main.build_parser()
    ns = p.parse_args(["content", "refresh", "--all"])
    assert ns.ci_cmd == "refresh"
    assert ns.all_repos is True


def test_refresh_all_iterates_configured_repos(tmp_path, monkeypatch):
    """With --all, the CLI should walk digest.repos, running init for
    missing DBs and refresh for present ones, and return 0 on success."""
    from claude_almanac.core import config as core_config

    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    for r in (repo_a, repo_b):
        (r / ".git").mkdir(parents=True)

    cfg = core_config.default_config()
    cfg.digest.repos = [
        core_config.RepoCfg(path=str(repo_a), alias="a"),
        core_config.RepoCfg(path=str(repo_b), alias="b"),
    ]
    monkeypatch.setattr("claude_almanac.core.config.load", lambda: cfg)

    init_calls: list[str] = []
    refresh_calls: list[str] = []

    def fake_init(p: str) -> int:
        init_calls.append(p)
        return 0

    def fake_refresh(p: str) -> int:
        refresh_calls.append(p)
        return 0

    # Force both repos to look "un-initialized" so init runs for each.
    monkeypatch.setattr(
        "claude_almanac.core.paths.project_memory_dir",
        lambda: tmp_path / "nope",
    )
    monkeypatch.setattr("claude_almanac.codeindex.init.main", fake_init)
    monkeypatch.setattr("claude_almanac.codeindex.refresh.main", fake_refresh)

    cli_main.main(["content", "refresh", "--all"])
    assert [str(repo_a.resolve()), str(repo_b.resolve())] == init_calls
    assert [str(repo_a.resolve()), str(repo_b.resolve())] == refresh_calls


def test_refresh_all_continues_on_per_repo_failure(tmp_path, monkeypatch, capsys):
    from claude_almanac.core import config as core_config

    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    for r in (repo_a, repo_b):
        (r / ".git").mkdir(parents=True)

    cfg = core_config.default_config()
    cfg.digest.repos = [
        core_config.RepoCfg(path=str(repo_a), alias="a"),
        core_config.RepoCfg(path=str(repo_b), alias="b"),
    ]
    monkeypatch.setattr("claude_almanac.core.config.load", lambda: cfg)
    # DB exists so refresh runs directly without init.
    db = tmp_path / "dbdir"
    db.mkdir()
    (db / "content-index.db").write_text("")
    monkeypatch.setattr(
        "claude_almanac.core.paths.project_memory_dir", lambda: db,
    )

    refresh_calls: list[str] = []

    def fake_refresh(p: str) -> int:
        refresh_calls.append(p)
        if p == str(repo_a.resolve()):
            raise RuntimeError("boom")
        return 0

    monkeypatch.setattr("claude_almanac.codeindex.refresh.main", fake_refresh)
    import pytest
    with pytest.raises(SystemExit) as e:
        cli_main.main(["content", "refresh", "--all"])
    assert e.value.code == 1
    # Second repo still processed despite first's failure.
    assert refresh_calls == [str(repo_a.resolve()), str(repo_b.resolve())]


def test_refresh_all_errors_when_repos_empty(monkeypatch, capsys):
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    monkeypatch.setattr("claude_almanac.core.config.load", lambda: cfg)
    import pytest
    with pytest.raises(SystemExit) as e:
        cli_main.main(["content", "refresh", "--all"])
    assert e.value.code == 1
    assert "digest.repos" in capsys.readouterr().err
