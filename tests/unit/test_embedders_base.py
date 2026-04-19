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
        model = "fake"
        dim = 4
        distance = "l2"

        def embed(self, texts):
            return [[0.0] * 4 for _ in texts]

    fake: Embedder = FakeEmbedder()  # Protocol acceptance
    assert fake.embed(["a"])[0] == [0.0, 0.0, 0.0, 0.0]


def test_concrete_embedders_name_equals_provider():
    from unittest.mock import patch
    from claude_almanac.embedders.ollama import OllamaEmbedder
    from claude_almanac.embedders.openai import OpenAIEmbedder
    from claude_almanac.embedders.voyage import VoyageEmbedder

    ollama = OllamaEmbedder(model="bge-m3", dim=1024)
    assert ollama.name == "ollama"

    with patch("claude_almanac.embedders.openai.OpenAI"):
        openai = OpenAIEmbedder(model="text-embedding-3-small", dim=1536, api_key="x")
    assert openai.name == "openai"

    with patch("claude_almanac.embedders.voyage.voyageai"):
        voyage = VoyageEmbedder(model="voyage-3-large", dim=1024, api_key="x")
    assert voyage.name == "voyage"
