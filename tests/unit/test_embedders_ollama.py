import httpx
import pytest

from claude_almanac.embedders.ollama import OllamaEmbedder


def test_ollama_embed_batches_texts(respx_mock):
    mock = respx_mock.post("http://localhost:11434/api/embed").mock(
        return_value=httpx.Response(
            200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        )
    )
    e = OllamaEmbedder(model="bge-m3", dim=2, host="http://localhost:11434")
    out = e.embed(["alpha", "beta"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert mock.called
    assert mock.calls[0].request.content  # payload sent


def test_ollama_raises_on_empty_batch():
    e = OllamaEmbedder(model="bge-m3", dim=1024)
    with pytest.raises(ValueError, match="empty"):
        e.embed([])


def test_ollama_attrs():
    e = OllamaEmbedder(model="bge-m3", dim=1024)
    assert e.name == "ollama"
    assert e.dim == 1024
    assert e.distance == "l2"
