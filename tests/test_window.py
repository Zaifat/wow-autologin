# -*- coding: utf-8 -*-
"""Build the real window and drive it: the account -> characters tree, the
dialogs, search, drag reorder, deletion, the automatic character import and
the master-password unlock. Catches wiring mistakes pure-function tests can't.
"""
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


# ── a legacy flat config in master-password mode ───────────────────────────
salt = os.urandom(16)
key = L.derive_master_key("hunter22", salt)
L.set_master_key(key)
cfg = L._default_cfg()
cfg["secret_mode"] = "master"
cfg["master_salt"] = base64.b64encode(salt).decode()
cfg["master_check"] = L.master_verifier(key)
cfg["wow_path"] = tmp
cfg["columns"] = ["class", "gs", "dailyDone", "questsDone", "gold",
                  "realmlist"]
cfg["characters"] = [
    {"name": "Тестомаг", "account": "acc", "password": "pw", "class": "Маг",
     "realm": "R", "realmlist": "logon.x", "totp_secret": ""},
    {"name": "Тестопал", "account": "acc", "password": "pw", "class": "Паладин",
     "realm": "R", "realmlist": "logon.x", "totp_secret": ""},
    {"name": "", "account": "second-acc", "password": "pw2", "class": "",
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

asked = []


def fake_password(self, title, prompt, confirm_prompt=None):
    asked.append(prompt)
    return "wrong" if len(asked) == 1 else "hunter22"


L.App._ask_password = fake_password
L.App._start_background_checks = lambda self: None
L.App._setup_tray = lambda self: None
import tkinter.messagebox as mb
mb.askyesno = lambda *a, **k: True
mb.showwarning = lambda *a, **k: None
mb.showinfo = lambda *a, **k: None
mb.showerror = lambda *a, **k: None

root = tk.Tk()
root.withdraw()
app = L.App(root)
root.update()
tree = app.tree
E = lambda: app.cfg["characters"]

# ── unlock ─────────────────────────────────────────────────────────────────
check("master password was asked for", len(asked) >= 1)
check("wrong password was retried", len(asked) == 2)
check("secrets unlocked", not L.SECRETS_LOCKED)
check("password decrypted onto the account row", E()[0]["password"] == "pw")

# ── one tree: accounts with their characters ──────────────────────────────
tops = tree.get_children("")
check("one top-level row per account", len(tops) == 2)
check("legacy characters were grouped under a created account row",
      L.is_account_entry(E()[int(tops[0])])
      and [tree.item(c, "text") for c in tree.get_children(tops[0])]
      == ["Тестомаг", "Тестопал"])
check("account label shows the login", "acc" in tree.item(tops[0], "text"))
check("empty account says it waits for the first login",
      not tree.get_children(tops[1]))

cols = list(app._cols)
acc_vals = tree.item(tops[0], "values")
char_vals = tree.item(tree.get_children(tops[0])[0], "values")
check("account row totals the gold of its characters",
      acc_vals[cols.index("gold")] != "")
check("dailies composite on a character row",
      char_vals[cols.index("dailyDone")] == "7 / 25")
check("name column is the tree column, not a data column", "name" not in cols)

check("the version is shown in the title", L.__version__ in root.title())
labels = []


def walk_labels(w):
    for c in w.winfo_children():
        if isinstance(c, tk.Label):
            labels.append(c.cget("text"))
        walk_labels(c)


walk_labels(root)
check("the version is shown in the window",
      any("v" + L.__version__ == x for x in labels))

# ── summary chips ─────────────────────────────────────────────────────────
chips = [w for w in app._chips.winfo_children()]
check("summary chips rendered", len(chips) >= 4)
check("summary names the best geared character", "Тестомаг" in app.summary_var.get())

# ── selection drives the toolbar ──────────────────────────────────────────
tree.selection_set(())
root.update()
check("no selection -> Edit disabled", not app._btn_edit.enabled)
tree.selection_set(tree.get_children(tops[0])[0])
root.update()
check("selection -> Edit enabled", app._btn_edit.enabled)

# ── search ────────────────────────────────────────────────────────────────
app.search_var.set("тестопал")
root.update()
tops_q = tree.get_children("")
check("search keeps only the matching account",
      len(tops_q) == 1 and len(tree.get_children(tops_q[0])) == 1)
app.search_var.set("second")
root.update()
check("search on a login shows that account", len(tree.get_children("")) == 1)
app.search_var.set("")
root.update()

# ── launching ─────────────────────────────────────────────────────────────
launched = []
L.launch_wow = lambda cfg, ch, **k: launched.append(ch.get("name") or ch["account"])
L.App._relock_prompt = lambda self: None
L.SECRETS_LOCKED = True
app._launch_char(E()[1])
check("locked config refuses to launch", not launched)
L.SECRETS_LOCKED = False
app._launch_char(E()[1])
check("unlocked config launches", launched == ["Тестомаг"])
app._launch_char(E()[1])
check("repeat launch is throttled", len(launched) == 1)
check("launch goes out with the account password", E()[1]["password"] == "pw")


def find_buttons(widget):
    out = []
    for w in widget.winfo_children():
        if isinstance(w, L.FlatButton):
            out.append(w)
        out += find_buttons(w)
    return out


def last_dialog():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]


def entries_of(dlg):
    found = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Entry) and not isinstance(c, L.ttk.Combobox):
                found.append(c)
            walk(c)
    walk(dlg)
    return found


def type_into(entry, text):
    entry.delete(0, "end")
    entry.insert(0, text)


# ── add an account through its dialog ─────────────────────────────────────
app.account_dialog(None)
root.update()
dlg = last_dialog()
ents = entries_of(dlg)
type_into(ents[0], "fresh")          # login
type_into(ents[1], "s3cret")         # password
find_buttons(dlg)[-1].command()
root.update()
fresh = L.account_entry_for(app.cfg, "fresh")
check("account dialog adds an account row", fresh is not None
      and fresh["password"] == "s3cret")
check("new account shows up in the tree", str(E().index(fresh)) in tree.get_children(""))
check("a banner offers to log in", "new_account" in app._banners)

# duplicate login is refused
app.account_dialog(None)
root.update()
dlg = last_dialog()
type_into(entries_of(dlg)[0], "FRESH")
find_buttons(dlg)[-1].command()
root.update()
check("duplicate login is refused",
      sum(1 for e in E() if L.acc_key(e.get("account")) == "fresh") == 1)
dlg.destroy()

# ── characters come from the game; the dialog only edits them ────────────
check("no manual add-character entry point",
      not hasattr(app, "add_character"))
check("collecting characters is off until the user asks",
      L._default_cfg()["auto_import_chars"] is False)
# ── badges: the row image is built even without a game client ─────────────
badge = L.row_badge("Маг", "BloodElf", "female")
check("a character row gets a race + class badge",
      badge is not None and badge.width() > badge.height())
check("badges are cached instead of rebuilt",
      L.row_badge("Маг", "BloodElf", "female") is badge)
check("a row with neither class nor race has no badge",
      L.row_badge("", "", "") is None)
check("class rows are tinted with their colour",
      L.class_row_tint("Маг") != L.PANEL and L.class_row_tint("") == L.PANEL)
app.cfg["auto_import_chars"] = True
app._import_char_lists([{"account": "fresh", "realm": "R",
                         "chars": [{"name": "Ручной", "class": 8}]}])
root.update()
manual = next((e for e in E() if e.get("name") == "Ручной"), None)
check("the imported character appears", manual is not None)
check("the character inherits the account password",
      manual and manual["password"] == "s3cret")
check("the character sits right under its account",
      manual and E().index(manual) == E().index(fresh) + 1)
app.char_dialog(E().index(manual))
root.update()
dlg = last_dialog()
type_into(entries_of(dlg)[0], "Переименован")
find_buttons(dlg)[-1].command()
root.update()
manual = next((e for e in E() if e.get("name") == "Переименован"), None)
check("the character dialog saves an edit", manual is not None)

# ── editing the account password flows to its characters ─────────────────
app.account_dialog(E().index(fresh))
root.update()
dlg = last_dialog()
type_into(entries_of(dlg)[1], "n3w")
find_buttons(dlg)[-1].command()
root.update()
check("changing the account password updates its characters",
      manual["password"] == "n3w")

# ── automatic import from the game ────────────────────────────────────────
app._import_char_lists([{"account": "second-acc", "realm": "R", "chars": [
    {"name": "Авто1", "class": 5}, {"name": "Авто2", "class": 9}]}])
root.update()
second = L.account_entry_for(app.cfg, "second-acc")
kids = [tree.item(c, "text") for c in tree.get_children(str(E().index(second)))]
check("imported characters appear under their account", kids == ["Авто1", "Авто2"])
check("import shows a banner", "imported" in app._banners)
auto1 = next(e for e in E() if e.get("name") == "Авто1")
check("imported character got the account password", auto1["password"] == "pw2")

# ── the roster import can be switched off ─────────────────────────────────
app.cfg["auto_import_chars"] = False
app._import_char_lists([{"account": "second-acc", "realm": "R",
                         "chars": [{"name": "Нежданный", "class": 1}]}])
check("nothing is imported while the switch is off",
      not any(e.get("name") == "Нежданный" for e in E()))
app.cfg["auto_import_chars"] = True

# ── deleting a character hides it from the next import ────────────────────
tree.selection_set(str(E().index(auto1)))
app.delete_selected()
root.update()
check("character deleted", not any(e.get("name") == "Авто1" for e in E()))
app._import_char_lists([{"account": "second-acc", "realm": "R", "chars": [
    {"name": "Авто1", "class": 5}]}])
check("deleted character is not re-imported",
      not any(e.get("name") == "Авто1" for e in E()))

# ── folding an account is remembered; double-click launches it ───────────
acc_row = str(E().index(L.account_entry_for(app.cfg, "acc")))
tree.item(acc_row, open=False)
tree.focus(acc_row)
app._on_fold(False)
check("a folded account is recorded",
      "acc" in (app.cfg.get("collapsed_accounts") or []))
app.render_rows()
root.update()
acc_row = str(E().index(L.account_entry_for(app.cfg, "acc")))
check("...and stays folded after a redraw", not tree.item(acc_row, "open"))
check("the folded state survives a reload",
      "acc" in (L.load_cfg().get("collapsed_accounts") or []))
tree.focus(acc_row)
app._on_fold(True)
app.render_rows()
root.update()
acc_row = str(E().index(L.account_entry_for(app.cfg, "acc")))
check("unfolding is recorded too",
      "acc" not in (app.cfg.get("collapsed_accounts") or [])
      and tree.item(acc_row, "open"))

launched.clear()
app._last_launch.clear()


class FakeClick:
    def __init__(self, iid, indicator=False):
        box = tree.bbox(iid)
        self.x = 12 if indicator else (box[0] + box[2] - 10 if box else 200)
        self.y = (box[1] + 2) if box else 10


tree.selection_set(acc_row)
res = app._on_double(FakeClick(acc_row))
check("double-click on an account row launches it",
      launched == ["acc"] and res == "break")

# ── sorting from the footer ───────────────────────────────────────────────
opts = dict((lbl, key) for key, lbl in app.sort_options())
check("the sort picker offers manual order and the columns",
      "" in opts.values() and "gs" in opts.values() and "name" in opts.values())
app._sort_var.set(next(lbl for lbl, key in opts.items() if key == "gs"))
app._on_sort_pick()
root.update()
acc_iid = str(E().index(L.account_entry_for(app.cfg, "acc")))
names_sorted = [tree.item(c, "text") for c in tree.get_children(acc_iid)]
check("sorting by GS orders the characters",
      names_sorted == ["Тестопал", "Тестомаг"])
check("the chosen sort is saved", L.load_cfg().get("sort", {}).get("col") == "gs")
app._toggle_sort_dir()
root.update()
check("the direction flips",
      [tree.item(c, "text") for c in tree.get_children(acc_iid)]
      == ["Тестомаг", "Тестопал"]
      and L.load_cfg().get("sort", {}).get("reverse") is True)

# ── drag reorder: a character within its account ──────────────────────────
acc_iid = str(E().index(L.account_entry_for(app.cfg, "acc")))
first, second_row = tree.get_children(acc_iid)
app._drag = {"iid": second_row, "moved": False}
tree.move(second_row, acc_iid, 0)
app._drag["moved"] = True
app._on_drag_drop(None)
root.update()
acc_idx = int(str(E().index(L.account_entry_for(app.cfg, "acc"))))
check("dragging switches back to the manual order",
      not (app.cfg.get("sort") or {}).get("col"))
check("drag reorders characters inside the account",
      [E()[acc_idx + 1]["name"], E()[acc_idx + 2]["name"]]
      == ["Тестопал", "Тестомаг"])

# ...and an account among accounts, dragging its characters along
tops = tree.get_children("")
app._drag = {"iid": tops[-1], "moved": True}
tree.move(tops[-1], "", 0)
app._on_drag_drop(None)
root.update()
check("drag moves a whole account with its characters",
      L.is_account_entry(E()[0]) and E()[0]["account"] == "fresh"
      and E()[1]["name"] == "Переименован")

# ── deleting an account removes its characters ────────────────────────────
tree.selection_set(str(E().index(L.account_entry_for(app.cfg, "fresh"))))
app.delete_selected()
root.update()
check("account and its characters deleted",
      not any(L.acc_key(e.get("account")) == "fresh" for e in E()))

# ── everything survives a save / reload ───────────────────────────────────
reloaded = L.load_cfg()
check("config reloads grouped and complete",
      [(e["account"], e.get("name")) for e in reloaded["characters"]]
      == [(e["account"], e.get("name")) for e in E()])

# ── hover card, tool dialogs ───────────────────────────────────────────────
app._show_card(E()[1], 10, 10)
check("hover card built", app._card is not None)
app._hide_card()

wow = os.path.join(tmp, "game")
for sub in ("WTF/Account/ACC/Realm/Тестомаг", "WTF/Account/ACC/Realm/Тестопал"):
    os.makedirs(os.path.join(wow, *sub.split("/")), exist_ok=True)
app.cfg["wow_path"] = wow
app.roster_dialog(root)
root.update()
rosters = [w for w in root.winfo_children()
           if isinstance(w, tk.Toplevel) and w.title() == L.t("Ростер")]
check("roster dialog opens", len(rosters) == 1)
for w in rosters:
    w.destroy()
app.wtf_transfer_dialog(root)
root.update()
transfers = [w for w in root.winfo_children()
             if isinstance(w, tk.Toplevel)
             and w.title() == L.t("Перенос настроек персонажа")]
check("settings-transfer dialog opens", len(transfers) == 1)
for w in transfers:
    w.destroy()

# the settings dialog itself still builds with the new model
app.settings()
root.update()
check("settings dialog opens", any(isinstance(w, tk.Toplevel)
                                   for w in root.winfo_children()))

# ── graphics preset builder ───────────────────────────────────────────────
app.graphics_constructor(root)
root.update()
gfx = [w for w in root.winfo_children()
       if isinstance(w, tk.Toplevel) and w.title() == L.t("Конструктор графики")][-1]
boxes = []


def walk(w):
    for c in w.winfo_children():
        if isinstance(c, tk.Listbox):
            boxes.append(c)
        walk(c)


walk(gfx)
check("builder lists the built-in presets", boxes and boxes[0].size() == 2)
def find_tk_buttons(w, out):
    for c in w.winfo_children():
        if isinstance(c, tk.Button):
            out[c.cget("text")] = c
        find_tk_buttons(c, out)
    return out


tkb = find_tk_buttons(gfx, {})
tkb[L.t("Копия")].invoke()               # copy the selected built-in
root.update()
presets = L.user_presets(app.cfg)
check("copy creates an editable preset", len(presets) == 1)
copied = list(presets)[0]
check("the copy carries the built-in's settings",
      presets[copied]["cvars"] == L.GRAPHICS_PRESETS["light"])
check("the list now shows three presets", boxes[0].size() == 3)

tkb[L.t("Новый")].invoke()
root.update()
check("a second preset gets its own key", len(L.user_presets(app.cfg)) == 2)
mb.askyesno = lambda *a, **k: True
tkb[L.t("Удалить")].invoke()
root.update()
check("delete removes the selected preset", len(L.user_presets(app.cfg)) == 1)
for b in find_buttons(gfx):
    b.command()                           # "Готово" saves and closes
root.update()
check("builder closes and saves",
      not any(isinstance(w, tk.Toplevel)
              and w.title() == L.t("Конструктор графики")
              for w in root.winfo_children()))
check("the preset survives a reload",
      L.user_presets(L.load_cfg()) == L.user_presets(app.cfg))

# the account dialog offers it
app.account_dialog(E().index(L.account_entry_for(app.cfg, "acc")))
root.update()
adlg = last_dialog()
combos = []


def walk_combo(w):
    for c in w.winfo_children():
        if isinstance(c, L.ttk.Combobox):
            combos.append(c)
        walk_combo(c)


walk_combo(adlg)
values = [v for cb in combos for v in cb.cget("values")]
check("the account picker lists the custom preset",
      any(L.preset_label(app.cfg, list(L.user_presets(app.cfg))[0]) == v
          for v in values))
adlg.destroy()

# ── theme switch rebuilds cleanly ─────────────────────────────────────────
for w in root.winfo_children():
    if isinstance(w, tk.Toplevel):
        w.destroy()
for theme in ("light", "wow", "dark"):
    L.apply_theme(theme)
    app.rebuild()
    root.update()
check("every theme rebuilds the window", app.tree.winfo_exists())

root.destroy()
print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
