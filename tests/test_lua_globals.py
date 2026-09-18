# -*- coding: utf-8 -*-
"""Catch accidental globals in the addon.

A missing `local` in a WoW addon leaks a name into `_G`, where it can collide
with another addon or with the game's own API. Only the handful of names the
addon deliberately publishes are allowed.
"""
import io, re, sys

ALLOWED = {
    "WowManagerDB",          # SavedVariables (declared in the .toc)
    "WowManagerCharDB",      # SavedVariablesPerCharacter
    "WowManagerConfig",      # written by the manager into Config.lua
    "SLASH_WOWMANAGER1",
    "SLASH_WOWMANAGER2",
    "SlashCmdList",
}

FILES = ["addon/WowManager/Core.lua", "addon/WowManager/Config.lua"]

# `function Name(` and `Name = ...` / `Name.field = ...` at column 0
FUNC = re.compile(r"^function\s+([A-Za-z_][\w]*)\s*[.:(]")
ASSIGN = re.compile(r"^([A-Za-z_][\w]*)\s*(?:\[[^\]]*\])?\s*(?:\.\w+)?\s*=[^=]")

bad = []
for path in FILES:
    for n, line in enumerate(io.open(path, encoding="utf-8"), 1):
        if line.startswith("local") or line.lstrip().startswith("--"):
            continue
        m = FUNC.match(line) or ASSIGN.match(line)
        if m and m.group(1) not in ALLOWED:
            bad.append("%s:%d declares global %r" % (path, n, m.group(1)))

if bad:
    for b in bad:
        print("FAIL " + b)
    sys.exit(1)
print("PASS no unexpected globals in the addon")
