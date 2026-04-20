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


def test_ollama_uses_split_timeouts_by_default():
    e = OllamaEmbedder(model="bge-m3", dim=1024)
    t = e._client.timeout
    # Connect must stay tight to surface unreachable hosts fast;
    # read must be generous to tolerate bge-m3 cold-load.
    assert t.connect == 5.0
    assert t.read == 120.0


def test_ollama_timeout_overrides_are_honored():
    e = OllamaEmbedder(
        model="bge-m3", dim=1024,
        connect_timeout=1.5, read_timeout=45.0,
        write_timeout=10.0, pool_timeout=10.0,
    )
    t = e._client.timeout
    assert t.connect == 1.5
    assert t.read == 45.0
    assert t.write == 10.0
    assert t.pool == 10.0
