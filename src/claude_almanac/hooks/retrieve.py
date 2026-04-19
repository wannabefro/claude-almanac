"""UserPromptSubmit hook entrypoint. Reads JSON {prompt: ...} from stdin,
prints context to stdout (which Claude Code injects into the turn)."""
from __future__ import annotations

import json
import sys

from ..core import retrieve as core_retrieve


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return
    prompt = payload.get("prompt", "")
    text = core_retrieve.run(prompt)
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
