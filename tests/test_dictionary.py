from jaspervoice.dictionary import DeveloperDictionary, DictionaryEntry


def test_empty_text_returns_empty():
    d = DeveloperDictionary([{"phrase": "foo", "replacement": "bar"}])
    assert d.apply("") == ""


def test_no_entries_returns_original():
    d = DeveloperDictionary()
    assert d.apply("hello world") == "hello world"


def test_single_phrase_replacement():
    d = DeveloperDictionary([{"phrase": "open code", "replacement": "OpenCode"}])
    assert d.apply("use open code here") == "use OpenCode here"


def test_case_insensitive_matching():
    d = DeveloperDictionary([{"phrase": "open code", "replacement": "OpenCode"}])
    assert d.apply("Open Code") == "OpenCode"
    assert d.apply("OPEN CODE") == "OpenCode"
    assert d.apply("open code") == "OpenCode"


def test_replacement_preserves_configured_casing():
    d = DeveloperDictionary([{"phrase": "fast api", "replacement": "FastAPI"}])
    assert d.apply("fast api") == "FastAPI"


def test_multi_word_phrase_replacement():
    d = DeveloperDictionary([{"phrase": "react query", "replacement": "ReactQuery"}])
    assert d.apply("use react query for data") == "use ReactQuery for data"


def test_does_not_replace_inside_larger_words():
    d = DeveloperDictionary([{"phrase": "api", "replacement": "API"}])
    assert d.apply("api call") == "API call"
    assert d.apply("capital") == "capital"
    assert d.apply("capitation") == "capitation"


def test_longer_phrases_apply_before_shorter():
    d = DeveloperDictionary([
        {"phrase": "react", "replacement": "React"},
        {"phrase": "react query", "replacement": "ReactQuery"},
    ])
    assert d.apply("react query is cool") == "ReactQuery is cool"


def test_invalid_entries_ignored():
    d = DeveloperDictionary([
        {"phrase": "", "replacement": "Foo"},
        {"phrase": "bar", "replacement": ""},
        "not_a_dict",
        {"phrase": "   valid   ", "replacement": "   ValidReplacement   "},
    ])
    assert d.apply("valid phrase") == "ValidReplacement phrase"


def test_multiple_entries_in_one_text():
    d = DeveloperDictionary([
        {"phrase": "use effect", "replacement": "useEffect"},
        {"phrase": "fast api", "replacement": "FastAPI"},
    ])
    assert d.apply("use effect with fast api") == "useEffect with FastAPI"


def test_punctuation_around_phrase_still_works():
    d = DeveloperDictionary([
        {"phrase": "use effect", "replacement": "useEffect"},
        {"phrase": "fast api", "replacement": "FastAPI"},
    ])
    assert d.apply("use effect, then fast api.") == "useEffect, then FastAPI."


def test_whitespace_in_entries_is_stripped():
    d = DeveloperDictionary([
        {"phrase": "  tail wind  ", "replacement": "  Tailwind  "},
    ])
    assert d.apply("use tail wind css") == "use Tailwind css"


def test_DictionaryEntry_instances_accepted():
    d = DeveloperDictionary([
        DictionaryEntry(phrase="react query", replacement="ReactQuery"),
    ])
    assert d.apply("react query") == "ReactQuery"


def test_none_entries_is_same_as_empty():
    d = DeveloperDictionary(None)
    assert d.apply("hello") == "hello"


# --- Enabled / disabled rules ---

def test_disabled_rule_is_not_applied():
    d = DeveloperDictionary([
        {"phrase": "py side", "replacement": "PySide6", "enabled": False},
    ])
    assert d.apply("use py side here") == "use py side here"


def test_missing_enabled_defaults_to_true():
    d = DeveloperDictionary([{"phrase": "py side", "replacement": "PySide6"}])
    assert d.apply("py side") == "PySide6"


def test_mixed_enabled_and_disabled_rules():
    d = DeveloperDictionary([
        {"phrase": "git lab", "replacement": "GitLab"},
        {"phrase": "py side", "replacement": "PySide6", "enabled": False},
    ])
    assert d.apply("git lab and py side") == "GitLab and py side"


def test_DictionaryEntry_disabled_is_ignored():
    d = DeveloperDictionary([
        DictionaryEntry(phrase="react", replacement="React", enabled=False),
    ])
    assert d.apply("react") == "react"


def test_disabled_rules_still_listed_in_entries():
    d = DeveloperDictionary([
        {"phrase": "py side", "replacement": "PySide6", "enabled": False},
    ])
    assert len(d._entries) == 1
    assert d._entries[0].enabled is False
