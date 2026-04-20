"""Decay-score-based pruning with 30-day safety floor."""
import time

import pytest

from claude_almanac.core import archive
from claude_almanac.core.config import DecayCfg


def _insert(db, **kw):
    return archive.insert_entry(
        db, text=kw.get("text", "t"), kind="note", source=kw.get("source", "t"),
        pinned=kw.get("pinned", False),
        embedding=kw.get("embedding", [1.0, 0.0]),
        created_at=kw["created_at"],
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "a.db"
    archive.init(path, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    return path


def test_prune_keeps_entries_within_min_age(db):
    now = int(time.time())
    young = _insert(db, created_at=now - 5 * 86400)  # 5 days old
    # threshold=1 = "prune everything allowed"
    cfg = DecayCfg(prune_threshold=1.0, prune_min_age_days=30)
    removed = archive.prune(db, cfg=cfg, now=now)
    assert removed == 0
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=5)
    assert any(h.id == young for h in hits)


def test_prune_evicts_old_low_score(db):
    now = int(time.time())
    ancient = _insert(db, created_at=now - 200 * 86400, embedding=[1.0, 0.0])
    # Default cfg: threshold=0.05, half_life=60d, min_age=30d → score after 200d ≈ 0.099
    # which is ABOVE 0.05. Use a shorter half-life so the entry falls below threshold.
    # Verify: score(0+1, 200d / 60d half-life) = 1 * 2^(-200/60) ≈ 0.099 — above 0.05.
    cfg = DecayCfg(prune_threshold=0.05, prune_min_age_days=30, half_life_days=20)
    removed = archive.prune(db, cfg=cfg, now=now)
    assert removed == 1
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=5)
    assert not any(h.id == ancient for h in hits)


def test_prune_keeps_pinned(db):
    now = int(time.time())
    pinned = _insert(db, created_at=now - 200 * 86400, pinned=True, embedding=[1.0, 0.0])
    cfg = DecayCfg(prune_threshold=0.05, prune_min_age_days=30, half_life_days=10)
    archive.prune(db, cfg=cfg, now=now)
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=5)
    assert any(h.id == pinned for h in hits)


def test_prune_keeps_recently_reinforced(db):
    now = int(time.time())
    rid = _insert(db, created_at=now - 100 * 86400, embedding=[1.0, 0.0])
    archive.reinforce(db, ids=[rid], now=now - 86400)  # reinforced yesterday
    cfg = DecayCfg(prune_threshold=0.05, prune_min_age_days=30, half_life_days=20)
    removed = archive.prune(db, cfg=cfg, now=now)
    assert removed == 0
