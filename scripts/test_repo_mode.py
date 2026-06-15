#!/usr/bin/env python3
"""
test_repo_mode.py — live end-to-end smoke test for repo mode.

Runs the actual git tools against a real (public) repo using the real
GITHUB_TOKEN. Designed to be run manually on the server after activating
repo mode to confirm the full clone→edit→commit→push→PR flow works.

Usage:
    python scripts/test_repo_mode.py --repo owner/repo [--branch test/agent-e2e]

Requirements:
    - GITHUB_TOKEN set in env (or .env loaded)
    - git installed
    - The token must have Contents + Pull Requests write access to --repo
"""
import argparse
import os
import sys
import tempfile

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def _check(label: str, result: str, expect: str = None, not_expect: str = "ERROR"):
    ok = True
    if not_expect and not_expect in result:
        ok = False
    if expect and expect not in result:
        ok = False
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         got: {result[:300]}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Repo-mode E2E smoke test")
    parser.add_argument("--repo", required=True,
                        help="owner/repo to test against (e.g. yourname/test-repo)")
    parser.add_argument("--branch", default="test/agent-e2e",
                        help="Branch name to create (default: test/agent-e2e)")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("ERROR: GITHUB_TOKEN is not set. Add it to .env or export it.")
        sys.exit(1)

    # Use a temporary directory as the workspace
    with tempfile.TemporaryDirectory(prefix="agent_e2e_") as ws:
        # Bind the workspace so tools use it
        from core.tools import _workspace_root
        _workspace_root.set(ws)

        # Import tools AFTER workspace is set
        import tools.github as gh
        from core.tools import write_file, read_file

        repo_url = f"https://github.com/{args.repo}.git"
        branch = args.branch

        passes = []

        # 1. Clone
        _section("1. git_clone")
        result = gh.git_clone(repo_url)
        print(f"  {result[:200]}")
        passes.append(_check("clone exits 0", result, expect="exit=0"))

        # Update workspace to the cloned repo dir
        repo_name = args.repo.split("/")[-1]
        repo_dir = os.path.join(ws, repo_name)
        if os.path.isdir(repo_dir):
            _workspace_root.set(repo_dir)
            from core.tools import _workspace_root as _wr
            _wr.set(repo_dir)
            # Rebind current_workspace mock
            import core.tools as ct
            ct._workspace_root.set(repo_dir)
        else:
            print("  FAIL: cloned directory not found — aborting")
            sys.exit(1)

        # 2. Status
        _section("2. git_status")
        result = gh.git_status()
        print(f"  {result[:200]}")
        passes.append(_check("status exits 0", result, expect="exit=0"))

        # 3. Log
        _section("3. git_log")
        result = gh.git_log(n=3)
        print(f"  {result[:300]}")
        passes.append(_check("log exits 0", result, expect="exit=0"))

        # 4. Checkout branch
        _section("4. git_checkout_branch")
        result = gh.git_checkout_branch(branch, create=True)
        print(f"  {result[:200]}")
        passes.append(_check("checkout exits 0", result, expect="exit=0"))

        # 5. Write a file
        _section("5. write_file + read_file")
        write_file("agent_e2e_test.txt",
                   "This file was written by the agent repo-mode E2E test.\n")
        result = read_file("agent_e2e_test.txt")
        passes.append(_check("file written and readable", result,
                              expect="agent_e2e_test.txt",
                              not_expect="ERROR"))

        # 6. Diff
        _section("6. git_diff")
        result = gh.git_diff()
        print(f"  {result[:300]}")
        passes.append(_check("diff shows new file or empty ok", result, expect="exit=0"))

        # 7. Commit
        _section("7. git_commit")
        result = gh.git_commit("test: agent repo-mode E2E smoke test", "agent_e2e_test.txt")
        print(f"  {result[:300]}")
        passes.append(_check("commit exits 0", result, expect="exit=0"))

        # 8. Push  (requires human approval in normal agent runs — bypassed here for testing)
        _section("8. git_push")
        result = gh.git_push(branch)
        print(f"  {result[:300]}")
        passes.append(_check("push exits 0", result, expect="exit=0"))

        # 9. Create PR
        _section("9. create_pull_request")
        result = gh.create_pull_request(
            title="[test] Agent repo-mode E2E smoke test",
            body="Automated test PR from `scripts/test_repo_mode.py`. Safe to close.",
            head_branch=branch,
            repo=args.repo,
        )
        print(f"  {result[:400]}")
        passes.append(_check("PR created", result,
                              expect="PR created", not_expect="ERROR"))

    # Summary
    _section("RESULTS")
    total = len(passes)
    passed = sum(passes)
    print(f"  {passed}/{total} checks passed")
    if passed < total:
        print("\n  SOME CHECKS FAILED — see above for details")
        sys.exit(1)
    else:
        print("\n  All checks passed — repo mode is working end-to-end!")


if __name__ == "__main__":
    main()
