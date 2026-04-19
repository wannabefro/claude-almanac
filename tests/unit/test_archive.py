import pytest

from claude_almanac.core import archive


def test_init_creates_schema(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    meta = archive.get_meta(db)
    assert meta["embedder"] == "ollama"
    assert meta["model"] == "bge-m3"
    assert meta["dim"] == 4
    assert meta["distance"] == "l2"


def test_mismatched_embedder_refuses(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    with pytest.raises(archive.EmbedderMismatch):
        archive.assert_compatible(db, embedder_name="openai", model="any", dim=1536)


def test_insert_and_search_roundtrip(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db,
        text="hello world",
        kind="reference",
        source="test",
        pinned=True,
        embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db,
        text="goodbye",
        kind="reference",
        source="test",
        pinned=False,
        embedding=[0.0, 1.0],
    )
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].text == "hello world"
    assert hits[0].distance < 0.1


def test_nearest_source_prefix_filter(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db, text="a", kind="note", source="md:foo.md",
        pinned=True, embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db, text="b", kind="note", source="turn",
        pinned=False, embedding=[1.0, 0.0],
    )
    hit = archive.nearest(db, query_embedding=[1.0, 0.0], source_prefix="md:")
    assert hit.source == "md:foo.md"


def test_mismatched_model_refuses(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    with pytest.raises(archive.EmbedderMismatch):
        archive.init(db, embedder_name="ollama", model="other-model", dim=4, distance="l2")


def test_prune_old_unpinned(tmp_path):
    import time
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    old_ts = int(time.time()) - 86400 * 200
    archive.insert_entry(
        db, text="stale", kind="note", source="t", pinned=False,
        embedding=[1.0, 0.0], created_at=old_ts,
    )
    archive.insert_entry(
        db, text="pinned-stale", kind="note", source="t", pinned=True,
        embedding=[0.0, 1.0], created_at=old_ts,
    )
    removed = archive.prune(db, days=180)
    assert removed == 1
