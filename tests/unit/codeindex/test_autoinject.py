from claude_almanac.codeindex import autoinject


def test_plain_english_prompt_does_not_trigger():
    assert not autoinject.should_query("what time is it today?")


def test_file_path_and_backtick_trigger():
    assert autoinject.should_query("where is `handle_request` defined in api.py?")


def test_camel_case_plus_file_trigger():
    assert autoinject.should_query("how does parseInput work in lexer.ts")


def test_how_does_x_work_idiom_plus_token_triggers():
    assert autoinject.should_query("how does `retry` work?")
