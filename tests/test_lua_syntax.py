# -*- coding: utf-8 -*-
"""Compile the addon's Lua files to catch syntax errors (no WoW APIs needed)."""
import io, sys
try:
    import lupa
except ImportError:
    print('SKIP: lupa is not installed (pip install lupa)')
    raise SystemExit(0)

files = ["addon/WowManager/Core.lua", "addon/WowManager/Config.lua"]
bad = False
L = lupa.LuaRuntime(unpack_returned_tuples=False)
check = L.eval("function(s) local f, e = load(s); if f then return 'OK' end return e end")
for f in files:
    src = io.open(f, encoding="utf-8").read()
    res = check(src)
    if res == "OK":
        print("OK %s" % f)
    else:
        print("SYNTAX ERROR %s: %s" % (f, res))
        bad = True
sys.exit(1 if bad else 0)
