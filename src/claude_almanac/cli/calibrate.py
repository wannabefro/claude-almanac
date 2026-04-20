"""`claude-almanac calibrate <provider> <model> <fixture-file>` —
embed pair fixtures and report a suggested dedup_distance threshold."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from claude_almanac.embedders import make_embedder
from claude_almanac.embedders.calibrate import distances


def _render_histogram(values: list[float], bins: int = 10) -> str:
    if not values:
        return "(no data)"
    lo, hi = min(values), max(values)
    if hi == lo:
        return f"all values = {lo:.3f}"
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    scale = max(counts)
    out_lines = []
    for i, c in enumerate(counts):
        bar = "#" * int(40 * c / scale) if scale else ""
        lo_i = lo + i * width
        out_lines.append(f"{lo_i:7.3f} │{bar} ({c})")
    return "\n".join(out_lines)


def _suggest_threshold(values: list[float]) -> float:
    """Pick a threshold ~20% above the max observed duplicate distance."""
    if not values:
        return 0.0
    return max(values) * 1.2


def run(argv: list[str]) -> None:
    if len(argv) < 3:
        print(
            "usage: claude-almanac calibrate <provider> <model> "
            "<fixture-file> [--out path]",
            file=sys.stderr,
        )
        sys.exit(2)
    provider, model, fixture_path = argv[0], argv[1], argv[2]
    out_csv: str | None = None
    if "--out" in argv:
        out_csv = argv[argv.index("--out") + 1]
    pairs: list[tuple[str, str]] = []
    for line in Path(fixture_path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        pairs.append((obj["a"], obj["b"]))
    embedder = make_embedder(provider, model)
    vals = distances(embedder, pairs)
    threshold = _suggest_threshold(vals)
    print(f"calibration: {provider}/{model}  pairs={len(pairs)}")
    print(
        f"  min={min(vals):.4f}  max={max(vals):.4f}  "
        f"mean={sum(vals)/len(vals):.4f}"
    )
    print(f"  suggested threshold (dedup_distance = max × 1.2): {threshold:.4f}")
    print()
    print("histogram")
    print(_render_histogram(vals))
    if out_csv:
        Path(out_csv).write_text("\n".join(f"{v:.6f}" for v in vals))
        print(f"raw distances written to {out_csv}")
