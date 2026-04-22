"""Document-subsystem scoring profile (v0.4).

Starts as a no-op ScoringProfile. Doc-specific rules (demoting generic
headings like 'Overview', 'TODO', etc.) are deferred to v0.4.1 after
dogfood surfaces false positives.
"""
from __future__ import annotations

from claude_almanac.contentindex.scoring import ScoringProfile

DOC_PROFILE = ScoringProfile()
