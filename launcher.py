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
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

__version__ = "1.3.4"


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

THEMES = {
    "light": dict(BG="#F4F6FA", PANEL="#FFFFFF", BORDER="#D6DCE8",
                  TEXT="#182033", MUTED="#697386", HEADER="#182033",
                  ACCENT="#D9B95E", LINK="#1F6FB2",
                  ENTRY_BG="#FFFFFF", BTN_BG="#E2E6EF",
                  ROW_ALT="#F8FAFD", ROW_SEL_TEXT="#171717",
                  # Primary buttons (Добавить, Сохранить, Запустить)
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
    "dark":  dict(BG="#1A1D2A", PANEL="#252A3A", BORDER="#3A3F50",
                  TEXT="#E8EBF2", MUTED="#8E96AA", HEADER="#0F1119",
                  ACCENT="#D9B95E", LINK="#7DB6E8",
                  ENTRY_BG="#1F2330", BTN_BG="#3A3F50",
                  ROW_ALT="#2C3142", ROW_SEL_TEXT="#171717",
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
}

CURRENT_THEME = "light"

# Module-level colour vars get rebound by apply_theme()
BG = PANEL = BORDER = TEXT = MUTED = HEADER = ACCENT = LINK = "#000"
ENTRY_BG = BTN_BG = ROW_ALT = ROW_SEL_TEXT = "#000"
PRIMARY_BG = PRIMARY_FG = "#000"

def apply_theme(name):
    global BG, PANEL, BORDER, TEXT, MUTED, HEADER, ACCENT, LINK
    global ENTRY_BG, BTN_BG, ROW_ALT, ROW_SEL_TEXT
    global PRIMARY_BG, PRIMARY_FG, CURRENT_THEME
    t = THEMES.get(name, THEMES["light"])
    CURRENT_THEME                    = name if name in THEMES else "light"
    BG, PANEL, BORDER, TEXT, MUTED   = t["BG"], t["PANEL"], t["BORDER"], t["TEXT"], t["MUTED"]
    HEADER, ACCENT, LINK             = t["HEADER"], t["ACCENT"], t["LINK"]
    ENTRY_BG, BTN_BG                 = t["ENTRY_BG"], t["BTN_BG"]
    ROW_ALT, ROW_SEL_TEXT            = t["ROW_ALT"], t["ROW_SEL_TEXT"]
    PRIMARY_BG, PRIMARY_FG           = t["PRIMARY_BG"], t["PRIMARY_FG"]

apply_theme("light")

WIN_W = 880
WIN_H = 560


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
        "wow_path":             r"E:\WOW",
        "realmlist":            REALMLISTS_DEFAULT[0],
        "realms":               list(REALMS_DEFAULT),
        "realmlists":           list(REALMLISTS_DEFAULT),
        "characters":           [],
        "theme":                "light",   # "light" | "dark"
        # Optional single external loader used for ALL characters.
        # If `loader_path` is empty, characters launch WoW.exe directly.
        "loader_path":          "",
        "loader_window_title":  "",
        "loader_launch_button": "",
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
    if not isinstance(cfg.get("realms"), list) or not cfg["realms"]:
        cfg["realms"] = list(REALMS_DEFAULT)
    if not isinstance(cfg.get("realmlists"), list) or not cfg["realmlists"]:
        cfg["realmlists"] = list(REALMLISTS_DEFAULT)
    # Drop obsolete keys left behind by older builds
    for k in ("via_loader", "loaders"):
        cfg.pop(k, None)
    for c in cfg.get("characters", []):
        c.pop("loader_name", None)
    # Decrypt secrets — in-memory cfg always holds plaintext
    for c in cfg.get("characters", []):
        for k in _SECRET_FIELDS:
            if c.get(k):
                c[k] = decrypt_secret(c[k])
    return cfg


def save_cfg(cfg):
    # Write a copy with secrets encrypted; do not mutate caller's cfg
    out = {k: v for k, v in cfg.items() if k != "characters"}
    out["characters"] = []
    for c in cfg.get("characters", []):
        cc = dict(c)
        for k in _SECRET_FIELDS:
            if cc.get(k):
                cc[k] = encrypt_secret(cc[k])
        out["characters"].append(cc)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)


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


def _build_autologin_json(char, realmlist):
    data = {
        "login":     char.get("account", ""),
        "password":  char.get("password", ""),
        "realmlist": realmlist,
        "realmname": char.get("realm", ""),
        "character": char.get("name", ""),
    }
    secret = normalize_totp_secret(char.get("totp_secret", ""))
    if secret:
        # DLL recomputes TOTP at the moment TokenEnterDialog appears, so the
        # code never expires regardless of how long the launch takes.
        data["totp_secret"] = secret
    return data


def _write_autologin_json(wow_dir, char, realmlist):
    """Write per-launch params next to Wow.exe — DLL reads it then deletes it."""
    path = os.path.join(wow_dir, "autologin.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_build_autologin_json(char, realmlist), f, ensure_ascii=False)


def _dump_loader_controls(parent, target_text):
    """Write every child control's class+text to a log so the user can see
    exactly what the loader looks like and fix their button_text setting."""
    try:
        user32 = ctypes.windll.user32
        EnumChildProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        rows = []

        def cb(hwnd, _lp):
            cls = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, cls, 128)
            txt = ctypes.create_unicode_buffer(520)
            user32.GetWindowTextW(hwnd, txt, 520)
            rows.append(f"hwnd={hwnd:>10}  class={cls.value!r:<40}  "
                        f"text={txt.value!r}")
            return True

        user32.EnumChildWindows(parent, EnumChildProc(cb), 0)
        log_dir = _config_dir()
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "loader_debug.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(f"Искал кнопку с текстом: {target_text!r}\n")
            fh.write(f"Не найдено. Список всех контролов окна:\n\n")
            fh.write("\n".join(rows))
    except Exception:
        pass


def _orchestrate_loader(wow_exe, window_title, button_text, on_error=None):
    """
    Drive the external loader's UI:
      1. Wait for its main window to appear.
      2. Poll its child controls for up to 10s — the loader may create them
         lazily after the window itself becomes visible.
      3. If found, push our Wow.exe path into the loader's path edit.
      4. Click the launch button using three methods in sequence
         (BM_CLICK + WM_LBUTTONDOWN/UP + SPACE-key) so at least one works
         regardless of whether the control honours synthetic messages.

    The window is intentionally NOT hidden — many loaders self-close on
    launch, and hiding tends to disturb their internal state.
    """
    if sys.platform != "win32":
        return
    if not (window_title and button_text):
        return

    user32 = ctypes.windll.user32
    WM_SETTEXT       = 0x000C
    BM_CLICK         = 0x00F5
    WM_LBUTTONDOWN   = 0x0201
    WM_LBUTTONUP     = 0x0202
    WM_KEYDOWN       = 0x0100
    WM_KEYUP         = 0x0101
    VK_SPACE         = 0x20
    MK_LBUTTON       = 0x0001

    def _norm(s):
        return "".join((s or "").replace("&", "").split()).lower()
    target = _norm(button_text)

    # Step 1: wait for the loader window
    deadline = time.time() + 30.0
    parent = 0
    while time.time() < deadline:
        parent = user32.FindWindowW(None, window_title)
        if parent:
            break
        time.sleep(0.05)
    if not parent:
        if on_error:
            on_error(f"Окно лоадера с заголовком «{window_title}» "
                     f"не появилось за 30 секунд.\n"
                     f"Проверь поле «Заголовок окна» в Настройках.")
        return

    # Step 2: poll for children — controls may appear lazily
    EnumChildProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    btn = 0
    path_box = 0
    poll_end = time.time() + 10.0
    while time.time() < poll_end and not btn:
        cur = {"btn": 0, "path_box": 0}

        def cb(hwnd, _lp):
            cls = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, cls, 128)
            txt = ctypes.create_unicode_buffer(520)
            user32.GetWindowTextW(hwnd, txt, 520)
            cls_u = cls.value.upper()
            # Match by text on ANY control — TButton, Afx:Button, WinForms
            # Button, custom-drawn classes all qualify.
            if not cur["btn"] and _norm(txt.value) == target:
                cur["btn"] = hwnd
            elif (not cur["path_box"]
                  and "EDIT" in cls_u
                  and txt.value.strip().lower().endswith(".exe")):
                cur["path_box"] = hwnd
            return True

        user32.EnumChildWindows(parent, EnumChildProc(cb), 0)
        btn = cur["btn"] or btn
        path_box = cur["path_box"] or path_box
        if btn:
            break
        time.sleep(0.2)

    # Step 3: push our Wow.exe into the loader's path edit (if any)
    if path_box and wow_exe:
        user32.SendMessageW(path_box, WM_SETTEXT, 0, ctypes.c_wchar_p(wow_exe))
        time.sleep(0.1)

    if not btn:
        # Snapshot every child control so the user can see what captions
        # actually exist in the loader's window.
        _dump_loader_controls(parent, button_text)
        if on_error:
            log_path = os.path.join(_config_dir(), "loader_debug.txt")
            on_error(f"Кнопка с текстом «{button_text}» не найдена "
                     f"в окне лоадера.\n\n"
                     f"Проверь правильность текста в Настройках → "
                     f"Доп настройки.\n\n"
                     f"Список всех контролов окна сохранён в:\n{log_path}")
        return

    # Step 4: click the button. We try three different paths because every
    # GUI framework reacts differently:
    #   - BM_CLICK   — works on real BUTTON-class controls (Win32, WinForms)
    #   - WM_LBUTTONDOWN/UP at client (1,1) — works on custom-drawn buttons
    #   - SPACE keypress on focused control — works for almost everything
    #     focusable, including .NET controls hardened against synthetic clicks
    lParam = (1 << 16) | 1
    try:
        user32.SetFocus(btn)
    except Exception:
        pass

    user32.PostMessageW(btn, BM_CLICK, 0, 0)
    time.sleep(0.10)

    user32.PostMessageW(btn, WM_LBUTTONDOWN, MK_LBUTTON, lParam)
    time.sleep(0.05)
    user32.PostMessageW(btn, WM_LBUTTONUP, 0, lParam)
    time.sleep(0.10)

    user32.PostMessageW(btn, WM_KEYDOWN, VK_SPACE, 0)
    time.sleep(0.05)
    user32.PostMessageW(btn, WM_KEYUP, VK_SPACE, 0)


def _launch_via_loader(cfg, wow_dir, on_error=None):
    path   = (cfg.get("loader_path") or "").strip()
    title  = (cfg.get("loader_window_title") or "").strip()
    button = (cfg.get("loader_launch_button") or "").strip()
    if not path or not os.path.isfile(path):
        raise RuntimeError("Внешний лоадер не найден.\n"
                           "Проверь путь в Настройках → Доп настройки.")
    if not (title and button):
        raise RuntimeError("Не заданы заголовок окна или текст кнопки "
                           "запуска лоадера. Проверь Настройки → Доп настройки.")

    loader_dir = os.path.dirname(path)
    wow_exe    = os.path.join(wow_dir, "Wow.exe")

    threading.Thread(target=_orchestrate_loader,
                     args=(wow_exe, title, button, on_error),
                     daemon=True).start()

    # Leave the loader's window visible — user wanted to see it, and many
    # loaders rely on their own message pump being active.
    subprocess.Popen([path], cwd=loader_dir)


def launch_wow(cfg, char, on_error=None):
    wow_dir = cfg.get("wow_path", "")
    exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(f"Wow.exe не найден:\n{exe}")

    realmlist = (char.get("realmlist") or cfg.get("realmlist")
                 or REALMLISTS_DEFAULT[0])

    deploy_patch(wow_dir)
    update_realmlist(wow_dir, realmlist)

    # Always write autologin.json so the DLL has params no matter who launches Wow.
    _write_autologin_json(wow_dir, char, realmlist)

    if (cfg.get("loader_path") or "").strip():
        _launch_via_loader(cfg, wow_dir, on_error=on_error)
        return

    # Single source of truth for credentials = autologin.json, read by the
    # DLL. Passing them ALSO via argv used to cause a race: the argv path
    # and the JSON path could both fire a login packet, the server saw two
    # auth attempts from the same account and kicked one of them mid-world-
    # load — that was the "1 in 3" disconnect on character enter.
    subprocess.Popen([exe], cwd=wow_dir)


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_colors(class_color):
    """Return (background, foreground) for a row of this class. Saturated
    enough to identify the class instantly; foreground auto-picks black or
    white based on the resulting background's luminance for readability."""
    r, g, b = (int(class_color[1:3], 16), int(class_color[3:5], 16),
               int(class_color[5:7], 16))
    if CURRENT_THEME == "dark":
        tr, tg, tb = (int(PANEL[1:3], 16), int(PANEL[3:5], 16),
                      int(PANEL[5:7], 16))
        a = 0.55          # 55% class hue on dark panel
    else:
        tr, tg, tb = 255, 255, 255
        a = 0.50          # 50% class hue on white
    br = int(r * a + tr * (1 - a))
    bg = int(g * a + tg * (1 - a))
    bb = int(b * a + tb * (1 - a))
    bg_hex = "#{:02X}{:02X}{:02X}".format(br, bg, bb)
    # Rec. 601 luma — pick contrasting fg
    luma = 0.299 * br + 0.587 * bg + 0.114 * bb
    fg_hex = "#1A1A1A" if luma > 150 else "#F2F2F2"
    return bg_hex, fg_hex


def _hyperlink(parent, text, url, bg=None, **kw):
    lbl = tk.Label(parent, text=text, fg=LINK, cursor="hand2",
                   bg=bg if bg else parent["bg"],
                   font=("Segoe UI", 9, "underline"), **kw)
    lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return lbl


def _make_entry(parent, var, show=None):
    e = tk.Entry(parent, textvariable=var, show=show, bg=ENTRY_BG, fg=TEXT,
                 relief="flat", highlightthickness=1)
    e.configure(highlightbackground=BORDER, highlightcolor=ACCENT,
                insertbackground=TEXT, font=("Segoe UI", 10))
    return e


# ── DPAPI secret encryption ───────────────────────────────────────────────────
# Keep passwords/2FA secrets encrypted at rest with the user's Windows profile
# key. The plaintext only lives in memory and in the short-lived autologin.json
# (which the DLL deletes immediately).

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]

_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_SECRET_PREFIX = "enc:v1:"


def _dpapi_call(fn, data):
    buf = (ctypes.c_byte * len(data))(*data)
    in_blob = _DataBlob(len(data),
                        ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    if not fn(ctypes.byref(in_blob), None, None, None, None,
              _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def encrypt_secret(plaintext):
    if not plaintext or sys.platform != "win32":
        return plaintext
    if isinstance(plaintext, str) and plaintext.startswith(_SECRET_PREFIX):
        return plaintext
    try:
        blob = _dpapi_call(ctypes.windll.crypt32.CryptProtectData,
                           plaintext.encode("utf-8"))
        return _SECRET_PREFIX + base64.b64encode(blob).decode("ascii")
    except Exception:
        return plaintext


def decrypt_secret(stored):
    if not stored or not isinstance(stored, str) or not stored.startswith(_SECRET_PREFIX):
        return stored or ""
    try:
        blob = base64.b64decode(stored[len(_SECRET_PREFIX):])
        return _dpapi_call(ctypes.windll.crypt32.CryptUnprotectData,
                           blob).decode("utf-8")
    except Exception:
        return ""


_SECRET_FIELDS = ("password", "totp_secret")


# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        apply_theme(self.cfg.get("theme", "light"))
        self.search_var = tk.StringVar()
        self.count_var  = tk.StringVar()
        self._sort_state = (None, False)  # (column, reverse)
        self._tray_icon = None
        root.title(APP_TITLE)
        root.geometry(f"{WIN_W}x{WIN_H}")
        root.minsize(780, 480)
        root.configure(bg=BG)
        # Hide-to-tray on close, real exit via tray menu
        root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        try:
            root.iconbitmap(_bundled("wow.ico"))
        except Exception:
            pass
        self.build()
        self._setup_tray()

    def _apply_ttk_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Treeview",
                     background=PANEL, foreground=TEXT,
                     fieldbackground=PANEL, borderwidth=0, rowheight=22)
        st.configure("Treeview.Heading",
                     background=BORDER, foreground=TEXT, borderwidth=0,
                     relief="flat", font=("Segoe UI", 9, "bold"))
        st.map("Treeview",
               background=[("selected", ACCENT)],
               foreground=[("selected", ROW_SEL_TEXT)])
        st.map("Treeview.Heading",
               background=[("active", ACCENT)])

    def rebuild(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self.build()

    def build(self):
        self._apply_ttk_styles()

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(toolbar, text="Поиск", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        search = _make_entry(toolbar, self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(8, 12), ipady=6)
        search.bind("<KeyRelease>", lambda _e: self.render_rows())

        tk.Button(toolbar, text="Добавить", bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", padx=14, pady=7, command=self.add_char
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="Изменить", bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.edit_selected
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="Удалить", bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.delete_selected
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="↑", bg=BTN_BG, fg=TEXT, relief="flat",
                  width=2, pady=7, command=lambda: self._move(-1)
                  ).pack(side="left", padx=(0, 2))
        tk.Button(toolbar, text="↓", bg=BTN_BG, fg=TEXT, relief="flat",
                  width=2, pady=7, command=lambda: self._move(1)
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="Настройки", bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=14, pady=7, command=self.settings
                  ).pack(side="right")

        table_wrap = tk.Frame(self.root, bg=PANEL,
                              highlightbackground=BORDER, highlightthickness=1)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        cols = ("name", "class", "gs", "account", "realm", "realmlist")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                                 selectmode="browse")
        headings = (("name",      "Персонаж", 140, "w"),
                    ("class",     "Класс",    110, "w"),
                    ("gs",        "ГС",        60, "center"),
                    ("account",   "Аккаунт",  110, "w"),
                    ("realm",     "Реалм",    210, "w"),
                    ("realmlist", "Realmlist",160, "w"))
        for col, label, w, anchor in headings:
            self.tree.heading(col, text=label,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anchor)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.launch_selected())
        self.tree.bind("<Return>",   lambda _e: self.launch_selected())

        for cls, color in CLASS_COLORS.items():
            bg_, fg_ = _row_colors(color)
            self.tree.tag_configure(f"cls_{cls}",
                                    background=bg_, foreground=fg_)

        sb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

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

    # ── sort/reorder ──────────────────────────────────────────────────────────

    def _sort_by(self, col):
        prev_col, prev_rev = self._sort_state
        rev = (prev_col == col) and not prev_rev
        self._sort_state = (col, rev)

        def _key(c):
            v = c.get(col, "")
            if col == "gs":
                try:    return int("".join(ch for ch in str(v) if ch.isdigit()) or 0)
                except: return 0
            return str(v).lower()
        self.cfg["characters"].sort(key=_key, reverse=rev)
        save_cfg(self.cfg)
        self.render_rows()

    def _move(self, delta):
        idx = self.selected_idx(silent=True)
        if idx is None:
            return
        chars = self.cfg["characters"]
        new = idx + delta
        if 0 <= new < len(chars):
            chars[idx], chars[new] = chars[new], chars[idx]
            save_cfg(self.cfg)
            self._sort_state = (None, False)
            self.render_rows()
            self.tree.selection_set(str(new))

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
        self._refresh_tray()

    def selected_idx(self, silent=False):
        sel = self.tree.selection()
        if not sel:
            if not silent:
                messagebox.showinfo(APP_TITLE, "Выбери персонажа в списке.")
            return None
        return int(sel[0])

    # ── tray ──────────────────────────────────────────────────────────────────

    def _setup_tray(self):
        if sys.platform != "win32":
            return
        try:
            import pystray
            from PIL import Image
        except Exception:
            return

        try:
            icon_img = Image.open(_bundled("wow.ico"))
        except Exception:
            return

        def show(_i=None, _it=None):
            self.root.after(0, self._show_window)

        def quit_(_i=None, _it=None):
            self.root.after(0, self._quit)

        def launch_factory(idx):
            def _launch(_i=None, _it=None):
                if 0 <= idx < len(self.cfg.get("characters", [])):
                    char = self.cfg["characters"][idx]
                    try:
                        launch_wow(self.cfg, char)
                    except Exception:
                        pass
            return _launch

        def build_menu():
            chars = self.cfg.get("characters", [])
            items = [pystray.MenuItem("Показать", show, default=True),
                     pystray.Menu.SEPARATOR]
            for i, c in enumerate(chars[:15]):
                lbl = c.get("name", f"#{i+1}")
                items.append(pystray.MenuItem(lbl, launch_factory(i)))
            items += [pystray.Menu.SEPARATOR,
                      pystray.MenuItem("Выход", quit_)]
            return pystray.Menu(*items)

        self._tray_icon = pystray.Icon("wow_manager", icon_img,
                                       APP_TITLE, build_menu())
        self._build_tray_menu = build_menu
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _refresh_tray(self):
        if self._tray_icon and getattr(self, "_build_tray_menu", None):
            try:
                self._tray_icon.menu = self._build_tray_menu()
                self._tray_icon.update_menu()
            except Exception:
                pass

    def _hide_to_tray(self):
        if self._tray_icon:
            self.root.withdraw()
        else:
            self._quit()

    def _show_window(self):
        # Cover every hidden state: withdrawn (from tray), iconified
        # (minimised), or just buried behind other windows.
        self.root.deiconify()
        try:
            self.root.state("normal")
        except tk.TclError:
            pass
        self.root.lift()
        # Topmost-toggle trick — Windows won't let a background process steal
        # focus directly, but briefly promoting then demoting works.
        self.root.attributes("-topmost", True)
        self.root.after(50, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _quit(self):
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self.root.destroy()

    def launch_selected(self):
        idx = self.selected_idx()
        if idx is None:
            return
        char = self.cfg["characters"][idx]

        # Worker-thread callback for async errors (loader button not found etc).
        # tkinter is single-threaded — we hop back to the UI thread via after().
        def _async_err(msg):
            self.root.after(0, lambda m=msg:
                            messagebox.showerror(APP_TITLE, m))

        try:
            launch_wow(self.cfg, char, on_error=_async_err)
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
                  bg=PRIMARY_BG, fg=PRIMARY_FG, relief="flat", pady=9,
                  cursor="hand2", command=save
                  ).pack(fill="x", padx=20, pady=18)

        first.focus_set()

    # ── settings dialog ───────────────────────────────────────────────────────

    def settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Настройки")
        dlg.geometry("580x780")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        # Scrollable canvas so the dialog fits even when the loader manager
        # is expanded
        outer = tk.Frame(dlg, bg=BG); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 120),
                                                     "units"))

        tk.Label(body, text="Настройки", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")
                 ).pack(padx=20, pady=(18, 10), anchor="w")

        # ── WoW path ─────────────────────────────────────────────────────────
        tk.Label(body, text="Папка с Wow.exe", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20)
        path_var = tk.StringVar(value=self.cfg.get("wow_path", ""))
        row = tk.Frame(body, bg=BG); row.pack(fill="x", padx=20, pady=(4, 12))
        _make_entry(row, path_var).pack(side="left", fill="x", expand=True,
                                        ipady=5)

        def browse():
            p = filedialog.askopenfilename(
                parent=dlg, title="Выбери Wow.exe",
                filetypes=[("WoW Client", "Wow.exe"),
                           ("Exe", "*.exe"), ("All", "*.*")])
            if p:
                path_var.set(os.path.normpath(os.path.dirname(p)))

        tk.Button(row, text="Обзор", bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=10, command=browse
                  ).pack(side="left", padx=(8, 0), ipady=5)

        # ── Realms list ──────────────────────────────────────────────────────
        tk.Label(body, text="Список реалмов (по строке на реалм)", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=20)
        realms_text = tk.Text(body, height=6, bg=ENTRY_BG, fg=TEXT,
                              relief="flat", highlightthickness=1,
                              font=("Segoe UI", 10), wrap="none")
        realms_text.configure(highlightbackground=BORDER,
                              highlightcolor=ACCENT, insertbackground=TEXT)
        realms_text.insert("1.0", "\n".join(self.cfg.get("realms", [])))
        realms_text.pack(fill="x", padx=20, pady=(2, 12))

        # ── Realmlists ───────────────────────────────────────────────────────
        tk.Label(body, text="Список realmlist-серверов (по строке)", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=20)
        realmlists_text = tk.Text(body, height=3, bg=ENTRY_BG, fg=TEXT,
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

        # ── Config management ────────────────────────────────────────────────
        tk.Label(body, text="Конфиг", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(4, 0))
        cfg_row = tk.Frame(body, bg=BG)
        cfg_row.pack(fill="x", padx=20, pady=(2, 12))

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
            for c in new_cfg.get("characters", []):
                for k in _SECRET_FIELDS:
                    if c.get(k):
                        c[k] = decrypt_secret(c[k])
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
                # Export plaintext (DPAPI keys are profile-specific and useless
                # outside this PC)
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

        for txt, bg_, fg_, cmd in (
            ("Загрузить", BTN_BG,    TEXT,      load_config),
            ("Скачать",   BTN_BG,    TEXT,      download_config),
            ("Очистить",  "#FBE5E7", "#9A2730", clear_config),
        ):
            tk.Button(cfg_row, text=txt, bg=bg_, fg=fg_, relief="flat",
                      padx=10, pady=6, command=cmd
                      ).pack(side="left", padx=(0, 6))

        # ══ Доп настройки ════════════════════════════════════════════════════
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(8, 8))
        tk.Label(body, text="Доп настройки", bg=BG, fg=TEXT,
                 font=("Segoe UI", 11, "bold")
                 ).pack(fill="x", padx=20, pady=(0, 6))

        # ── Theme toggle ─────────────────────────────────────────────────────
        theme_var = tk.StringVar(value=self.cfg.get("theme", "light"))
        theme_row = tk.Frame(body, bg=BG); theme_row.pack(fill="x", padx=20)
        tk.Label(theme_row, text="Тема:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Combobox(theme_row, textvariable=theme_var,
                     values=("light", "dark"), state="readonly",
                     width=10, font=("Segoe UI", 10)
                     ).pack(side="left", padx=(8, 0), ipady=2)

        # ── Global loader (optional) ─────────────────────────────────────────
        loader_path_var  = tk.StringVar(value=self.cfg.get("loader_path", ""))
        loader_title_var = tk.StringVar(value=self.cfg.get("loader_window_title", ""))
        loader_btn_var   = tk.StringVar(value=self.cfg.get("loader_launch_button", ""))

        tk.Label(body, text="Внешний лоадер (необязательно — используется "
                            "для всех персонажей)", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(12, 0))

        tk.Label(body, text="Путь к .exe лоадера", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(6, 0))
        loader_row = tk.Frame(body, bg=BG)
        loader_row.pack(fill="x", padx=20, pady=(2, 6))
        _make_entry(loader_row, loader_path_var).pack(side="left", fill="x",
                                                      expand=True, ipady=5)

        def browse_loader():
            p = filedialog.askopenfilename(
                parent=dlg, title="Выбери .exe лоадера",
                filetypes=[("Exe", "*.exe"), ("All", "*.*")])
            if p:
                loader_path_var.set(os.path.normpath(p))

        tk.Button(loader_row, text="Обзор", bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, command=browse_loader
                  ).pack(side="left", padx=(8, 0), ipady=5)

        sub_row = tk.Frame(body, bg=BG)
        sub_row.pack(fill="x", padx=20, pady=(0, 12))
        col_l = tk.Frame(sub_row, bg=BG)
        col_l.pack(side="left", fill="x", expand=True)
        col_r = tk.Frame(sub_row, bg=BG)
        col_r.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(col_l, text="Заголовок окна", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(col_l, loader_title_var).pack(fill="x", ipady=4)
        tk.Label(col_r, text="Текст кнопки запуска", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(col_r, loader_btn_var).pack(fill="x", ipady=4)

        # ── Save button ──────────────────────────────────────────────────────
        def save():
            self.cfg["wow_path"] = path_var.get().strip()
            realms_new = lines(realms_text)
            realmlists_new = lines(realmlists_text)
            if realms_new:
                self.cfg["realms"] = realms_new
            if realmlists_new:
                self.cfg["realmlists"] = realmlists_new
                if self.cfg.get("realmlist") not in realmlists_new:
                    self.cfg["realmlist"] = realmlists_new[0]
            # rstrip-only so user can keep "Run WoW" with internal spaces
            self.cfg["loader_path"]          = loader_path_var.get().strip()
            self.cfg["loader_window_title"]  = loader_title_var.get().strip()
            self.cfg["loader_launch_button"] = loader_btn_var.get().strip()
            old_theme = self.cfg.get("theme", "light")
            new_theme = theme_var.get()
            self.cfg["theme"] = new_theme
            save_cfg(self.cfg)
            self.render_rows()
            dlg.destroy()
            if old_theme != new_theme:
                apply_theme(new_theme)
                self.rebuild()

        tk.Button(body, text="Сохранить", bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(12, 14))


# ── single-instance lock ──────────────────────────────────────────────────────
# A tiny TCP server bound to localhost acts as both the lock and the IPC
# channel: a second copy of the app probes the port, and if it answers, the
# new copy sends a "SHOW" request and exits. The running instance picks up
# the request and brings its window forward.

_SINGLE_INSTANCE_PORT = 47823     # arbitrary, picked from the private range
_SINGLE_INSTANCE_TOKEN = b"WowManagerShow"


def _signal_existing_instance():
    """Probe the lock port. Return True if an existing instance answered."""
    try:
        c = socket.create_connection(("127.0.0.1", _SINGLE_INSTANCE_PORT),
                                     timeout=0.5)
    except OSError:
        return False
    try:
        c.sendall(_SINGLE_INSTANCE_TOKEN)
        c.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    finally:
        c.close()
    return True


def _start_single_instance_listener(on_show):
    """Bind the lock port and accept SHOW pings in a daemon thread."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
    except OSError:
        # Lost a race against another instance starting at the same time.
        # Fall back to sending the SHOW ourselves and bowing out.
        _signal_existing_instance()
        sys.exit(0)
    srv.listen(4)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    data = conn.recv(64)
                if data == _SINGLE_INSTANCE_TOKEN:
                    on_show()
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    # If another instance is already running, ask it to come forward and
    # exit silently without building our own UI.
    if _signal_existing_instance():
        sys.exit(0)

    root = tk.Tk()
    app = App(root)

    # Thread-safe trampoline back to the UI thread for SHOW requests
    def _bring_forward():
        root.after(0, app._show_window)
    _start_single_instance_listener(_bring_forward)

    root.mainloop()
