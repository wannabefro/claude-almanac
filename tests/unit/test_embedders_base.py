import pytest
from claude_almanac.embedders.base import Embedder, EmbedderProfile
from claude_almanac.embedders import profiles


def test_profile_has_ollama_bge_m3_threshold():
    p = profiles.get("ollama", "bge-m3")
    assert p.dedup_distance == 17.0
    assert p.dim == 1024
    assert p.distance == "l2"


def test_profile_unknown_raises():
    with pytest.raises(KeyError):
        profiles.get("nonexistent-provider", "nonexistent-model")


def test_embedder_is_a_protocol():
    # Duck-typing check: anything with .name, .dim, .distance, .embed() qualifies.
    class FakeEmbedder:
        name = "fake"
        dim = 4
        distance = "l2"

        def embed(self, texts):
            return [[0.0] * 4 for _ in texts]

    fake: Embedder = FakeEmbedder()  # Protocol acceptance
    assert fake.embed(["a"])[0] == [0.0, 0.0, 0.0, 0.0]
