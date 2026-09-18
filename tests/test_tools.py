# -*- coding: utf-8 -*-
"""Roster export, WTF settings transfer, and the in-game alts summary."""
import importlib.util, io, os, sys, tempfile

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_tools_")
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── feature 8: roster export ───────────────────────────────────────────────
L.INGAME.clear()
L.INGAME["тестомаг"] = {"name": "Тестомаг", "level": 80, "gs": 5400,
                        "guild": "Гильдия",
                        "profs": ["Кузнец 450/450", "Горное 450/450",
                                  "Первая помощь 450/450", "Кулинария 450/450"]}
cfg = {"characters": [
    {"name": "Тестомаг", "class": "Маг", "realm": "WoW Circle x100"},
    {"name": "Безданных", "class": "Друид", "realm": "WoW Circle x100"},
    {"name": "", "account": "acc-only"},
]}

rows = L.roster_rows(cfg)
check("roster skips account-only entries", len(rows) == 2)
check("roster fills in collected data",
      rows[0][2] == "80" and rows[0][3] == "5400" and rows[0][4] == "Гильдия")
check("roster tolerates a character with no data",
      rows[1][0] == "Безданных" and rows[1][2] == "")
check("roster caps the profession list",
      rows[0][6].count(",") == 2)

txt = L.format_roster(cfg, "text")
check("text format is aligned", "Тестомаг" in txt and "---" in txt)
bb = L.format_roster(cfg, "bbcode")
check("bbcode is a table", bb.startswith("[table]") and bb.endswith("[/table]")
      and "[td]Тестомаг[/td]" in bb)
md = L.format_roster(cfg, "markdown")
check("markdown is a pipe table",
      md.splitlines()[1].startswith("|---") and "| Тестомаг |" in md)
check("every advertised format renders",
      all(L.format_roster(cfg, f) for f in L.ROSTER_FORMATS))
check("empty roster returns nothing",
      L.format_roster({"characters": []}, "text") == "")

# ── feature 4: compact summary for the in-game list ────────────────────────
L.INGAME["тестомаг"]["gold"] = 12345678
line = L.entry_summary({"name": "Тестомаг"})
check("summary mentions level and gear", "80" in line and "5400" in line)
check("summary mentions gold", "234" in line or "1234" in line)
check("summary is empty without data", L.entry_summary({"name": "Нет"}) == "")

wow = os.path.join(tmp, "game")
os.makedirs(os.path.join(wow, "Interface", "AddOns"), exist_ok=True)
L.deploy_addon(wow, True, True, characters=cfg["characters"],
               card_fields=L.CARD_ORDER, current_account="acc-only")
conf = io.open(os.path.join(wow, "Interface", "AddOns", "WowManager",
                            "Config.lua"), encoding="utf-8").read()
check("addon config carries the summary", "summary = " in conf and "5400" in conf)

# ── feature 11: WTF discovery ──────────────────────────────────────────────
def touch(path, body="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


base = os.path.join(wow, "WTF", "Account", "ACCONE")
src = os.path.join(base, "WoW Circle x100", "Тестомаг")
dst1 = os.path.join(base, "WoW Circle x100", "Тестопал")
dst2 = os.path.join(base, "WoW Circle x1", "Тестожрец")
for f in ("config-cache.wtf", "layout-local.txt", "AddOns.txt",
          "macros-cache.txt"):
    touch(os.path.join(src, f), "source-" + f)
touch(os.path.join(src, "SavedVariables", "Some.lua"), "sv")
touch(os.path.join(dst1, "config-cache.wtf"), "old")
os.makedirs(dst2, exist_ok=True)
# account-wide SavedVariables must not be mistaken for a realm
touch(os.path.join(base, "SavedVariables", "WowManager.lua"), "acct")

found = L.list_wtf_characters(wow)
names = [c for _a, _r, c, _p in found]
check("wtf discovery finds every character",
      sorted(names) == sorted(["Тестомаг", "Тестопал", "Тестожрец"]))
check("wtf discovery skips account-level SavedVariables",
      "SavedVariables" not in [r for _a, r, _c, _p in found])
check("wtf discovery on a missing folder returns nothing",
      L.list_wtf_characters(os.path.join(tmp, "nope")) == [])

# copy only interface + addon list
copied, errors = L.copy_wtf_settings(src, [dst1, dst2], ["config", "addons"])
check("copy reported no errors", not errors)
check("copy overwrote the target's interface",
      io.open(os.path.join(dst1, "config-cache.wtf"), encoding="utf-8").read()
      == "source-config-cache.wtf")
check("copy created files in an empty target",
      os.path.isfile(os.path.join(dst2, "AddOns.txt")))
check("unselected groups are left alone",
      not os.path.isfile(os.path.join(dst1, "macros-cache.txt")))
check("SavedVariables not copied when not asked",
      not os.path.isdir(os.path.join(dst1, "SavedVariables")))

# now with SavedVariables and macros
copied2, errors2 = L.copy_wtf_settings(src, [dst1], ["savedvars", "macros"])
check("second pass reported no errors", not errors2)
check("SavedVariables copied on request",
      os.path.isfile(os.path.join(dst1, "SavedVariables", "Some.lua")))
check("macros copied on request",
      os.path.isfile(os.path.join(dst1, "macros-cache.txt")))

# copying onto itself must be a no-op, not a self-destruct
before = io.open(os.path.join(src, "config-cache.wtf"), encoding="utf-8").read()
n, e = L.copy_wtf_settings(src, [src], ["config"])
check("copying onto the source is skipped", n == 0 and not e)
check("source left intact",
      io.open(os.path.join(src, "config-cache.wtf"), encoding="utf-8").read()
      == before)

# a missing source file is normal, not an error
sparse = os.path.join(base, "WoW Circle x1", "Пустой")
os.makedirs(sparse, exist_ok=True)
n2, e2 = L.copy_wtf_settings(sparse, [dst1], ["config", "addons", "macros"])
check("absent source files are not errors", n2 == 0 and not e2)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
