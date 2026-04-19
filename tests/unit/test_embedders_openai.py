import pytest
from unittest.mock import MagicMock, patch
from claude_almanac.embedders.openai import OpenAIEmbedder


def test_openai_embed_returns_vectors():
    with patch("claude_almanac.embedders.openai.OpenAI") as mock_openai:
        client = MagicMock()
        mock_openai.return_value = client
        client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1, 0.2]), MagicMock(embedding=[0.3, 0.4])]
        )
        e = OpenAIEmbedder(model="text-embedding-3-small", dim=2, api_key="sk-test")
        out = e.embed(["a", "b"])
        assert out == [[0.1, 0.2], [0.3, 0.4]]
        client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small", input=["a", "b"]
        )


def test_openai_attrs():
    with patch("claude_almanac.embedders.openai.OpenAI"):
        e = OpenAIEmbedder(model="text-embedding-3-small", dim=1536, api_key="sk-test")
    assert e.name == "openai"
    assert e.dim == 1536
    assert e.distance == "cosine"


def test_openai_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("claude_almanac.embedders.openai.OpenAI"):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            OpenAIEmbedder(model="text-embedding-3-small", dim=1536)
