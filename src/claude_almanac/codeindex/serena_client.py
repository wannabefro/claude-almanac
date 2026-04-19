"""Minimal Serena HTTP client used by the fallback extractor.

Serena is NOT bundled with claude-almanac. When it is unreachable, every
public function raises and the caller (serena_fallback.extract) swallows the
error and returns []. That behavior is the graceful-degradation contract.

We only implement get_symbols_overview here; find_symbol / find_referencing
were used by the original memory-tools implementation for de-facto-public
detection, which Plan 2 drops for performance reasons (see code_index_sym
module docstring in Task 9).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_PORT = int(os.environ.get("CLAUDE_ALMANAC_SERENA_PORT", "51777"))
_BASE_URL = f"http://127.0.0.1:{_PORT}"


@dataclass(frozen=True)
class SerenaSymbol:
    name: str
    kind: str          # lowercase ('function' | 'class' | ...)
    line_end: int      # 1-based, best-effort


def get_symbols_overview(repo_root: str, file_rel: str) -> list[SerenaSymbol]:
    """Call Serena's /query_project get_symbols_overview and flatten the result.

    Raises ConnectionError / urllib.error.URLError if the server is unreachable.
    Never returns None; empty list if Serena responded with no symbols.
    """
    payload = json.dumps({
        "project_name": str(Path(repo_root).resolve()),
        "tool_name": "get_symbols_overview",
        "tool_params_json": json.dumps({"relative_path": file_rel}),
    }).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}/query_project",
        data=payload, headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise ConnectionError(f"serena unreachable at {_BASE_URL}: {e}") from e
    text = r.read().decode()
    if text.startswith("Error"):
        raise RuntimeError(f"serena tool error: {text[:300]}")
    raw = json.loads(text)
    # Shape: {"Function": ["a", "b"], "Class": ["C"], ...}
    out: list[SerenaSymbol] = []
    for kind_label, value in raw.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    out.append(SerenaSymbol(name=item, kind=kind_label.lower(), line_end=0))
                elif isinstance(item, dict):
                    for class_name in item:
                        out.append(SerenaSymbol(name=class_name, kind=kind_label.lower(), line_end=0))
        elif isinstance(value, str):
            out.append(SerenaSymbol(name=value, kind=kind_label.lower(), line_end=0))
    return out
