"""One-off: call Ollama gemma3:4b (or configured model) with the curator
prompt against N representative transcripts, record raw outputs + lengths,
detect truncation.

Usage:
    python scripts/gemma_truncation_probe.py tests/fixtures/transcripts/*.jsonl

The script reuses the curator's own system-prompt builder and conversation
parser so results are representative of real curator runs.
"""
from __future__ import annotations

# Ensure src/ is importable when run from the repo root.
# This must come before the claude_almanac imports below.
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

import argparse  # noqa: E402
import json  # noqa: E402

from claude_almanac.core import config as _config  # noqa: E402
from claude_almanac.core.curator import (  # noqa: E402
    _build_system_prompt,
    _parse_full_transcript,
)
from claude_almanac.curators import make_curator  # noqa: E402


def looks_truncated(raw: str) -> bool:
    """Heuristic: valid JSON must close with } or ]; anything else is truncated."""
    stripped = raw.strip().rstrip("`").rstrip()
    return not (stripped.endswith("}") or stripped.endswith("]"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe Ollama curator for truncation")
    ap.add_argument("fixtures", nargs="+", type=Path, help="Transcript .jsonl files")
    args = ap.parse_args()

    cfg = _config.load()
    curator = make_curator(cfg)
    system_prompt = _build_system_prompt()

    results = []
    for fx in args.fixtures:
        if not fx.exists():
            print(f"SKIP {fx.name}: not found", file=sys.stderr)
            continue
        # _parse_full_transcript expects a path string
        user_turn = _parse_full_transcript(str(fx))
        raw = curator.invoke(system_prompt, user_turn)
        truncated = looks_truncated(raw)
        results.append({
            "fixture": fx.name,
            "len": len(raw),
            "truncated": truncated,
            "raw_tail": raw[-200:],
        })
        flag = "TRUNCATED" if truncated else "ok"
        print(f"{fx.name:40s} len={len(raw):6d}  {flag}")

    total = len(results)
    if total == 0:
        print("No fixtures processed.")
        return 1
    trunc = sum(1 for r in results if r["truncated"])
    print(f"\nSummary: {trunc}/{total} truncated ({trunc / total * 100:.0f}%)")
    print(json.dumps(results, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
