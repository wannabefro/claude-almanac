"""`claude-almanac tail` — interleave curator/codeindex/digest/server logs."""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass

from claude_almanac.core import paths

_SOURCES = {
    "curator": "curator.log",
    "code-index": "code-index.log",
    "digest": "com.claude-almanac.digest.log",
    "server": "com.claude-almanac.server.log",
}

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


@dataclass
class _Line:
    ts: str
    source: str
    payload: str
    continuation: bool = False

    def render(self) -> str:
        tag = f"{self.source} cont" if self.continuation else f"{self.source} {self.ts}"
        return f"[{tag}] {self.payload.rstrip()}"


def _parse_lines(source: str, raw: str) -> list[_Line]:
    out: list[_Line] = []
    last_ts = "0000-00-00 00:00:00"
    for raw_line in raw.splitlines():
        m = _TS_RE.match(raw_line)
        if m:
            last_ts = m.group(1).replace("T", " ")
            out.append(_Line(ts=last_ts, source=source, payload=raw_line))
        else:
            out.append(
                _Line(ts=last_ts, source=source, payload=raw_line, continuation=True)
            )
    return out


def _since_cutoff(spec: str) -> float | None:
    m = re.fullmatch(r"(\d+)([smhd])", spec)
    if not m:
        return None
    n = int(m.group(1))
    unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    return time.time() - n * unit


def _parse_args(argv: list[str]) -> dict[str, object]:
    opts: dict[str, object] = {
        "follow": True,
        "lines": 50,
        "since": None,
        "sources": list(_SOURCES.keys()),
    }
    explicit_sources: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--follow":
            opts["follow"] = True
            i += 1
        elif a == "--no-follow":
            opts["follow"] = False
            i += 1
        elif a == "--lines" and i + 1 < len(argv):
            opts["lines"] = int(argv[i + 1])
            i += 2
        elif a == "--since" and i + 1 < len(argv):
            opts["since"] = argv[i + 1]
            i += 2
        elif a == "--source" and i + 1 < len(argv):
            explicit_sources.append(argv[i + 1])
            i += 2
        else:
            i += 1
    if explicit_sources:
        opts["sources"] = explicit_sources
    return opts


def _backfill(opts: dict[str, object]) -> list[_Line]:
    logs_dir = paths.logs_dir()
    all_lines: list[_Line] = []
    sources = opts["sources"]
    assert isinstance(sources, list)
    for src in sources:
        filename = _SOURCES.get(src)
        if filename is None:
            continue
        p = logs_dir / filename
        if not p.exists():
            continue
        raw = p.read_text(errors="replace")
        all_lines.extend(_parse_lines(src, raw))
    all_lines.sort(key=lambda line: (line.ts, line.source))
    lines_val = opts["lines"]
    assert isinstance(lines_val, int)
    return all_lines[-lines_val:]


def run(argv: list[str]) -> None:
    opts = _parse_args(argv)
    for line in _backfill(opts):
        print(line.render())
    if not opts["follow"]:
        return
    logs_dir = paths.logs_dir()
    sources = opts["sources"]
    assert isinstance(sources, list)
    offsets: dict[str, int] = {}
    for src in sources:
        filename = _SOURCES.get(src)
        if filename is None:
            continue
        p = logs_dir / filename
        offsets[src] = p.stat().st_size if p.exists() else 0
    try:
        while True:
            new_lines: list[_Line] = []
            for src in sources:
                filename = _SOURCES.get(src)
                if filename is None:
                    continue
                p = logs_dir / filename
                if not p.exists():
                    continue
                size = p.stat().st_size
                if size <= offsets[src]:
                    continue
                with p.open("r", errors="replace") as f:
                    f.seek(offsets[src])
                    chunk = f.read()
                    offsets[src] = f.tell()
                new_lines.extend(_parse_lines(src, chunk))
            new_lines.sort(key=lambda line: (line.ts, line.source))
            for line in new_lines:
                print(line.render(), flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        sys.exit(0)
