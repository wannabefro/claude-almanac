from claude_almanac.codeindex import config as ci_config
from claude_almanac.codeindex import refresh


def test_resolve_module_for_file_longest_prefix():
    mods = [
        ci_config.Module(name="src", path="/r/src"),
        ci_config.Module(name="src/nested", path="/r/src/nested"),
    ]
    assert refresh.resolve_module_for_file("src/nested/x.py", mods) == "src/nested"
    assert refresh.resolve_module_for_file("src/a.py", mods) == "src"
    assert refresh.resolve_module_for_file("other/y.py", mods) is None


def test_resolve_module_for_file_exact_match():
    mods = [ci_config.Module(name="src", path="/r/src")]
    assert refresh.resolve_module_for_file("src", mods) == "src"
