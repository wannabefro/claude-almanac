from unittest.mock import patch

from claude_almanac.cli import main as cli_main


def test_parser_accepts_codeindex_subcommands():
    p = cli_main.build_parser()
    ns = p.parse_args(["codeindex", "init"])
    assert ns.cmd == "codeindex"
    assert ns.ci_cmd == "init"


def test_parser_codeindex_refresh_with_repo():
    p = cli_main.build_parser()
    ns = p.parse_args(["codeindex", "refresh", "--repo", "/tmp/r"])
    assert ns.ci_cmd == "refresh"
    assert ns.repo == "/tmp/r"


def test_dispatch_init_calls_init_main():
    with patch("claude_almanac.codeindex.init.main", return_value=0) as m:
        cli_main.main(["codeindex", "init", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r")


def test_dispatch_status_calls_status_main():
    with patch("claude_almanac.codeindex.status.main", return_value=0) as m:
        cli_main.main(["codeindex", "status", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r")


def test_dispatch_arch_passes_global_flag():
    with patch("claude_almanac.codeindex.arch.main", return_value=0) as m, \
         patch("claude_almanac.core.config.load") as cfg_load:
        cfg_load.return_value.code_index.send_code_to_llm = True
        cli_main.main(["codeindex", "arch", "--repo", "/tmp/r"])
    m.assert_called_once_with("/tmp/r", global_send_code_to_llm=True)
