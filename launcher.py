#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Менеджер персонажей WOW 3.3.5a (by Zaifat)"""

import base64
import ctypes
import hashlib
import hmac
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

__version__ = "1.0"


# Bail out immediately if a debugger is attached. This is a soft anti-RE
# measure — it stops casual decompilation/inspection but won't deter someone
# determined enough to patch the binary. Wrapped in try/except so a missing
# WinAPI never crashes the launcher on non-Windows hosts.
def _antidebug():
    if sys.platform != "win32":
        return
    try:
        k = ctypes.windll.kernel32
        if k.IsDebuggerPresent():
            os._exit(0)
        present = ctypes.c_int(0)
        if k.CheckRemoteDebuggerPresent(k.GetCurrentProcess(),
                                        ctypes.byref(present)) and present.value:
            os._exit(0)
    except Exception:
        pass


_antidebug()


APP_TITLE = "Менеджер персонажей WOW 3.3.5a (by Zaifat)"
TELEGRAM_URL = "https://t.me/Zaifat"
TELEGRAM_HANDLE = "@Zaifat"
AWESOME_DLL = "AwesomeWotlkLib.dll"
PATCH_MARKER = b"AwesomeWotlkLib.dll\x00"

WOW_CLASSES = [
    "Воин", "Паладин", "Охотник", "Разбойник", "Жрец",
    "Рыцарь смерти", "Шаман", "Маг", "Чернокнижник", "Друид",
]

CLASS_COLORS = {
    "Воин": "#C79C6E",          "Паладин": "#F58CBA",
    "Охотник": "#ABD473",       "Разбойник": "#FFF569",
    "Жрец": "#CCCCCC",          "Рыцарь смерти": "#C41F3B",
    "Шаман": "#0070DE",         "Маг": "#69CCF0",
    "Чернокнижник": "#9482C9",  "Друид": "#FF7D0A",
}

REALMS_DEFAULT = [
    "WoW Circle 3.3.5a x100",
    "WoW Circle 3.3.5a x1",
    "WoW Circle 3.3.5a x4 Hardcore",
    "WoW Circle 3.3.5a Fun",
    "WoW Circle 3.3.5a x4 [MSK]",
    "WoW Circle 3.3.5a x4 [NL]",
    "WoW Circle 3.3.5a x4 [FIN]",
    "WoW Circle 3.3.5a x4 [NSK]",
    "WoW Circle 3.3.5a x4 [DE]",
    "WoW Circle 3.3.5a x100 [MSK]",
    "WoW Circle 3.3.5a x100 [NL]",
    "WoW Circle 3.3.5a x100 [FIN]",
    "WoW Circle 3.3.5a x100 [DE]",
]

REALMLISTS_DEFAULT = [
    "logon.wowcircle.com",
]

# Wow.exe binary patches that make the client load AwesomeWotlkLib.dll
_PATCHES = [
    (0x004DCCF0, bytes.fromhex("B800000000C3")),
    (0x004E5CB0, bytes.fromhex(
        "B801000000"
        "A374B4B600"
        "68E05C4E00"
        "E81C683800"
        "83C404"
        "55"
        "8BEC"
        "E8A110F2FF"
        "E9045BF2FF"
        "CCCCCCCCCCCCCCCCCCCCCCCC"
        "417765736F6D65576F746C6B4C69622E646C6C00"
    )),
    (0x0040B7D0, bytes.fromhex("E9DBA40D00909090")),
]

# ── theme ─────────────────────────────────────────────────────────────────────

BG     = "#F4F6FA"
PANEL  = "#FFFFFF"
BORDER = "#D6DCE8"
TEXT   = "#182033"
MUTED  = "#697386"
HEADER = "#182033"
ACCENT = "#D9B95E"
LINK   = "#1F6FB2"
WIN_W  = 880
WIN_H  = 560


# ── paths ─────────────────────────────────────────────────────────────────────

def _bundled(name):
    """Locate a bundled resource (works for PyInstaller, Nuitka, dev mode)."""
    bases = []
    if hasattr(sys, "_MEIPASS"):                       # PyInstaller onefile
        bases.append(sys._MEIPASS)
    try:
        bases.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        bases.append(os.path.dirname(os.path.abspath(sys.executable)))
        bases.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    for base in bases:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(bases[0] if bases else ".", name)


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_dir():
    """Per-user config directory (hidden from the exe folder)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    d = os.path.join(base, "АвтологинWOW")
    os.makedirs(d, exist_ok=True)
    return d


CONFIG_FILE = os.path.join(_config_dir(), "characters.json")


def _migrate_legacy_config():
    """Move old characters.json from next to the exe into AppData if needed."""
    old = os.path.join(_app_dir(), "characters.json")
    if os.path.isfile(old) and not os.path.isfile(CONFIG_FILE):
        try:
            shutil.move(old, CONFIG_FILE)
        except OSError:
            pass


_migrate_legacy_config()


# ── config ────────────────────────────────────────────────────────────────────

def _default_cfg():
    return {
        "wow_path":   r"E:\WOW",
        "realmlist":  REALMLISTS_DEFAULT[0],
        "realms":     list(REALMS_DEFAULT),
        "realmlists": list(REALMLISTS_DEFAULT),
        "characters": [],
    }


def load_cfg():
    if not os.path.exists(CONFIG_FILE):
        cfg = _default_cfg()
        save_cfg(cfg)
        return cfg
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    for k, v in _default_cfg().items():
        cfg.setdefault(k, v)
    # ensure lists exist as lists
    if not isinstance(cfg.get("realms"), list) or not cfg["realms"]:
        cfg["realms"] = list(REALMS_DEFAULT)
    if not isinstance(cfg.get("realmlists"), list) or not cfg["realmlists"]:
        cfg["realmlists"] = list(REALMLISTS_DEFAULT)
    return cfg


def save_cfg(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


# ── AwesomeWotlk auto-deploy ──────────────────────────────────────────────────

def _va_to_file_offset(image, va):
    e_lfanew = struct.unpack_from("<I", image, 0x3C)[0]
    if image[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("Не PE-файл")
    num_sections = struct.unpack_from("<H", image, e_lfanew + 6)[0]
    size_opt_header = struct.unpack_from("<H", image, e_lfanew + 20)[0]
    opt_off = e_lfanew + 24
    image_base = struct.unpack_from("<I", image, opt_off + 28)[0]
    rva = va - image_base
    sections_off = opt_off + size_opt_header
    for i in range(num_sections):
        s = sections_off + i * 40
        v_size = struct.unpack_from("<I", image, s + 8)[0]
        v_addr = struct.unpack_from("<I", image, s + 12)[0]
        r_size = struct.unpack_from("<I", image, s + 16)[0]
        r_ptr  = struct.unpack_from("<I", image, s + 20)[0]
        if v_addr <= rva < v_addr + max(v_size, r_size):
            return r_ptr + (rva - v_addr)
    raise ValueError(f"VA 0x{va:08X} не найден в секциях PE")


def is_wow_patched(wow_exe):
    try:
        with open(wow_exe, "rb") as f:
            return PATCH_MARKER in f.read()
    except OSError:
        return False


def patch_wow_exe(wow_exe):
    with open(wow_exe, "rb") as f:
        image = bytearray(f.read())
    for va, payload in _PATCHES:
        offset = _va_to_file_offset(bytes(image), va)
        image[offset:offset + len(payload)] = payload
    backup = wow_exe + ".unpatched.bak"
    if not os.path.exists(backup):
        shutil.copy2(wow_exe, backup)
    with open(wow_exe, "wb") as f:
        f.write(image)


def deploy_patch(wow_dir):
    src_dll = _bundled(AWESOME_DLL)
    if not os.path.isfile(src_dll):
        raise RuntimeError(f"В программу не зашит {AWESOME_DLL}")
    dst_dll = os.path.join(wow_dir, AWESOME_DLL)
    if (not os.path.isfile(dst_dll)
            or os.path.getsize(dst_dll) != os.path.getsize(src_dll)):
        shutil.copy2(src_dll, dst_dll)
    wow_exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(wow_exe):
        raise RuntimeError(f"Не найден Wow.exe в {wow_dir}")
    if not is_wow_patched(wow_exe):
        patch_wow_exe(wow_exe)


def update_realmlist(wow_dir, realmlist):
    with open(os.path.join(wow_dir, "realmlist.wtf"), "w", encoding="ascii") as f:
        f.write(f"set realmlist {realmlist}\n")


def normalize_totp_secret(s):
    if not s:
        return ""
    s = s.strip().upper().replace(" ", "").replace("-", "")
    if s.startswith("OTPAUTH://"):
        # Take everything after secret= until next & or end
        i = s.find("SECRET=")
        if i >= 0:
            tail = s[i + 7:]
            j = tail.find("&")
            s = tail if j < 0 else tail[:j]
    return s


def compute_totp(secret, t=None, digits=6, period=30):
    """RFC 6238 TOTP. Returns 6-digit code or '' on bad input."""
    secret = normalize_totp_secret(secret)
    if not secret:
        return ""
    pad = (-len(secret)) % 8
    if pad:
        secret += "=" * pad
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return ""
    if not key:
        return ""
    if t is None:
        t = time.time()
    counter = int(t // period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def launch_wow(cfg, char):
    wow_dir = cfg.get("wow_path", "")
    exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(f"Wow.exe не найден:\n{exe}")

    realmlist = (char.get("realmlist") or cfg.get("realmlist")
                 or REALMLISTS_DEFAULT[0])

    deploy_patch(wow_dir)
    update_realmlist(wow_dir, realmlist)

    args = [
        exe,
        "-login",     char.get("account", ""),
        "-password",  char.get("password", ""),
        "-realmlist", realmlist,
        "-realmname", char.get("realm", ""),
        "-character", char.get("name", ""),
    ]

    secret = char.get("totp_secret", "")
    if secret:
        code = compute_totp(secret)
        if code:
            args += ["-token", code]

    subprocess.Popen(args, cwd=wow_dir)


# ── helpers ───────────────────────────────────────────────────────────────────

def _tint(hex_color, alpha=0.18):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return "#{:02X}{:02X}{:02X}".format(
        int(r * alpha + 255 * (1 - alpha)),
        int(g * alpha + 255 * (1 - alpha)),
        int(b * alpha + 255 * (1 - alpha)))


def _hyperlink(parent, text, url, bg=None, **kw):
    lbl = tk.Label(parent, text=text, fg=LINK, cursor="hand2",
                   bg=bg if bg else parent["bg"],
                   font=("Segoe UI", 9, "underline"), **kw)
    lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return lbl


def _make_entry(parent, var, show=None):
    e = tk.Entry(parent, textvariable=var, show=show, bg=PANEL, fg=TEXT,
                 relief="flat", highlightthickness=1)
    e.configure(highlightbackground=BORDER, highlightcolor=ACCENT,
                insertbackground=TEXT, font=("Segoe UI", 10))
    return e


# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.search_var = tk.StringVar()
        self.count_var  = tk.StringVar()
        root.title(APP_TITLE)
        root.geometry(f"{WIN_W}x{WIN_H}")
        root.minsize(780, 480)
        root.configure(bg=BG)
        self.build()

    def build(self):
        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(toolbar, text="Поиск", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        search = _make_entry(toolbar, self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(8, 12), ipady=6)
        search.bind("<KeyRelease>", lambda _e: self.render_rows())

        tk.Button(toolbar, text="Добавить", bg=HEADER, fg=ACCENT, relief="flat",
                  padx=14, pady=7, command=self.add_char
                  ).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Изменить", bg="#E2E6EF", fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.edit_selected
                  ).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Удалить", bg="#E2E6EF", fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.delete_selected
                  ).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Настройки", bg="#E2E6EF", fg=TEXT,
                  relief="flat", padx=14, pady=7, command=self.settings
                  ).pack(side="right")

        table_wrap = tk.Frame(self.root, bg=PANEL,
                              highlightbackground=BORDER, highlightthickness=1)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        cols = ("name", "class", "gs", "account", "realm", "realmlist")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                                 selectmode="browse")
        self.tree.heading("name",      text="Персонаж")
        self.tree.heading("class",     text="Класс")
        self.tree.heading("gs",        text="ГС")
        self.tree.heading("account",   text="Аккаунт")
        self.tree.heading("realm",     text="Реалм")
        self.tree.heading("realmlist", text="Realmlist")
        self.tree.column("name",      width=140, anchor="w")
        self.tree.column("class",     width=110, anchor="w")
        self.tree.column("gs",        width=60,  anchor="center")
        self.tree.column("account",   width=110, anchor="w")
        self.tree.column("realm",     width=210, anchor="w")
        self.tree.column("realmlist", width=160, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.launch_selected())
        self.tree.bind("<Return>",   lambda _e: self.launch_selected())

        # class-based row tinting
        for cls, color in CLASS_COLORS.items():
            self.tree.tag_configure(f"cls_{cls}",
                                    background=_tint(color, 0.20))

        sb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        # ── footer ────────────────────────────────────────────────────────────
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(bottom, textvariable=self.count_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        tk.Label(bottom, text="    •    Отблагодарить:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        _hyperlink(bottom, TELEGRAM_HANDLE, TELEGRAM_URL, bg=BG
                   ).pack(side="left", padx=(2, 0))

        tk.Button(bottom, text="Запустить выбранного", bg=ACCENT, fg="#171717",
                  relief="flat", padx=18, pady=8,
                  command=self.launch_selected).pack(side="right")

        self.render_rows()

    def filtered(self):
        q = self.search_var.get().strip().lower()
        items = list(enumerate(self.cfg.get("characters", [])))
        if not q:
            return items
        out = []
        for i, c in items:
            hay = " ".join(str(c.get(k, ""))
                           for k in ("name", "class", "gs", "account", "realm",
                                     "realmlist")).lower()
            if q in hay:
                out.append((i, c))
        return out

    def render_rows(self):
        for it in self.tree.get_children():
            self.tree.delete(it)
        for idx, c in self.filtered():
            tag = f"cls_{c.get('class', '')}"
            self.tree.insert("", "end", iid=str(idx), values=(
                c.get("name", ""), c.get("class", ""),
                c.get("gs", ""), c.get("account", ""),
                c.get("realm", ""), c.get("realmlist", "")), tags=(tag,))
        self.count_var.set(f"Персонажей: {len(self.cfg.get('characters', []))}")

    def selected_idx(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Выбери персонажа в списке.")
            return None
        return int(sel[0])

    def launch_selected(self):
        idx = self.selected_idx()
        if idx is None:
            return
        char = self.cfg["characters"][idx]
        try:
            launch_wow(self.cfg, char)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def delete_selected(self):
        idx = self.selected_idx()
        if idx is None:
            return
        name = self.cfg["characters"][idx].get("name", "?")
        if messagebox.askyesno(APP_TITLE, f"Удалить «{name}»?"):
            self.cfg["characters"].pop(idx)
            save_cfg(self.cfg)
            self.render_rows()

    def edit_selected(self):
        idx = self.selected_idx()
        if idx is not None:
            self.character_dialog(idx)

    def add_char(self):
        self.character_dialog(None)

    # ── character dialog ──────────────────────────────────────────────────────

    def character_dialog(self, idx):
        editing = idx is not None
        if editing:
            char = self.cfg["characters"][idx]
        else:
            # remember last entered fields (skip name)
            chars = self.cfg.get("characters", [])
            char = ({k: v for k, v in chars[-1].items() if k != "name"}
                    if chars else {})

        dlg = tk.Toplevel(self.root)
        dlg.title("Персонаж")
        dlg.geometry("440x690")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text="Персонаж", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")
                 ).pack(padx=20, pady=(18, 10), anchor="w")

        name_var      = tk.StringVar(value=char.get("name", ""))
        account_var   = tk.StringVar(value=char.get("account", ""))
        password_var  = tk.StringVar(value=char.get("password", ""))
        class_var     = tk.StringVar(value=char.get("class", "Паладин"))
        gs_var        = tk.StringVar(value=str(char.get("gs", "")))
        realm_var     = tk.StringVar(value=char.get("realm",
                                          self.cfg["realms"][0]))
        realmlist_var = tk.StringVar(value=char.get("realmlist",
                                          self.cfg["realmlists"][0]))
        totp_var      = tk.StringVar(value=char.get("totp_secret", ""))

        def field(label, var, show=None):
            tk.Label(dlg, text=label, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9)
                     ).pack(fill="x", padx=20, pady=(8, 0))
            ent = _make_entry(dlg, var, show=show)
            ent.pack(fill="x", padx=20, ipady=5)
            return ent

        first = field("Ник персонажа",  name_var)
        field("Логин аккаунта", account_var)
        field("Пароль",         password_var, show="●")

        tk.Label(dlg, text="Класс", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=class_var, values=WOW_CLASSES,
                     state="readonly", font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        field("ГС (Gear Score)", gs_var)

        tk.Label(dlg, text="Реалм", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=realm_var, values=self.cfg["realms"],
                     font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        tk.Label(dlg, text="Realmlist", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=realmlist_var,
                     values=self.cfg["realmlists"], font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        # 2FA
        tk.Label(dlg,
                 text="Секрет 2FA (Google / 2FAS Auth / Yandex Authenticator)",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(10, 0))
        totp_row = tk.Frame(dlg, bg=BG)
        totp_row.pack(fill="x", padx=20)
        _make_entry(totp_row, totp_var).pack(side="left", fill="x",
                                             expand=True, ipady=5)
        totp_check_var = tk.StringVar(value="")
        check_lbl = tk.Label(totp_row, textvariable=totp_check_var, bg=BG,
                             fg=MUTED, font=("Segoe UI", 9, "bold"), width=8)
        check_lbl.pack(side="left", padx=(8, 0))
        tk.Label(dlg, text="Если 2FA не подключена — оставь пусто.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)
                 ).pack(fill="x", padx=20, pady=(2, 0))

        def refresh_code(*_):
            secret = totp_var.get().strip()
            if not secret:
                totp_check_var.set("")
                return
            code = compute_totp(secret)
            totp_check_var.set(code if code else "невалидно")
        totp_var.trace_add("write", refresh_code)
        refresh_code()

        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning(APP_TITLE, "Введи ник персонажа.",
                                       parent=dlg)
                return
            item = {
                "name":        name,
                "account":     account_var.get().strip(),
                "password":    password_var.get(),
                "class":       class_var.get().strip(),
                "gs":          gs_var.get().strip(),
                "realm":       realm_var.get().strip(),
                "realmlist":   realmlist_var.get().strip(),
                "totp_secret": totp_var.get().strip(),
            }
            if editing:
                self.cfg["characters"][idx] = item
            else:
                self.cfg.setdefault("characters", []).append(item)
            save_cfg(self.cfg)
            self.render_rows()
            dlg.destroy()

        tk.Button(dlg, text="Сохранить" if editing else "Добавить",
                  bg=HEADER, fg=ACCENT, relief="flat", pady=9, cursor="hand2",
                  command=save
                  ).pack(fill="x", padx=20, pady=18)

        first.focus_set()

    # ── settings dialog ───────────────────────────────────────────────────────

    def settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Настройки")
        dlg.geometry("540x650")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text="Настройки", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")
                 ).pack(padx=20, pady=(18, 10), anchor="w")

        # WoW path
        tk.Label(dlg, text="Папка с Wow.exe", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20)
        path_var = tk.StringVar(value=self.cfg.get("wow_path", ""))
        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=20, pady=(4, 12))
        _make_entry(row, path_var).pack(side="left", fill="x", expand=True,
                                        ipady=5)

        def browse():
            p = filedialog.askopenfilename(
                parent=dlg, title="Выбери Wow.exe",
                filetypes=[("WoW Client", "Wow.exe"),
                           ("Exe", "*.exe"), ("All", "*.*")])
            if p:
                path_var.set(os.path.normpath(os.path.dirname(p)))

        tk.Button(row, text="Обзор", bg="#E2E6EF", fg=TEXT, relief="flat",
                  padx=10, command=browse
                  ).pack(side="left", padx=(8, 0), ipady=5)

        # Realms list
        tk.Label(dlg, text="Список реалмов (по строке на реалм)", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=20,
                                                     pady=(4, 0))
        realms_text = tk.Text(dlg, height=8, bg=PANEL, fg=TEXT, relief="flat",
                              highlightthickness=1, font=("Segoe UI", 10),
                              wrap="none")
        realms_text.configure(highlightbackground=BORDER,
                              highlightcolor=ACCENT, insertbackground=TEXT)
        realms_text.insert("1.0", "\n".join(self.cfg.get("realms", [])))
        realms_text.pack(fill="x", padx=20, pady=(2, 12))

        # Realmlists
        tk.Label(dlg, text="Список realmlist-серверов (по строке)", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=20)
        realmlists_text = tk.Text(dlg, height=4, bg=PANEL, fg=TEXT,
                                  relief="flat", highlightthickness=1,
                                  font=("Segoe UI", 10), wrap="none")
        realmlists_text.configure(highlightbackground=BORDER,
                                  highlightcolor=ACCENT, insertbackground=TEXT)
        realmlists_text.insert("1.0", "\n".join(self.cfg.get("realmlists", [])))
        realmlists_text.pack(fill="x", padx=20, pady=(2, 12))

        def lines(widget):
            raw = widget.get("1.0", "end")
            return [ln.strip() for ln in raw.split("\n") if ln.strip()]

        def reload_settings_dialog():
            dlg.destroy()
            self.settings()

        # ── Config management buttons ────────────────────────────────────────
        tk.Label(dlg, text="Конфиг", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(4, 0))
        cfg_row = tk.Frame(dlg, bg=BG)
        cfg_row.pack(fill="x", padx=20, pady=(2, 0))

        def load_config():
            p = filedialog.askopenfilename(
                parent=dlg, title="Загрузить конфиг",
                filetypes=[("JSON", "*.json"), ("Все", "*.*")])
            if not p:
                return
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    new_cfg = json.load(fh)
                if not isinstance(new_cfg, dict):
                    raise ValueError("файл не содержит объект конфига")
            except Exception as e:
                messagebox.showerror(APP_TITLE,
                                     f"Не удалось прочитать конфиг:\n{e}",
                                     parent=dlg)
                return
            for k, v in _default_cfg().items():
                new_cfg.setdefault(k, v)
            self.cfg = new_cfg
            save_cfg(self.cfg)
            self.render_rows()
            messagebox.showinfo(APP_TITLE,
                                f"Загружено персонажей: "
                                f"{len(self.cfg.get('characters', []))}",
                                parent=dlg)
            reload_settings_dialog()

        def download_config():
            p = filedialog.asksaveasfilename(
                parent=dlg, title="Сохранить конфиг как…",
                initialfile="wow_autologin_config.json",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("Все", "*.*")])
            if not p:
                return
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
                messagebox.showinfo(APP_TITLE, f"Сохранено:\n{p}", parent=dlg)
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e), parent=dlg)

        def clear_config():
            if not messagebox.askyesno(
                    APP_TITLE,
                    "Очистить весь конфиг?\nВсе персонажи и настройки будут "
                    "удалены безвозвратно.",
                    parent=dlg):
                return
            self.cfg = _default_cfg()
            save_cfg(self.cfg)
            self.render_rows()
            reload_settings_dialog()

        tk.Button(cfg_row, text="Загрузить", bg="#E2E6EF", fg=TEXT,
                  relief="flat", padx=10, pady=6, command=load_config
                  ).pack(side="left", padx=(0, 6))
        tk.Button(cfg_row, text="Скачать", bg="#E2E6EF", fg=TEXT,
                  relief="flat", padx=10, pady=6, command=download_config
                  ).pack(side="left", padx=(0, 6))
        tk.Button(cfg_row, text="Очистить", bg="#FBE5E7", fg="#9A2730",
                  relief="flat", padx=10, pady=6, command=clear_config
                  ).pack(side="left", padx=(0, 6))

        def save():
            self.cfg["wow_path"]   = path_var.get().strip()
            realms_new = lines(realms_text)
            realmlists_new = lines(realmlists_text)
            if realms_new:
                self.cfg["realms"] = realms_new
            if realmlists_new:
                self.cfg["realmlists"] = realmlists_new
                if self.cfg.get("realmlist") not in realmlists_new:
                    self.cfg["realmlist"] = realmlists_new[0]
            save_cfg(self.cfg)
            self.render_rows()
            dlg.destroy()

        tk.Button(dlg, text="Сохранить", bg=HEADER, fg=ACCENT, relief="flat",
                  pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(12, 14))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
