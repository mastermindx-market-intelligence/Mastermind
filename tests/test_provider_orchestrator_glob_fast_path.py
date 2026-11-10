"""The glob-head shortcut preserves original lexical and scope distinctions."""
import pytest

from ops.executive_os import provider_orchestrator_guard as guard


_ENCODED_GLOBS = [
    encoded
    for char in sorted(guard._R6_GLOB_CHARS)
    for encoded in (f"$'\\x{ord(char):02x}'", f"$'\\{ord(char):03o}'", f"$'\\u{ord(char):04x}'")
]


@pytest.mark.parametrize("command", [
    *(prefix + encoded + " run glm" for encoded in _ENCODED_GLOBS for prefix in ("", "p")),
    "=(x) ", "(x) ", r"\x2a run glm", r'$"\x2a" run glm',
    r"$(printf '\052') run glm", "unterminated'", "$(unterminated",
])
def test_absent_raw_globs_cannot_be_created_as_unquoted_literal_segments(command):
    assert not any(char in command for char in guard._R6_GLOB_CHARS)
    tokens, _error = guard._r6_lex(command)
    assert all(not word.has_glob() for kind, word in tokens if kind == "word")
    assert guard._r7_glob_head_names_wrapper(command) is False


@pytest.mark.parametrize("command", [
    "* run glm", "p* run glm", "env p* run glm", "A=x command p* run glm",
    "p[o]ol run glm", "{p,q}ool run glm", "p?ol run glm", "p''* run glm",
    "p\\\n* run glm",
])
def test_original_raw_glob_heads_still_select_the_scope_reader(command):
    assert guard._r7_glob_head_names_wrapper(command) is True
    assert guard.r6_names_wrapper(command) is True


@pytest.mark.parametrize("command", [
    "pool run glm", "po\"\"ol run glm", "p\\\nool run glm",
    r"$'\x70ool' run glm", r"$(printf '\160')ool run glm",
])
def test_other_scope_readings_still_find_non_glob_wrapper_spellings(command):
    assert not any(char in command for char in guard._R6_GLOB_CHARS)
    assert guard.r6_names_wrapper(command) is True
