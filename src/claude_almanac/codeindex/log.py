"""Tab-separated key=value structured logger for the code-index subsystem.

Format: each line is `ts=ISO\tcomponent=...\tlevel=...\tevent=...\t<kv>...\n`.
Values are quoted if they contain whitespace, double-quote, equals, or are empty.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def _quote(value: str) -> str:
    needs_quoting = (
        not value
        or any(c in value for c in (" ", "\t", "\n", "\r", '"', "="))
    )
    if not needs_quoting:
        return value
    escaped = (
        value
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace('"', '\\"')
    )
    return '"' + escaped + '"'


def emit(path: str | Path, *, component: str, level: str, event: str, **kv: object) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    pairs = [
        f"ts={ts}",
        f"component={_quote(component)}",
        f"level={_quote(level)}",
        f"event={_quote(event)}",
    ]
    for k, v in kv.items():
        if v is None:
            continue
        rendered = "true" if v is True else "false" if v is False else str(v)
        pairs.append(f"{k}={_quote(rendered)}")
    line = "\t".join(pairs) + "\n"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "ab") as f:
        f.write(line.encode("utf-8"))
