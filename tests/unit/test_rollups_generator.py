import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_almanac.rollups.generator import Rollup, RollupGenerator


@pytest.fixture
def fake_curator():
    c = MagicMock()
    c.invoke.return_value = json.dumps({
        "narrative": "We debugged the X bug and found Y.",
        "decisions": [{"title": "Picked B over A", "why": "Y is faster"}],
        "artifacts": {"files": ["src/x.py"], "commits": ["abc1234"], "memories": []},
    })
    return c


@pytest.fixture
def fake_embedder():
    e = MagicMock()
    e.embed.return_value = [[0.1] * 1024]
    return e


def _write_transcript(path: Path, n_turns: int = 5) -> None:
    lines = []
    for i in range(n_turns):
        lines.append(json.dumps({"type": "user", "message": {"content": f"q{i}"},
                                 "timestamp": i * 10 + 1}))
        lines.append(json.dumps({"type": "assistant", "message": {"content": f"a{i}"},
                                 "timestamp": i * 10 + 2}))
    path.write_text("\n".join(lines) + "\n")


def test_generate_parses_and_returns_rollup(tmp_path, fake_curator, fake_embedder):
    t = tmp_path / "s.jsonl"
    _write_transcript(t, n_turns=3)  # 6 lines, 6 turns in the stream
    gen = RollupGenerator(
        curator=fake_curator, embedder=fake_embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )
    rollup = gen.generate(
        transcript_path=t, session_id="s1",
        repo_key="r", branch="main", trigger="session_end",
        min_turns=3,
    )
    assert isinstance(rollup, Rollup)
    assert "debugged" in rollup.narrative
    assert rollup.decisions == [{"title": "Picked B over A", "why": "Y is faster"}]


def test_generate_skips_when_under_min_turns(tmp_path, fake_curator, fake_embedder):
    t = tmp_path / "s.jsonl"
    _write_transcript(t, n_turns=1)  # 2 turns
    gen = RollupGenerator(
        curator=fake_curator, embedder=fake_embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )
    rollup = gen.generate(
        transcript_path=t, session_id="s1", repo_key="r", branch=None,
        trigger="session_end", min_turns=3,
    )
    assert rollup is None


def test_generate_handles_non_json_llm_output(tmp_path, fake_embedder):
    bad_curator = MagicMock()
    bad_curator.invoke.return_value = "I cannot comply."
    t = tmp_path / "s.jsonl"
    _write_transcript(t, n_turns=3)
    gen = RollupGenerator(
        curator=bad_curator, embedder=fake_embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )
    rollup = gen.generate(
        transcript_path=t, session_id="s1", repo_key="r", branch=None,
        trigger="session_end", min_turns=3,
    )
    assert rollup is None


def test_generate_handles_code_fenced_json(tmp_path, fake_embedder):
    fenced_curator = MagicMock()
    fenced_curator.invoke.return_value = (
        '```json\n{"narrative": "N", "decisions": [], "artifacts": {}}\n```'
    )
    t = tmp_path / "s.jsonl"
    _write_transcript(t, n_turns=3)
    gen = RollupGenerator(
        curator=fenced_curator, embedder=fake_embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )
    rollup = gen.generate(
        transcript_path=t, session_id="s1", repo_key="r", branch=None,
        trigger="session_end", min_turns=3,
    )
    assert rollup is not None
    assert rollup.narrative == "N"


def test_generate_drops_empty_narrative(tmp_path, fake_embedder):
    curator = MagicMock()
    curator.invoke.return_value = '{"narrative": "", "decisions": [], "artifacts": {}}'
    t = tmp_path / "s.jsonl"
    _write_transcript(t, n_turns=3)
    gen = RollupGenerator(
        curator=curator, embedder=fake_embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )
    assert gen.generate(
        transcript_path=t, session_id="s1", repo_key="r", branch=None,
        trigger="session_end", min_turns=3,
    ) is None
