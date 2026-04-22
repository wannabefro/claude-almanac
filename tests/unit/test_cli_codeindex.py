import argparse
import pathlib
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


# --- v0.4.1 hotfix: CLI wires documents.ingest/refresh into init/refresh ---


def _make_code_index_yaml(repo: pathlib.Path, *, docs_enabled: bool = True) -> None:
    """Write a minimal `.claude/code-index.yaml` under ``repo`` so
    `codeindex.config.load()` succeeds in dispatch tests."""
    (repo / ".claude").mkdir(parents=True, exist_ok=True)
    docs_block = "docs:\n  enabled: false\n" if not docs_enabled else ""
    (repo / ".claude" / "code-index.yaml").write_text(
        "default_branch: main\n"
        "modules:\n"
        "  patterns: []\n"
        + docs_block
    )


def test_cmd_init_runs_doc_ingest_when_enabled(tmp_path, monkeypatch):
    """After sym init succeeds, cmd_init must call documents.ingest.index_repo
    with the docs patterns/excludes/chunk sizes from the repo-local config."""
    import pathlib as _pl

    from claude_almanac.cli import codeindex as ci
    from claude_almanac.core import config as core_config

    repo = tmp_path / "repo"
    repo.mkdir()
    _make_code_index_yaml(repo, docs_enabled=True)

    # Stub sym init (covered elsewhere) so we can focus on the doc wiring.
    monkeypatch.setattr(
        "claude_almanac.codeindex.init.main", lambda r: 0,
    )
    # Stub embedder construction.
    class _FakeEmb:
        dim = 4
        distance = "l2"
        name = "fake"
        model = "fake"
        def embed(self, texts): return [[0.0] * 4 for _ in texts]
    monkeypatch.setattr(
        "claude_almanac.embedders.make_embedder",
        lambda provider, model: _FakeEmb(),
    )
    monkeypatch.setattr(
        core_config, "load", lambda: core_config.default_config(),
    )
    # Route data/logs to tmp_path so we don't dirty real XDG state.
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    calls: list[dict] = []

    def _fake_index_repo(**kwargs):
        calls.append(kwargs)
        return 7  # chunks written

    import claude_almanac.documents.ingest as _di
    monkeypatch.setattr(_di, "index_repo", _fake_index_repo)

    ns = argparse.Namespace(repo=str(repo))
    rc = ci.cmd_init(ns)
    assert rc == 0
    assert len(calls) == 1, "documents.ingest.index_repo should run once"
    kw = calls[0]
    assert kw["repo_root"] == str(_pl.Path(repo).resolve()) or kw["repo_root"] == str(repo)
    # Default DocsCfg patterns + chunk sizes propagated.
    assert kw["chunk_max_chars"] == 2000
    assert kw["chunk_overlap_chars"] == 200
    assert "docs/**" in kw["patterns"]
    assert isinstance(kw["excludes"], list)


def test_cmd_init_skips_doc_ingest_when_docs_disabled(tmp_path, monkeypatch):
    """If `.claude/code-index.yaml` has `docs.enabled: false`, cmd_init
    must NOT invoke documents.ingest.index_repo."""
    from claude_almanac.cli import codeindex as ci
    from claude_almanac.core import config as core_config

    repo = tmp_path / "repo"
    repo.mkdir()
    _make_code_index_yaml(repo, docs_enabled=False)

    monkeypatch.setattr(
        "claude_almanac.codeindex.init.main", lambda r: 0,
    )
    monkeypatch.setattr(
        core_config, "load", lambda: core_config.default_config(),
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    calls: list[dict] = []

    def _fake_index_repo(**kwargs):
        calls.append(kwargs)
        return 0

    import claude_almanac.documents.ingest as _di
    monkeypatch.setattr(_di, "index_repo", _fake_index_repo)

    ns = argparse.Namespace(repo=str(repo))
    rc = ci.cmd_init(ns)
    assert rc == 0
    assert calls == [], "docs.enabled=false must skip documents.ingest"


def test_cmd_refresh_runs_doc_refresh(tmp_path, monkeypatch):
    """cmd_refresh must invoke both codeindex.refresh and documents.refresh
    when `docs.enabled` is True (default)."""
    from claude_almanac.cli import codeindex as ci
    from claude_almanac.core import config as core_config

    repo = tmp_path / "repo"
    repo.mkdir()
    _make_code_index_yaml(repo, docs_enabled=True)

    # Both sym refresh and doc refresh should be invoked.
    refresh_calls: list[str] = []
    doc_refresh_calls: list[dict] = []

    monkeypatch.setattr(
        "claude_almanac.codeindex.refresh.main",
        lambda r: refresh_calls.append(r) or 0,
    )

    class _FakeEmb:
        dim = 4
        distance = "l2"
        name = "fake"
        model = "fake"
        def embed(self, texts): return [[0.0] * 4 for _ in texts]
    monkeypatch.setattr(
        "claude_almanac.embedders.make_embedder",
        lambda provider, model: _FakeEmb(),
    )
    monkeypatch.setattr(
        core_config, "load", lambda: core_config.default_config(),
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    def _fake_refresh_repo(**kwargs):
        doc_refresh_calls.append(kwargs)
        return 0

    import claude_almanac.documents.refresh as _dr
    monkeypatch.setattr(_dr, "refresh_repo", _fake_refresh_repo)

    ns = argparse.Namespace(repo=str(repo), all_repos=False)
    rc = ci.cmd_refresh(ns)
    assert rc == 0
    assert refresh_calls == [str(repo)]
    assert len(doc_refresh_calls) == 1
    kw = doc_refresh_calls[0]
    assert kw["chunk_max_chars"] == 2000
    assert kw["chunk_overlap_chars"] == 200
    assert "docs/**" in kw["patterns"]
