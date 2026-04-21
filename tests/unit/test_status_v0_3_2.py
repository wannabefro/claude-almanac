import sqlite3
from contextlib import suppress
from pathlib import Path

from claude_almanac.cli.main import main as cli_main


def _seed_rollup_and_edge(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO rollups (session_id, repo_key, started_at, ended_at,"
            " turn_count, trigger, narrative, decisions, artifacts, created_at)"
            " VALUES ('s1', 'r', 1, 2, 5, 'session_end', 'N', '[]', '{}', 100)"
        )
        conn.execute(
            "INSERT INTO edges (src_id, src_scope, dst_id, dst_scope, type, created_at, created_by)"
            " VALUES (1, 'entry@project', 2, 'entry@project', 'related', 100, 'curator')"
        )
        conn.commit()
    finally:
        conn.close()


def test_status_shows_rollup_and_edge_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core.archive import init
    from claude_almanac.core.paths import project_memory_dir
    from claude_almanac.embedders.profiles import get
    project_memory_dir().mkdir(parents=True, exist_ok=True)
    db = project_memory_dir() / "archive.db"
    profile = get("ollama", "bge-m3")
    init(db, embedder_name=profile.provider, model=profile.model,
         dim=profile.dim, distance=profile.distance)
    _seed_rollup_and_edge(db)
    with suppress(SystemExit):
        cli_main(["status"])
    out = capsys.readouterr().out
    assert "rollup" in out.lower()
    assert "edge" in out.lower()
    # Counts should appear
    assert "1" in out  # 1 rollup, 1 edge
