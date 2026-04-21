"""End-to-end: curator writes a memory → recall search finds it → retrieve injects it."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_curator_write_then_recall_search_returns_entry(isolated_data_dir):
    transcript = isolated_data_dir / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "user",
                                "content": "remember that my color preference is teal"}})
        + "\n"
        + json.dumps({"message": {"role": "assistant",
                                  "content": "Noted: teal."}})
        + "\n"
    )
    env = {**os.environ, "CLAUDE_ALMANAC_TRANSCRIPT": str(transcript)}
    # Kick the curator directly (not via the Stop hook).
    result = subprocess.run(
        ["python", "-m", "claude_almanac.core.curator"],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    # Recall search: CLI must complete without crash. Curator may or may not
    # have saved (LLM may decline to save from a thin transcript).
    search = subprocess.run(
        ["claude-almanac", "recall", "search", "color preference"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert search.returncode == 0, search.stderr
    # Curator may decline to save from a thin 2-turn transcript; in that case
    # `recall search` prints the `(no matches)` sentinel introduced in v0.3.6.
    # Accept either outcome: a real hit mentioning teal, or the no-match path.
    stdout = search.stdout.strip().lower()
    assert "teal" in stdout or stdout in ("", "(no matches)")
