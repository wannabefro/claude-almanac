from unittest.mock import MagicMock

from claude_almanac.embedders import calibrate


def test_calibrate_produces_histogram(monkeypatch):
    fake_embedder = MagicMock()
    fake_embedder.distance = "l2"
    # pairs: 3 near-dups (~14), 3 same-topic (~21), 3 unrelated (~28)
    def fake_embed(texts):
        lookup = {
            "a1": [1.0, 0.0, 0.0], "a2": [0.99, 0.01, 0.0],
            "b1": [0.5, 0.5, 0.0], "b2": [0.3, 0.7, 0.0],
            "c1": [0.0, 0.0, 1.0], "c2": [0.0, 0.0, 0.9],
        }
        return [lookup[t] for t in texts]
    fake_embedder.embed.side_effect = fake_embed
    pairs = [("a1", "a2"), ("b1", "b2"), ("c1", "c2")]
    distances = calibrate.distances(fake_embedder, pairs)
    assert len(distances) == 3
    assert all(d >= 0 for d in distances)
