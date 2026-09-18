# -*- coding: utf-8 -*-
"""Build the real window once and poke at it: catches wiring mistakes that
pure-function tests can't (missing widgets, bad column keys, unlock flow)."""
import base64, importlib.util, io, os, sys, tempfile, time, tkinter as tk

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_gui_")
L.CONFIG_FILE = os.path.join(tmp, "characters.json")
L._config_dir = lambda: tmp
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# roster + some collected data so the summary and the new columns have content
salt = os.urandom(16)
key = L.derive_master_key("hunter22", salt)
L.set_master_key(key)
cfg = L._default_cfg()
cfg["secret_mode"] = "master"
cfg["master_salt"] = base64.b64encode(salt).decode()
cfg["master_check"] = L.master_verifier(key)
cfg["columns"] = ["class", "gs", "dailyDone", "arenaGames", "questsDone",
                  "status", "realmlist"]
cfg["characters"] = [
    {"name": "Тестомаг", "account": "acc", "password": "pw", "class": "Маг",
     "realm": "R", "realmlist": "logon.x", "totp_secret": ""},
    {"name": "Тестопал", "account": "acc", "password": "pw", "class": "Паладин",
     "realm": "R", "realmlist": "logon.x", "totp_secret": ""},
    {"name": "", "account": "second-acc", "password": "pw", "class": "",
     "realm": "R", "realmlist": "logon.y", "totp_secret": ""},
]
L.save_cfg(cfg)
L.set_master_key(None)

L.INGAME.update({
    "тестомаг": {"name": "Тестомаг", "gold": 45000000, "gs": 5400, "level": 80,
                 "played": 720000, "dailyDone": 7, "dailyMax": 25,
                 "dailyResetAt": time.time() + 3600, "questsDone": 2,
                 "questsTotal": 18, "arenaGames": 7,
                 "arenaTeams": [{"size": 2, "rating": 1580, "mine": 7}]},
    "тестопал": {"name": "Тестопал", "gold": 1200000, "gs": 5100, "level": 80,
                 "played": 300000, "dailyDone": 25, "dailyMax": 25,
                 "questsDone": 0, "questsTotal": 4},
})
L.REALM_STATUS["logon.x"] = {"ok": True, "ms": 37, "at": time.time()}
L.REALM_STATUS["logon.y"] = {"ok": False, "ms": 0, "at": time.time()}

asked = []


def fake_password(self, title, prompt, confirm_prompt=None):
    asked.append(prompt)
    return "wrong" if len(asked) == 1 else "hunter22"


L.App._ask_password = fake_password

root = tk.Tk()
root.withdraw()                      # don't flash a window across the screen
app = L.App(root)
root.update()

check("master password was asked for", len(asked) >= 1)
check("wrong password was retried", len(asked) == 2)
check("secrets unlocked", not L.SECRETS_LOCKED)
check("password decrypted", app.cfg["characters"][0]["password"] == "pw")

rows = app.tree.get_children()
check("character rows rendered", len(rows) == 2)
check("account row rendered", len(app.acc_tree.get_children()) == 1)

vals = app.tree.item(rows[0], "values")
cols = list(app._cols)
check("dailies column shows the composite",
      vals[cols.index("dailyDone")] in ("7 / 25", "25 / 25"))
check("quests column shows the composite",
      vals[cols.index("questsDone")] in ("2 / 18", "0 / 4"))
check("status column shows the ping", "37" in vals[cols.index("status")])

summary = app.summary_var.get()
check("summary totals gold across the roster",
      "4" in summary and summary != "")
check("summary names the best geared character", "Тестомаг" in summary)
check("summary includes played time", "д" in summary or "d" in summary)

# hover card for a character with all the new sections
app._show_card(app.cfg["characters"][0], 10, 10)
check("hover card built", app._card is not None)
app._hide_card()

# launching must be refused while locked
L.SECRETS_LOCKED = True
launched = []
L.launch_wow = lambda *a, **k: launched.append(a)
import tkinter.messagebox as mb
mb.showwarning = lambda *a, **k: None
L.App._relock_prompt = lambda self: None
app._launch_char(app.cfg["characters"][0])
check("locked config refuses to launch", not launched)
L.SECRETS_LOCKED = False
app._launch_char(app.cfg["characters"][0])
check("unlocked config launches", len(launched) == 1)
app._launch_char(app.cfg["characters"][0])
check("repeat launch is throttled", len(launched) == 1)

# ── the two tool dialogs must at least build ──────────────────────────────
# They are long functions nothing else executes, so a typo in one would
# otherwise only ever surface in front of a user.
wow = os.path.join(tmp, "game")
for sub in ("WTF/Account/ACC/Realm/Тестомаг", "WTF/Account/ACC/Realm/Тестопал"):
    os.makedirs(os.path.join(wow, *sub.split("/")), exist_ok=True)
with io.open(os.path.join(wow, "WTF", "Account", "ACC", "Realm", "Тестомаг",
                          "config-cache.wtf"), "w", encoding="utf-8") as fh:
    fh.write("x")
app.cfg["wow_path"] = wow

app.roster_dialog(root)
root.update()
rosters = [w for w in root.winfo_children()
           if isinstance(w, tk.Toplevel) and w.title() == L.t("Ростер")]
check("roster dialog opens", len(rosters) == 1)
if rosters:
    texts = [c for c in rosters[0].winfo_children() if isinstance(c, tk.Text)]
    check("roster dialog previews the roster",
          texts and "Тестомаг" in texts[0].get("1.0", "end"))
    rosters[0].grab_release()
    rosters[0].destroy()

app.wtf_transfer_dialog(root)
root.update()
transfers = [w for w in root.winfo_children()
             if isinstance(w, tk.Toplevel)
             and w.title() == L.t("Перенос настроек персонажа")]
check("settings-transfer dialog opens", len(transfers) == 1)
if transfers:
    boxes = [c for c in transfers[0].winfo_children()
             if isinstance(c, tk.Frame)]
    listed = []
    for b in boxes:
        listed += [c for c in b.winfo_children() if isinstance(c, tk.Listbox)]
    check("transfer dialog lists the characters found in WTF",
          listed and listed[0].size() == 2)
    transfers[0].grab_release()
    transfers[0].destroy()

root.destroy()
print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
