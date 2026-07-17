"""Regression for the push-after-clone bug: git_push must not DOUBLE-inject the token.

A tool-clone authenticates over https://oauth2:<token>@github.com/... and (before the fix)
left that credentialed URL in origin. git_push then injected the token again, producing
https://oauth2:<t>@oauth2:<t>@github.com/... which git rejects ("Port number was not a
decimal number") — so every push after a tool-clone failed. `_auth_url` is the helper that
now strips any existing credentials before injecting.
"""
from tools.github import _auth_url

TOK = "ghp_TESTTOKEN123"


def test_injects_into_clean_url():
    assert _auth_url("https://github.com/o/r.git", TOK) == f"https://oauth2:{TOK}@github.com/o/r.git"


def test_does_not_double_inject_when_token_already_present():
    already = f"https://oauth2:{TOK}@github.com/o/r.git"
    out = _auth_url(already, TOK)
    assert out == f"https://oauth2:{TOK}@github.com/o/r.git"
    assert out.count("@") == 1                       # exactly one credential segment
    assert "@oauth2:" not in out                     # never the malformed double form


def test_replaces_other_existing_credentials():
    out = _auth_url("https://user:oldpass@github.com/o/r.git", TOK)
    assert out == f"https://oauth2:{TOK}@github.com/o/r.git"
    assert out.count("@") == 1


def test_empty_token_is_a_noop():
    url = "https://github.com/o/r.git"
    assert _auth_url(url, "") == url


def test_non_https_is_a_noop():
    url = "git@github.com:o/r.git"
    assert _auth_url(url, TOK) == url
