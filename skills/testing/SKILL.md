---
name: testing
description: Write good, meaningful tests for code (pytest/unit tests) — edge cases, isolation, clear assertions. Use when the task is to add or improve a test suite.
keywords: [test, tests, pytest, unittest, unit test, coverage, fixture, mock, edge case, assertion, tdd, test suite, regression test]
agents: [coder, fast-coder, data-analyst]
---

# Writing tests that catch real bugs

A test suite that only checks the happy path gives false confidence. Test behavior and edges.

## What to cover
- **The contract**: the function's documented behavior for typical inputs.
- **Edge cases**: empty / zero / negative / very large inputs, boundaries, duplicates,
  missing keys/files, unicode — the places bugs actually live.
- **Error paths**: assert the RIGHT exception is raised on bad input (`pytest.raises`), not
  just that "it works".
- **Regressions**: when you fix a bug, add a test that fails without the fix.

## How
1. **Isolate.** Each test is independent and repeatable — use `tmp_path`/fixtures for files,
   don't depend on test order or shared mutable state, don't hit the network.
2. **One behavior per test**, with a name that says what it checks
   (`test_rejects_negative_amount`).
3. **Assert on values, not on "no exception."** Check the actual result, not just truthiness.
4. **Arrange-Act-Assert**: set up, do the one thing, assert. Keep setup in fixtures.
5. **Run them** (`python -m pytest -q`) and make sure they pass — and that they'd FAIL if the
   code were wrong (a test that can't fail is worthless).

## Anti-patterns
- Tests that assert `is not None` and nothing else. Weakening or deleting a test to make it
  pass. Over-mocking until the test no longer exercises real code.
