# -*- coding: utf-8 -*-
"""The Config.lua the manager generates must be valid Lua even when names carry
quotes or backslashes, and the SavedVariables parser must survive the new
nested arena-team list."""
import importlib.util, io, os, sys, tempfile
try:
    import lupa
except ImportError:
    print('SKIP: lupa is not installed (pip install lupa)')
    raise SystemExit(0)

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

BS = chr(92)
QUOTE = chr(34)
nasty = "Тест" + QUOTE + "о" + BS + "x"

wow = tempfile.mkdtemp(prefix="wowmgr_lua_")
os.makedirs(os.path.join(wow, "Interface", "AddOns"), exist_ok=True)
L.INGAME.clear()
L.deploy_addon(wow, True, True,
               characters=[{"name": nasty, "account": "acc", "class": "Маг"}],
               current_account="acc" + QUOTE + "s")
src = io.open(os.path.join(wow, "Interface", "AddOns", "WowManager",
                           "Config.lua"), encoding="utf-8").read()
lua = lupa.LuaRuntime(unpack_returned_tuples=False)
run = lua.eval("function(s) local f,e = load(s); if f then f(); return 'OK' end return e end")
res = run(src)
print("generated Config.lua:", res)
assert res == "OK", src

sv = """
WowManagerDB = {
  ["R.Тест"] = { ["name"]="Тест", ["arenaTeams"] = {
      { ["size"]=2, ["rating"]=1580, ["mine"]=7 },
      { ["size"]=3, ["rating"]=1490, ["mine"]=4 }, },
    ["dailyDone"]=7, ["dailyMax"]=25, ["questsDone"]=2, ["questsTotal"]=18 },
}
"""
db = L.parse_lua_savedvars(sv)["WowManagerDB"]["R.Тест"]
L.INGAME.clear()
L.INGAME["тест"] = db
lines = L.card_lines({"name": "Тест"}, L.CARD_ORDER)
assert any("2x2" in x for x in lines), lines
assert any("3x3" in x for x in lines), lines
assert any("7 / 25" in x for x in lines), lines
assert any("2 / 18" in x for x in lines), lines
print("SavedVariables round-trip: OK")
sys.exit(0)
