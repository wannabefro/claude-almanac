from claude_almanac.codeindex import log


def test_emit_writes_quoted_values(tmp_path):
    target = tmp_path / "code-index.log"
    log.emit(target, component="code-index", level="info", event="test.evt",
             repo="foo bar", count=3, ok=True)
    contents = target.read_text().splitlines()
    assert len(contents) == 1
    line = contents[0]
    assert "\tevent=test.evt\t" in line
    assert "\trepo=\"foo bar\"\t" in line
    assert "\tcount=3\t" in line
    assert line.endswith("ok=true")


def test_emit_skips_none_values(tmp_path):
    target = tmp_path / "code-index.log"
    log.emit(target, component="code-index", level="info", event="x", maybe=None)
    assert "maybe=" not in target.read_text()
