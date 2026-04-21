"""Regression tests for digest collector kind resolution.

Before this fix, memories written without YAML frontmatter (the current
curator output shape since v0.2.x) showed up in the daily digest as
`[unknown]`. The fix adds a resolution chain: frontmatter → archive DB
→ slug prefix → `unknown`. Tests cover each rung.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_almanac.digest.collectors import _resolve_kind, _scan_md_dir


def _seed_archive(db: Path, filename: str, kind: str) -> None:
    """Create a minimal archive DB with a single entries row."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("""
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO entries (text, kind, source, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("body", kind, f"md:{filename}", 1),
        )
        conn.commit()
    finally:
        conn.close()


def test_resolve_kind_frontmatter_wins_over_everything(tmp_path):
    fm = {"type": "feedback"}
    _seed_archive(tmp_path / "archive.db", "foo.md", "project")
    kind = _resolve_kind(fm, filename="foo.md", slug="foo",
                         archive_db=tmp_path / "archive.db")
    assert kind == "feedback"


def test_resolve_kind_uses_archive_when_no_frontmatter(tmp_path):
    _seed_archive(tmp_path / "archive.db", "foo.md", "project")
    kind = _resolve_kind({}, filename="foo.md", slug="foo",
                         archive_db=tmp_path / "archive.db")
    assert kind == "project"


def test_resolve_kind_falls_back_to_slug_prefix(tmp_path):
    # No frontmatter, no archive DB row — use the naming convention.
    archive_db = tmp_path / "archive.db"  # doesn't exist
    kind = _resolve_kind({}, filename="feedback_foo.md", slug="feedback_foo",
                         archive_db=archive_db)
    assert kind == "feedback"


@pytest.mark.parametrize("slug,expected", [
    ("feedback_abc", "feedback"),
    ("project_xyz", "project"),
    ("reference_something", "reference"),
    ("user_profile", "user"),
])
def test_slug_prefix_covers_canonical_kinds(tmp_path, slug, expected):
    archive_db = tmp_path / "archive.db"  # doesn't exist
    kind = _resolve_kind({}, filename=f"{slug}.md", slug=slug,
                         archive_db=archive_db)
    assert kind == expected


def test_resolve_kind_unknown_when_nothing_matches(tmp_path):
    archive_db = tmp_path / "archive.db"
    kind = _resolve_kind({}, filename="random.md", slug="random",
                         archive_db=archive_db)
    assert kind == "unknown"


def test_scan_md_dir_surfaces_archive_kind_for_frontmatterless_files(tmp_path):
    """End-to-end: memory file with no frontmatter + archive row returns correct kind."""
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    p = mem_dir / "some_concept.md"
    p.write_text("bare body no frontmatter")
    _seed_archive(mem_dir / "archive.db", "some_concept.md", "project")
    out = _scan_md_dir(mem_dir, "project", cutoff_ts=0)
    assert len(out) == 1
    assert out[0]["kind"] == "project"
    assert out[0]["slug"] == "some_concept"


def test_scan_md_dir_handles_missing_archive(tmp_path):
    """No archive.db alongside → falls through to prefix heuristic without crashing."""
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    (mem_dir / "feedback_thing.md").write_text("body")
    out = _scan_md_dir(mem_dir, "global", cutoff_ts=0)
    assert len(out) == 1
    assert out[0]["kind"] == "feedback"
