import pytest
from unittest.mock import MagicMock
from claude_almanac.core import dedup
from claude_almanac.core.archive import Hit


def _hit(source: str, distance: float) -> Hit:
    return Hit(id=1, text="x", kind="reference", source=source, pinned=True,
               created_at=0, distance=distance)


def test_below_threshold_returns_slug(monkeypatch, tmp_path):
    db = tmp_path / "a.db"
    hit = _hit("md:existing.md", distance=14.0)
    monkeypatch.setattr("claude_almanac.core.dedup.archive.nearest", lambda *a, **kw: hit)
    slug, dist = dedup.find_dup_slug(db=db, embedding=[0.0], threshold=17.0)
    assert slug == "existing.md"
    assert dist == 14.0


def test_above_threshold_returns_none(monkeypatch, tmp_path):
    db = tmp_path / "a.db"
    hit = _hit("md:existing.md", distance=22.0)
    monkeypatch.setattr("claude_almanac.core.dedup.archive.nearest", lambda *a, **kw: hit)
    slug, dist = dedup.find_dup_slug(db=db, embedding=[0.0], threshold=17.0)
    assert slug is None
    assert dist == 22.0


def test_no_md_source_returns_none(monkeypatch, tmp_path):
    db = tmp_path / "a.db"
    monkeypatch.setattr("claude_almanac.core.dedup.archive.nearest", lambda *a, **kw: None)
    slug, dist = dedup.find_dup_slug(db=db, embedding=[0.0], threshold=17.0)
    assert slug is None
    assert dist is None


def test_threshold_boundary_is_inclusive_on_miss(monkeypatch, tmp_path):
    db = tmp_path / "a.db"
    hit = _hit("md:foo.md", distance=17.0)
    monkeypatch.setattr("claude_almanac.core.dedup.archive.nearest", lambda *a, **kw: hit)
    slug, dist = dedup.find_dup_slug(db=db, embedding=[0.0], threshold=17.0)
    # Strict <: 17.0 means "not a dup" (matches curator-worker.py contract)
    assert slug is None
