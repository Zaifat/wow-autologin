# -*- coding: utf-8 -*-
"""Account -> characters model and the automatic character import."""
import importlib.util, io, json, os, sys, tempfile

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


def names(cfg):
    return [(e.get("account"), e.get("name")) for e in cfg["characters"]]


# ── legacy flat config: characters only, interleaved accounts ──────────────
cfg = {"characters": [
    {"name": "Альфа", "account": "acc1", "password": "p1", "totp_secret": "",
     "realm": "R1", "realmlist": "logon.a", "class": "Маг"},
    {"name": "Бета", "account": "ACC2", "password": "p2", "realm": "R2",
     "realmlist": "logon.b", "class": "Воин"},
    {"name": "Гамма", "account": "Acc1", "password": "", "realm": "",
     "realmlist": "", "class": "Друид"},
    {"name": "", "account": "acc2", "password": "", "realm": "R2"},
    {"name": "", "account": "", "password": "x"},          # junk row
    {"name": "Сирота", "account": "", "class": "Жрец"},
]}
changed = L.normalize_roster(cfg)
check("normalize reports a change", changed)
check("groups: account, its characters, next account, orphans last",
      names(cfg) == [("acc1", ""), ("acc1", "Альфа"), ("acc1", "Гамма"),
                     ("acc2", ""), ("acc2", "Бета"), ("", "Сирота")])
acc1 = cfg["characters"][0]
check("missing account row was created with lifted credentials",
      acc1["password"] == "p1" and acc1["realmlist"] == "logon.a")
check("credentials copied down to every character",
      cfg["characters"][2]["password"] == "p1"
      and cfg["characters"][2]["realmlist"] == "logon.a")
check("empty character realm inherits the account realm",
      cfg["characters"][2]["realm"] == "R1")
check("existing account row lifts a password from its character",
      cfg["characters"][3]["password"] == "p2")
check("login casing comes from the account row",
      cfg["characters"][4]["account"] == "acc2")
check("junk rows are dropped", all(e.get("name") or e.get("account")
                                   for e in cfg["characters"]))
check("normalize is idempotent", not L.normalize_roster(cfg))

# duplicate account rows fold into one
dup = {"characters": [{"name": "", "account": "x", "password": ""},
                      {"name": "", "account": "X", "password": "pp",
                       "realm": "R"}]}
L.normalize_roster(dup)
check("duplicate account rows are folded",
      len(dup["characters"]) == 1 and dup["characters"][0]["password"] == "pp")

# ── groups for the tree ────────────────────────────────────────────────────
groups = L.roster_groups(cfg)
check("roster_groups: two accounts plus orphans", len(groups) == 3)
check("roster_groups: account indices point at account rows",
      groups[0][0] == 0 and groups[1][0] == 3 and groups[2][0] is None)
check("roster_groups: characters under the right account",
      [c["name"] for _i, c in groups[0][2]] == ["Альфа", "Гамма"])

# ── inserting and hiding ───────────────────────────────────────────────────
L.insert_character(cfg, {"name": "Дельта", "account": "acc1", "realm": "R1"})
check("new character lands inside its account group",
      names(cfg)[3] == ("acc1", "Дельта"))
L.hide_character(cfg, {"name": "Дельта", "account": "acc1", "realm": "R1"})
check("hide records the key", "acc1|r1|дельта" in cfg["hidden_chars"])
L.unhide_character(cfg, {"name": "Дельта", "account": "ACC1", "realm": "r1"})
check("unhide is case-insensitive", "acc1|r1|дельта" not in cfg["hidden_chars"])

# ── automatic import ───────────────────────────────────────────────────────
imp = {"characters": [{"name": "", "account": "Main", "password": "pw",
                       "totp_secret": "JBSWY3DPEHPK3PXP", "realm": "Realm",
                       "realmlist": "logon.x"}]}
L.normalize_roster(imp)
lists = [{"account": "main", "realm": "Realm", "at": 1,
          "chars": [{"name": "Первый", "level": 80, "class": 8},
                    {"name": "Второй", "level": 12, "class": 11},
                    {"name": "", "class": 1}]},
         {"account": "stranger", "realm": "Realm",
          "chars": [{"name": "Чужой", "class": 1}]}]
added = L.import_char_lists(imp, lists)
check("import adds the account's characters", added == ["Первый", "Второй"])
check("imported characters inherit credentials",
      all(e["password"] == "pw" and e["totp_secret"] == "JBSWY3DPEHPK3PXP"
          and e["realmlist"] == "logon.x"
          for e in imp["characters"] if e["name"]))
check("imported characters get their class", [
    e["class"] for e in imp["characters"] if e["name"]] == ["Маг", "Друид"])
check("unknown accounts are ignored",
      not any(e["name"] == "Чужой" for e in imp["characters"]))
check("re-import adds nothing", L.import_char_lists(imp, lists) == [])

# a deleted character stays deleted
victim = next(e for e in imp["characters"] if e["name"] == "Второй")
imp["characters"].remove(victim)
L.hide_character(imp, victim)
check("hidden character is not re-imported",
      L.import_char_lists(imp, lists) == [])
# ...until the user adds it back by hand
L.insert_character(imp, {"name": "Второй", "account": "Main", "realm": "Realm"})
check("manual re-add clears the hidden mark", not imp["hidden_chars"])

# class filled in for an existing character that had none
imp["characters"][1]["class"] = ""
L.import_char_lists(imp, lists)
check("missing class is filled from the game",
      imp["characters"][1]["class"] == "Маг")

# a character on another realm of the same account is a separate entry
lists2 = [{"account": "Main", "realm": "Other", "chars": [{"name": "Первый",
                                                            "class": 2}]}]
check("same name on another realm is imported separately",
      L.import_char_lists(imp, lists2) == ["Первый"])

# removing the account removes its characters and hidden marks
L.hide_character(imp, {"name": "Z", "account": "Main", "realm": "Realm"})
gone = L.remove_account(imp, "MAIN")
check("remove_account drops the whole group",
      gone >= 3 and not imp["characters"])
check("remove_account clears the hidden marks", not imp["hidden_chars"])

# ── reading the files the DLL writes ───────────────────────────────────────
wow = tempfile.mkdtemp(prefix="wowmgr_roster_")
d = os.path.join(wow, "WowManagerData")
os.makedirs(d)
with io.open(os.path.join(d, "main__0badf00d.json"), "w", encoding="utf-8") as f:
    json.dump(lists[0], f, ensure_ascii=False)
with io.open(os.path.join(d, "broken.json"), "w", encoding="utf-8") as f:
    f.write('{"account": "x", "chars": [')
with io.open(os.path.join(d, "note.txt"), "w", encoding="utf-8") as f:
    f.write("not a list")
read = L.read_char_lists(wow)
check("reader returns valid lists and skips broken files",
      len(read) == 1 and read[0]["account"] == "main")
sig1 = L.charlist_signature(wow)
check("signature sees the json files only", len(sig1) == 2)
check("signature is stable", L.charlist_signature(wow) == sig1)
check("missing folder has an empty signature",
      L.charlist_signature(os.path.join(wow, "nope")) == ())

# ── config round-trip keeps the model ─────────────────────────────────────
L.CONFIG_FILE = os.path.join(wow, "characters.json")
c2 = L._default_cfg()
c2["secret_mode"] = "plain"
c2["characters"] = [{"name": "Solo", "account": "a", "password": "pw",
                     "realm": "R", "realmlist": "l"}]
L.save_cfg(c2)
back = L.load_cfg()
check("load_cfg normalizes: account row appears",
      names(back) == [("a", ""), ("a", "Solo")])

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
