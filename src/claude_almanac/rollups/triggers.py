"""Parse Claude Code hook event payloads into RollupEvent records."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_EVENT_MAP = {"SessionEnd": "session_end", "PreCompact": "pre_compact"}


@dataclass(frozen=True)
class RollupEvent:
    trigger: str          # 'session_end' | 'pre_compact' | 'idle' | 'explicit'
    transcript_path: Path
    session_id: str
    cwd: Path


def parse_hook_event(stdin_payload: str) -> RollupEvent | None:
    """Parse the JSON stdin from a SessionEnd or PreCompact hook.

    Returns None on unknown event, missing fields, or malformed JSON.
    """
    try:
        data = json.loads(stdin_payload)
    except json.JSONDecodeError:
        LOGGER.debug("rollup-hook: non-json stdin payload")
        return None

    ev_name = data.get("hook_event_name")
    trigger = _EVENT_MAP.get(ev_name)
    if trigger is None:
        return None

    t_path = data.get("transcript_path")
    sid = data.get("session_id")
    cwd = data.get("cwd")
    if not (t_path and sid and cwd):
        return None

    return RollupEvent(
        trigger=trigger,
        transcript_path=Path(t_path),
        session_id=str(sid),
        cwd=Path(cwd),
    )
