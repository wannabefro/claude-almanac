"""Cross-platform notify shim over `platform.Notifier`."""
from __future__ import annotations

from ..platform import get_notifier


def notify(*, title: str, message: str, open_url: str) -> bool:
    try:
        get_notifier().notify(title, message, link=open_url)
        return True
    except Exception:
        return False
