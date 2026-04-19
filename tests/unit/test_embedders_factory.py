import pytest
from unittest.mock import patch
from claude_almanac.embedders.factory import make_embedder


def test_factory_returns_ollama_by_default():
    e = make_embedder("ollama", "bge-m3")
    assert e.name == "ollama"


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unknown embedder"):
        make_embedder("nonexistent", "any")


def test_factory_wires_openai():
    with patch("claude_almanac.embedders.openai.OpenAI"):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-x"}):
            e = make_embedder("openai", "text-embedding-3-small")
    assert e.name == "openai"
