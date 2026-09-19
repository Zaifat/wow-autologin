#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run every check. From the repository root:

    python tests/run_all.py

The Lua tests need `lupa` (pip install lupa) and are skipped without it.
test_window.py builds the real Tk window, so it needs a desktop session.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TESTS = [
    "test_core.py",
    "test_features.py",
    "test_tools.py",
    "test_roster.py",
    "test_game.py",
    "test_ipc.py",
    "test_window.py",
    "test_static_audit.py",
    "test_lua_syntax.py",
    "test_lua_globals.py",
    "test_lua_generated.py",
    "test_addon_logic.py",
]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    failed = []
    for name in TESTS:
        print("=" * 60)
        print(name)
        print("=" * 60)
        sys.stdout.flush()
        r = subprocess.run([sys.executable, os.path.join(HERE, name)],
                           cwd=ROOT, env=env)
        if r.returncode != 0:
            failed.append(name)
        print()
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("all suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
