"""Trust-boundary regression: arch pass must never run unless BOTH flags are true.

This test is marked integration because it exercises the real CLI parser end
to end; it does NOT require Ollama -- the test runs before the Anthropic call
would happen.
"""
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


def _yaml_with_send(tmp_path, send: bool) -> None:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "code-index.yaml").write_text(
        f"default_branch: main\n"
        f"send_code_to_llm: {'true' if send else 'false'}\n"
        f"modules:\n  patterns: ['src']\n"
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def f(): pass\n")


def test_cli_refuses_arch_when_global_flag_false(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    _yaml_with_send(tmp_path, send=True)
    from claude_almanac.cli import main as cli_main
    with patch("claude_almanac.core.config.load") as cfg_load, \
         patch("claude_almanac.codeindex.arch._haiku") as haiku:
        cfg_load.return_value.content_index.send_code_to_llm = False
        # Graceful exit path: arch.main() returns 0, dispatcher doesn't
        # sys.exit on rc=0, so cli_main.main() returns normally.
        cli_main.main(["content", "arch", "--repo", str(tmp_path)])
    haiku.assert_not_called()


def test_cli_refuses_arch_when_repo_flag_false(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    _yaml_with_send(tmp_path, send=False)
    from claude_almanac.cli import main as cli_main
    with patch("claude_almanac.core.config.load") as cfg_load, \
         patch("claude_almanac.codeindex.arch._haiku") as haiku:
        cfg_load.return_value.content_index.send_code_to_llm = True
        cli_main.main(["content", "arch", "--repo", str(tmp_path)])
    haiku.assert_not_called()
