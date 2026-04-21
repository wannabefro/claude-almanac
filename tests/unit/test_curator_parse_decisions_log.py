import logging

from claude_almanac.core.curator import _parse_decisions


def test_non_json_logs_full_payload_and_length(caplog):
    # raw is > 200 chars so "raw in msg" is a real regression guard
    # against someone restoring the old %.200s cap.
    raw = '{"decisions": [{"action": "write_md", "slug": "foo", "body": "' + ("x" * 200) + '"'
    assert len(raw) > 200
    with caplog.at_level(logging.WARNING, logger="claude_almanac.core.curator"):
        result = _parse_decisions(raw)
    assert result == []
    rec = caplog.records[-1]
    msg = rec.getMessage()
    assert str(len(raw)) in msg
    assert raw in msg
