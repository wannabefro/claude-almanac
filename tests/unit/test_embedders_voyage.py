from unittest.mock import MagicMock, patch

from claude_almanac.embedders.voyage import VoyageEmbedder


def test_voyage_embed_returns_vectors():
    with patch("claude_almanac.embedders.voyage.voyageai") as mock_vg:
        client = MagicMock()
        mock_vg.Client.return_value = client
        client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2], [0.3, 0.4]])
        e = VoyageEmbedder(model="voyage-3-large", dim=2, api_key="pa-test")
        out = e.embed(["x", "y"])
        assert out == [[0.1, 0.2], [0.3, 0.4]]
        client.embed.assert_called_once_with(
            texts=["x", "y"], model="voyage-3-large", input_type="document"
        )


def test_voyage_attrs():
    with patch("claude_almanac.embedders.voyage.voyageai"):
        e = VoyageEmbedder(model="voyage-3-large", dim=1024, api_key="pa-test")
    assert e.name == "voyage"
    assert e.dim == 1024
    assert e.distance == "cosine"
