from unittest.mock import MagicMock

from claude_almanac.cli import calibrate as cli_calibrate


def test_calibrate_prints_threshold_and_histogram(tmp_path, monkeypatch, capsys):
    fixture = tmp_path / "pairs.jsonl"
    fixture.write_text(
        '{"a": "hello", "b": "hello world"}\n'
        '{"a": "foo", "b": "foo bar baz"}\n'
        '{"a": "cat", "b": "cat sat on mat"}\n'
    )
    fake_embedder = MagicMock()
    fake_embedder.distance = "cosine"
    fake_embedder.embed.side_effect = lambda texts: [
        [float(i), 0.0] for i, _ in enumerate(texts)
    ]
    monkeypatch.setattr(cli_calibrate, "make_embedder", lambda *a, **kw: fake_embedder)
    cli_calibrate.run(["voyage", "voyage-3-large", str(fixture)])
    out = capsys.readouterr().out
    assert "threshold" in out.lower()
    assert "voyage" in out
    assert "histogram" in out.lower() or "│" in out or "#" in out


def test_calibrate_missing_args_exits_nonzero(capsys):
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli_calibrate.run([])
    assert exc.value.code == 2
