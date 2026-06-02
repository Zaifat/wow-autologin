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
import re
import webbrowser
import zipfile
from tkinter import filedialog, messagebox, ttk

__version__ = "1.4.0"


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

# ── localization ───────────────────────────────────────────────────────────────
# Strings are keyed by their Russian source text. t() returns the English
# variant when LANG == "en", otherwise echoes the Russian string. This keeps
# the source readable and lets us wrap literals in-place without renaming.

LANG = "ru"   # "ru" | "en"


def set_lang(name):
    global LANG
    LANG = name if name in ("ru", "en") else "ru"


_EN = {
    # toolbar / main window
    "Поиск": "Search",
    "Добавить": "Add",
    "Изменить": "Edit",
    "Удалить": "Delete",
    "Настройки": "Settings",
    "Запустить выбранного": "Launch selected",
    "    •    Отблагодарить:": "    •    Support:",
    "Персонажи": "Characters",
    "Аккаунты": "Accounts",
    "Персонажей: {c} · Аккаунтов: {a}": "Characters: {c} · Accounts: {a}",
    "Выбери запись в списке.": "Select an entry in the list.",
    # table headings
    "Персонаж": "Character",
    "Класс": "Class",
    "ГС": "GS",
    "Аккаунт": "Account",
    "Реалм": "Realm",
    "Realmlist": "Realmlist",
    # entry dialog
    "Запись": "Entry",
    "Ник персонажа (пусто = только аккаунт)": "Character name (empty = account only)",
    "Логин аккаунта": "Account login",
    "Пароль": "Password",
    "ГС (Gear Score)": "GS (Gear Score)",
    "Секрет 2FA (Google / 2FAS Auth / Yandex Authenticator)":
        "2FA secret (Google / 2FAS Auth / Yandex Authenticator)",
    "Если 2FA не подключена — оставь пусто.":
        "Leave empty if 2FA is not enabled.",
    "невалидно": "invalid",
    "Сохранить": "Save",
    "Введи ник персонажа или логин аккаунта.":
        "Enter a character name or account login.",
    # settings
    "Папка с Wow.exe": "WoW folder (Wow.exe)",
    "Обзор": "Browse",
    "Выбери Wow.exe": "Select Wow.exe",
    "Список реалмов (по строке на реалм)": "Realm list (one per line)",
    "Список realmlist-серверов (по строке)": "Realmlist servers (one per line)",
    "Конфиг": "Config",
    "Загрузить": "Load",
    "Скачать": "Export",
    "Очистить": "Clear",
    "Загрузить конфиг": "Load config",
    "файл не содержит объект конфига": "file is not a config object",
    "Не удалось прочитать конфиг:\n{e}": "Failed to read config:\n{e}",
    "Загружено персонажей: {n}": "Loaded entries: {n}",
    "Сохранить конфиг как…": "Save config as…",
    "Сохранено:\n{p}": "Saved:\n{p}",
    "Очистить весь конфиг?\nВсе персонажи и настройки будут удалены безвозвратно.":
        "Clear the entire config?\nAll entries and settings will be permanently deleted.",
    "Доп настройки": "Advanced",
    "Тема:": "Theme:",
    "Язык:": "Language:",
    "Шифровать пароли (привязать к этому ПК)":
        "Encrypt passwords (bind to this PC)",
    "Внешний лоадер (необязательно — используется для всех персонажей)":
        "External loader (optional — used for all characters)",
    "Путь к .exe лоадера": "Loader .exe path",
    "Выбери .exe лоадера": "Select loader .exe",
    "Заголовок окна": "Window title",
    "Текст кнопки запуска": "Launch button text",
    # confirmations / errors
    "Удалить «{name}»?": "Delete «{name}»?",
    "Wow.exe не найден:\n{exe}": "Wow.exe not found:\n{exe}",
    "В программу не зашит {dll}": "{dll} is not bundled with the app",
    "Не найден Wow.exe в {dir}": "Wow.exe not found in {dir}",
    "Внешний лоадер не найден.\nПроверь путь в Настройках → Доп настройки.":
        "External loader not found.\nCheck the path in Settings → Advanced.",
    "Не заданы заголовок окна или текст кнопки запуска лоадера. "
    "Проверь Настройки → Доп настройки.":
        "Loader window title or launch button text is empty. "
        "Check Settings → Advanced.",
    "Окно лоадера с заголовком «{title}» не появилось за 30 секунд.\n"
    "Проверь поле «Заголовок окна» в Настройках.":
        "Loader window titled «{title}» did not appear within 30 seconds.\n"
        "Check the «Window title» field in Settings.",
    "Кнопка с текстом «{btn}» не найдена в окне лоадера.\n\n"
    "Проверь правильность текста в Настройках → Доп настройки.\n\n"
    "Список всех контролов окна сохранён в:\n{path}":
        "Button labeled «{btn}» was not found in the loader window.\n\n"
        "Check the text in Settings → Advanced.\n\n"
        "A dump of all window controls was saved to:\n{path}",
    # tray
    "Показать": "Show",
    "Выход": "Exit",
    # misc
    "(без класса)": "(no class)",
    "Авто-бэкап WTF и аддонов при запуске":
        "Auto-backup WTF & AddOns on launch",
    # backup settings dialog
    "Настроить…": "Configure…",
    "Настройки бэкапа": "Backup settings",
    "Сколько копий хранить": "How many copies to keep",
    "Хранятся N последних снимков. Когда копий становится больше — "
    "самый старый удаляется автоматически (кольцевой буфер).":
        "The N most recent snapshots are kept. When there are more, the "
        "oldest one is deleted automatically (ring buffer).",
    "Интервал между копиями (мин)": "Interval between copies (min)",
    "Новый снимок создаётся при запуске, только если с прошлого прошло "
    "не меньше указанных минут. 0 — копировать при каждом запуске.":
        "A new snapshot is made on launch only if at least this many minutes "
        "have passed since the last one. 0 — back up on every launch.",
    "Папка для бэкапов (пусто = папка игры)":
        "Backup folder (empty = game folder)",
    "Выбери папку для бэкапов": "Select backup folder",
    "Папка требует прав администратора. Выдать доступ к ней?":
        "This folder requires administrator rights. Grant access to it?",
    "Папка по-прежнему недоступна для записи.\n"
    "Бэкапы в неё работать не будут.":
        "The folder is still not writable.\nBackups to it will not work.",
    "Введи число (копии и интервал должны быть числами).":
        "Enter numbers (copies and interval must be numeric).",
    # restore
    "Восстановить…": "Restore…",
    "Восстановление из бэкапа": "Restore from backup",
    "Бэкапов пока нет.": "No backups yet.",
    "Папка игры (Wow.exe) не задана в Настройках.":
        "The game folder (Wow.exe) is not set in Settings.",
    "Восстановить выбранный снимок поверх текущих WTF и аддонов?\n"
    "Текущие файлы будут перезаписаны.":
        "Restore the selected snapshot over the current WTF and AddOns?\n"
        "Current files will be overwritten.",
    "Готово. Восстановлено из:\n{name}": "Done. Restored from:\n{name}",
    "Не удалось восстановить:\n{e}": "Restore failed:\n{e}",
    "Восстановить": "Restore",
    # shortcuts
    "Ярлык на рабочем столе для записи": "Desktop shortcut for an entry",
    "Запись:": "Entry:",
    "Сделать ярлык": "Create shortcut",
    "Сначала добавь хотя бы одну запись.": "Add at least one entry first.",
    "Ярлык создан на рабочем столе:\n{path}":
        "Shortcut created on the desktop:\n{path}",
    "Не удалось создать ярлык:\n{e}": "Failed to create shortcut:\n{e}",
    "Запись «{name}» не найдена.": "Entry «{name}» was not found.",
    # gearscore
    "Обновить ГС из SavedVariables (нужен аддон GearScore)":
        "Refresh GS from SavedVariables (requires a GearScore addon)",
    "ГС не найден в SavedVariables.\nПроверь, что установлен аддон "
    "GearScore и ты заходил за этого персонажа.":
        "GS not found in SavedVariables.\nMake sure a GearScore addon is "
        "installed and you have logged in on this character.",
    "Сначала укажи папку с Wow.exe в Настройках.":
        "Set the Wow.exe folder in Settings first.",
}

# Sentinel shown in the class combobox for "no class"
NO_CLASS = "(без класса)"


def t(s):
    """Translate a Russian source string to the active language."""
    if LANG == "en":
        return _EN.get(s, s)
    return s


WOW_CLASSES = [
    "Воин", "Паладин", "Охотник", "Разбойник", "Жрец",
    "Рыцарь смерти", "Шаман", "Маг", "Чернокнижник", "Друид",
]

# Canonical class key is always Russian (used in config + CLASS_COLORS).
# Display can be localized via class_disp(); class_canon() maps back.
CLASS_EN = {
    "Воин": "Warrior",          "Паладин": "Paladin",
    "Охотник": "Hunter",        "Разбойник": "Rogue",
    "Жрец": "Priest",           "Рыцарь смерти": "Death Knight",
    "Шаман": "Shaman",          "Маг": "Mage",
    "Чернокнижник": "Warlock",  "Друид": "Druid",
}
CLASS_RU = {v: k for k, v in CLASS_EN.items()}


def class_disp(ru):
    return CLASS_EN.get(ru, ru) if LANG == "en" else ru


def class_canon(disp):
    return CLASS_RU.get(disp, disp)


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
                  ROW_ALT="#F8FAFD",
                  # Selection = a darkening overlay (not a colour fill)
                  SEL_BG="#33405A", SEL_FG="#FFFFFF",
                  # Primary buttons (Добавить, Сохранить, Запустить)
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
    "dark":  dict(BG="#1A1D2A", PANEL="#252A3A", BORDER="#3A3F50",
                  TEXT="#E8EBF2", MUTED="#8E96AA", HEADER="#0F1119",
                  ACCENT="#D9B95E", LINK="#7DB6E8",
                  ENTRY_BG="#1F2330", BTN_BG="#3A3F50",
                  ROW_ALT="#2C3142",
                  SEL_BG="#0E1118", SEL_FG="#FFFFFF",
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
}

CURRENT_THEME = "light"

# Module-level colour vars get rebound by apply_theme()
BG = PANEL = BORDER = TEXT = MUTED = HEADER = ACCENT = LINK = "#000"
ENTRY_BG = BTN_BG = ROW_ALT = SEL_BG = SEL_FG = "#000"
PRIMARY_BG = PRIMARY_FG = "#000"

def apply_theme(name):
    global BG, PANEL, BORDER, TEXT, MUTED, HEADER, ACCENT, LINK
    global ENTRY_BG, BTN_BG, ROW_ALT, SEL_BG, SEL_FG
    global PRIMARY_BG, PRIMARY_FG, CURRENT_THEME
    t = THEMES.get(name, THEMES["light"])
    CURRENT_THEME                    = name if name in THEMES else "light"
    BG, PANEL, BORDER, TEXT, MUTED   = t["BG"], t["PANEL"], t["BORDER"], t["TEXT"], t["MUTED"]
    HEADER, ACCENT, LINK             = t["HEADER"], t["ACCENT"], t["LINK"]
    ENTRY_BG, BTN_BG                 = t["ENTRY_BG"], t["BTN_BG"]
    ROW_ALT                          = t["ROW_ALT"]
    SEL_BG, SEL_FG                   = t["SEL_BG"], t["SEL_FG"]
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
    """Folder containing the program (exe in a frozen build, .py in dev)."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _appdata_dir():
    """Per-user fallback directory under %LOCALAPPDATA%."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    d = os.path.join(base, "АвтологинWOW")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _dir_writable(d):
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _resolve_config_file():
    """Prefer characters.json next to the program (portable). Fall back to
    %LOCALAPPDATA% only when the program folder isn't writable (e.g. when
    installed under Program Files). Existing configs in either location are
    respected so nobody loses their data on upgrade."""
    program_cfg = os.path.join(_app_dir(), "characters.json")
    appdata_cfg = os.path.join(_appdata_dir(), "characters.json")
    if os.path.isfile(program_cfg):
        return program_cfg
    if os.path.isfile(appdata_cfg):
        return appdata_cfg
    if _dir_writable(_app_dir()):
        return program_cfg
    return appdata_cfg


CONFIG_FILE = _resolve_config_file()


def _config_dir():
    """Directory holding the active config (used for logs / debug dumps)."""
    return os.path.dirname(CONFIG_FILE)


# ── config ────────────────────────────────────────────────────────────────────

def _default_cfg():
    return {
        "wow_path":             r"E:\WOW",
        "realmlist":            REALMLISTS_DEFAULT[0],
        "realms":               list(REALMS_DEFAULT),
        "realmlists":           list(REALMLISTS_DEFAULT),
        "characters":           [],
        "theme":                "light",   # "light" | "dark"
        "lang":                 "ru",      # "ru" | "en"
        # Encrypt passwords / 2FA secrets at rest with Windows DPAPI (bound to
        # this PC + user). Turn off to store them as plaintext (portable).
        "encrypt_secrets":      True,
        # Snapshot the game's WTF folder + Interface/AddOns before launch.
        "backup_wtf":           False,
        "backup_keep":          3,    # ring buffer size
        "backup_interval_min":  30,   # min minutes between snapshots
        "backup_dir":           "",   # empty = <wow_dir>/_WowManagerBackups
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
    # Write a copy with secrets optionally encrypted; never mutate caller's cfg
    encrypt = cfg.get("encrypt_secrets", True)
    out = {k: v for k, v in cfg.items() if k != "characters"}
    out["characters"] = []
    for c in cfg.get("characters", []):
        cc = dict(c)
        for k in _SECRET_FIELDS:
            if cc.get(k):
                cc[k] = encrypt_secret(cc[k]) if encrypt else cc[k]
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
        raise RuntimeError(t("В программу не зашит {dll}").format(dll=AWESOME_DLL))
    dst_dll = os.path.join(wow_dir, AWESOME_DLL)
    if (not os.path.isfile(dst_dll)
            or os.path.getsize(dst_dll) != os.path.getsize(src_dll)):
        shutil.copy2(src_dll, dst_dll)
    wow_exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(wow_exe):
        raise RuntimeError(t("Не найден Wow.exe в {dir}").format(dir=wow_dir))
    if not is_wow_patched(wow_exe):
        patch_wow_exe(wow_exe)


def update_realmlist(wow_dir, realmlist):
    with open(os.path.join(wow_dir, "realmlist.wtf"), "w", encoding="ascii") as f:
        f.write(f"set realmlist {realmlist}\n")


# ── GearScore from SavedVariables ──────────────────────────────────────────────
# Best-effort: WotLK GearScore is produced by an addon (GearScore / TacoTip /
# GearScoreLib …) that writes a *.lua SavedVariables file. There is no single
# universal schema, so we scan the account's and the character's SavedVariables
# for "GearScore"-labelled numbers in a plausible range and take the best match.

_GS_PATTERNS = [
    re.compile(r'[Gg]ear\s*[Ss]core["\]\s]*=\s*"?(\d{3,5})'),
    re.compile(r'["\[]GS["\]\s]*=\s*"?(\d{3,5})'),
    re.compile(r'\bGearScore\b\D{0,12}(\d{3,5})'),
]


def _gs_candidate_files(wow_dir, account, character):
    """SavedVariables .lua files for the account + the specific character."""
    files = []
    if not (wow_dir and account):
        return files
    acc_root = os.path.join(wow_dir, "WTF", "Account")
    if not os.path.isdir(acc_root):
        return files
    # Account folder name is usually the login upper-cased, but match loosely.
    acc_dirs = [d for d in os.listdir(acc_root)
                if d.upper() == account.upper()
                or d.upper() == account.strip().upper()]
    for acc in acc_dirs:
        adir = os.path.join(acc_root, acc)
        sv = os.path.join(adir, "SavedVariables")
        if os.path.isdir(sv):
            files += [os.path.join(sv, f) for f in os.listdir(sv)
                      if f.lower().endswith(".lua")]
        # per-character SavedVariables under each realm folder
        for realm in os.listdir(adir):
            rpath = os.path.join(adir, realm)
            if not os.path.isdir(rpath) or realm == "SavedVariables":
                continue
            for ch in os.listdir(rpath):
                if character and ch.lower() != character.lower():
                    continue
                csv = os.path.join(rpath, ch, "SavedVariables")
                if os.path.isdir(csv):
                    files += [os.path.join(csv, f) for f in os.listdir(csv)
                              if f.lower().endswith(".lua")]
    return files


def read_gearscore(wow_dir, account, character):
    """Return a plausible GearScore int parsed from SavedVariables, or None."""
    best = None
    for fp in _gs_candidate_files(wow_dir, account, character):
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        # If we know the character, prefer text near its name
        regions = [text]
        if character:
            i = text.lower().find(character.lower())
            if i >= 0:
                regions = [text[max(0, i - 400): i + 400], text]
        for region in regions:
            for pat in _GS_PATTERNS:
                for m in pat.finditer(region):
                    val = int(m.group(1))
                    if 1000 <= val <= 7000:      # plausible WotLK GS range
                        best = max(best or 0, val)
            if best:
                break
    return best


# ── WTF / AddOns backup ────────────────────────────────────────────────────────

BACKUP_DIR_NAME = "_WowManagerBackups"


def _backup_dest_root(cfg, wow_dir):
    """Resolve the backup destination: explicit `backup_dir` if set, else a
    folder inside the game directory."""
    custom = (cfg.get("backup_dir") or "").strip()
    return custom if custom else os.path.join(wow_dir, BACKUP_DIR_NAME)


def _list_snapshots(dest_root):
    """Newest-last list of snapshot .zip files."""
    try:
        return sorted(
            (os.path.join(dest_root, d) for d in os.listdir(dest_root)
             if d.startswith("backup_") and d.endswith(".zip")
             and os.path.isfile(os.path.join(dest_root, d))),
            key=os.path.getmtime)
    except OSError:
        return []


def _backup_game_data(wow_dir, dest_root, keep, interval_sec):
    """Snapshot WTF + Interface/AddOns into a compressed timestamped .zip under
    dest_root. Throttled (interval_sec) and ring-buffered (keep). Best-effort —
    never raises. Runs in a background thread."""
    try:
        if not wow_dir or not os.path.isdir(wow_dir):
            return
        os.makedirs(dest_root, exist_ok=True)

        existing = _list_snapshots(dest_root)
        # Throttle: skip if the newest snapshot is younger than the interval
        if existing and (time.time() - os.path.getmtime(existing[-1])
                         < interval_sec):
            return

        tmp_path = os.path.join(dest_root,
                                time.strftime("backup_%Y%m%d_%H%M%S.zip.part"))
        final_path = tmp_path[:-5]  # strip ".part"

        sources = (("WTF", os.path.join(wow_dir, "WTF")),
                   ("AddOns", os.path.join(wow_dir, "Interface", "AddOns")))
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as z:
            for label, src in sources:
                if not os.path.isdir(src):
                    continue
                for root, _dirs, files in os.walk(src):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        arc = os.path.join(label, os.path.relpath(fp, src))
                        try:
                            z.write(fp, arc)
                        except OSError:
                            pass  # locked/vanished file — skip
        os.replace(tmp_path, final_path)  # atomic: only complete zips appear

        # Prune to the newest `keep` snapshots
        for old in _list_snapshots(dest_root)[:-max(1, keep)]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        # Clean up a half-written part file if anything blew up
        try:
            if 'tmp_path' in dir() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _restore_snapshot(wow_dir, zip_path):
    """Extract a snapshot .zip back into the game folder: WTF/* → <wow>/WTF,
    AddOns/* → <wow>/Interface/AddOns. Merges over existing files."""
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if member.endswith("/"):
                continue
            norm = member.replace("\\", "/")
            if norm.startswith("WTF/"):
                dest = os.path.join(wow_dir, "WTF", *norm[len("WTF/"):].split("/"))
            elif norm.startswith("AddOns/"):
                rel = norm[len("AddOns/"):].split("/")
                dest = os.path.join(wow_dir, "Interface", "AddOns", *rel)
            else:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


def _zip_size_str(path):
    try:
        b = float(os.path.getsize(path))
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{int(b)} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} GB"


# ── elevation helper (UAC) ─────────────────────────────────────────────────────

def _run_elevated(exe, params, wait_ms=120000):
    """Launch `exe params` elevated via ShellExecuteEx('runas') and wait.
    Returns the child's exit code, or None if the user declined UAC / it
    failed. Windows-only."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE)]

    SEE_MASK_NOCLOSEPROCESS = 0x40
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None
    if not sei.hProcess:
        return 0
    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, wait_ms)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(sei.hProcess)
    return code.value


def _grant_write_access(path):
    """Elevate once to create `path` and grant the current user Modify rights,
    so subsequent (non-elevated) backups can write there without prompting."""
    user = os.environ.get("USERNAME", "")
    # mkdir (ignore if exists) then icacls grant Modify, inheritable, recursive
    params = ('/c mkdir "{p}" 2>nul & icacls "{p}" '
              '/grant "{u}":(OI)(CI)M /T').format(p=path, u=user)
    return _run_elevated("cmd.exe", params)


# ── desktop shortcuts ──────────────────────────────────────────────────────────

def _self_exe():
    """Path to the Manager_WOW.exe that a shortcut should launch. Never
    python.exe — a shortcut must depend on nothing but our own program."""
    exe = sys.executable or ""
    base = os.path.basename(exe).lower()
    if base.endswith(".exe") and base not in ("python.exe", "pythonw.exe"):
        return exe  # frozen build: this IS Manager_WOW.exe
    # Dev mode (running under python): look for the built exe next to us.
    cand = os.path.join(_app_dir(), "Manager_WOW.exe")
    return cand if os.path.isfile(cand) else exe


def create_desktop_shortcut(label, launch_value):
    """Create a .lnk on the desktop that launches Manager_WOW with
    `--launch "<launch_value>"`. The target is always Manager_WOW.exe — the
    shortcut requires nothing else installed. Windows-only."""
    if sys.platform != "win32":
        raise RuntimeError("Shortcuts are Windows-only")

    target = _self_exe()
    if os.path.basename(target).lower() in ("python.exe", "pythonw.exe"):
        # No compiled exe found (pure dev checkout) — refuse rather than make
        # a shortcut that depends on a Python install.
        raise RuntimeError("Manager_WOW.exe не найден рядом с программой")
    arguments = '--launch "%s"' % launch_value.replace('"', '')
    workdir = os.path.dirname(target)
    # Use the exe's own embedded icon so the shortcut never points at a
    # separate file that could go missing.
    icon = target + ",0"

    safe = "".join(c for c in label if c not in '\\/:*?"<>|').strip() or "WoW"

    def q(s):
        return s.replace("'", "''")  # PowerShell single-quote escaping

    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$p=Join-Path $d '{lnk}.lnk';"
        "$w=New-Object -ComObject WScript.Shell;"
        "$s=$w.CreateShortcut($p);"
        "$s.TargetPath='{exe}';"
        "$s.Arguments='{args}';"
        "$s.WorkingDirectory='{wd}';"
        "$s.IconLocation='{icon}';"
        "$s.Save();"
        "[Console]::Out.Write($p)"
    ).format(lnk=q(safe), exe=q(target), args=q(arguments),
             wd=q(workdir), icon=q(icon))

    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace").strip()
                           or "powershell failed")
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    return out or os.path.join(os.path.expanduser("~"), "Desktop",
                               safe + ".lnk")


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
            on_error(t("Окно лоадера с заголовком «{title}» не появилось "
                       "за 30 секунд.\nПроверь поле «Заголовок окна» "
                       "в Настройках.").format(title=window_title))
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
            on_error(t("Кнопка с текстом «{btn}» не найдена в окне "
                       "лоадера.\n\nПроверь правильность текста в "
                       "Настройках → Доп настройки.\n\nСписок всех "
                       "контролов окна сохранён в:\n{path}"
                       ).format(btn=button_text, path=log_path))
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
        raise RuntimeError(t("Внешний лоадер не найден.\n"
                             "Проверь путь в Настройках → Доп настройки."))
    if not (title and button):
        raise RuntimeError(t("Не заданы заголовок окна или текст кнопки "
                             "запуска лоадера. Проверь Настройки → "
                             "Доп настройки."))

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
        raise RuntimeError(t("Wow.exe не найден:\n{exe}").format(exe=exe))

    realmlist = (char.get("realmlist") or cfg.get("realmlist")
                 or REALMLISTS_DEFAULT[0])

    deploy_patch(wow_dir)
    update_realmlist(wow_dir, realmlist)

    # Optional: snapshot WTF + AddOns in the background (throttled, ring-buffered)
    if cfg.get("backup_wtf"):
        dest_root = _backup_dest_root(cfg, wow_dir)
        try:    keep = max(1, int(cfg.get("backup_keep", 3) or 3))
        except (TypeError, ValueError): keep = 3
        try:    interval = max(0, int(cfg.get("backup_interval_min", 30) or 0)) * 60
        except (TypeError, ValueError): interval = 1800
        threading.Thread(target=_backup_game_data,
                         args=(wow_dir, dest_root, keep, interval),
                         daemon=True).start()

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
        set_lang(self.cfg.get("lang", "ru"))
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
        # Selection reads as a darkening of the row, not a colour fill
        st.map("Treeview",
               background=[("selected", SEL_BG)],
               foreground=[("selected", SEL_FG)])
        st.map("Treeview.Heading",
               background=[("active", BORDER)])

    def rebuild(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self.build()

    def build(self):
        self._apply_ttk_styles()

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(toolbar, text=t("Поиск"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        search = _make_entry(toolbar, self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(8, 12), ipady=6)
        search.bind("<KeyRelease>", lambda _e: self.render_rows())

        tk.Button(toolbar, text=t("Добавить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", padx=14, pady=7, command=self.add_char
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text=t("Изменить"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.edit_selected
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text=t("Удалить"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=7, command=self.delete_selected
                  ).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text=t("Настройки"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=14, pady=7, command=self.settings
                  ).pack(side="right")

        table_wrap = tk.Frame(self.root, bg=PANEL,
                              highlightbackground=BORDER, highlightthickness=1)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Hierarchical tree: two group rows ("Персонажи" / "Аккаунты") with the
        # entries nested under them. #0 (tree column) holds the character name.
        cols = ("class", "gs", "account", "realm", "realmlist")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text=t("Персонаж"),
                          command=lambda: self._sort_by("name"))
        self.tree.column("#0", width=180, anchor="w")
        headings = (("class",     t("Класс"),    110, "w"),
                    ("gs",        t("ГС"),         60, "center"),
                    ("account",   t("Аккаунт"),  110, "w"),
                    ("realm",     t("Реалм"),    210, "w"),
                    ("realmlist", t("Realmlist"),160, "w"))
        for col, label, w, anchor in headings:
            self.tree.heading(col, text=label,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anchor)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_activate)
        self.tree.bind("<Return>",   self._on_activate)
        # Drag-and-drop reordering (within the same group)
        self._drag_iid = None
        self._drag_moved = False
        self.tree.bind("<ButtonPress-1>",   self._on_drag_start)
        self.tree.bind("<B1-Motion>",       self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_drop)

        for cls, color in CLASS_COLORS.items():
            bg_, fg_ = _row_colors(color)
            self.tree.tag_configure(f"cls_{cls}",
                                    background=bg_, foreground=fg_)
        # Group header rows: bold-ish, muted background, not class-tinted
        self.tree.tag_configure("group", background=BORDER, foreground=TEXT)

        sb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(bottom, textvariable=self.count_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(bottom, text=t("    •    Отблагодарить:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        _hyperlink(bottom, TELEGRAM_HANDLE, TELEGRAM_URL, bg=BG
                   ).pack(side="left", padx=(2, 0))

        tk.Button(bottom, text=t("Запустить выбранного"), bg=ACCENT,
                  fg="#171717", relief="flat", padx=18, pady=8,
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

    # ── drag-and-drop reorder ───────────────────────────────────────────────

    def _on_drag_start(self, e):
        iid = self.tree.identify_row(e.y)
        self._drag_iid = iid if (iid and not iid.startswith("grp_")) else None
        self._drag_moved = False

    def _on_drag_motion(self, e):
        src = self._drag_iid
        if not src:
            return
        tgt = self.tree.identify_row(e.y)
        if not tgt or tgt.startswith("grp_") or tgt == src:
            return
        # Only reorder within the same group (same parent node)
        if self.tree.parent(tgt) != self.tree.parent(src):
            return
        # Live-move the row to the target position for instant feedback
        self.tree.move(src, self.tree.parent(src), self.tree.index(tgt))
        self._drag_moved = True

    def _on_drag_drop(self, _e):
        # Only persist when an actual drag happened — a plain click must not
        # trigger a save/re-render.
        if not self._drag_iid or not self._drag_moved:
            self._drag_iid = None
            return
        self._drag_iid = None
        self._drag_moved = False
        # Rebuild cfg["characters"] to match the current visual order. iids
        # still hold the original cfg indices until we re-render.
        new_order = []
        for grp in self.tree.get_children(""):
            for leaf in self.tree.get_children(grp):
                new_order.append(int(leaf))
        if not new_order:
            return
        chars = self.cfg["characters"]
        self.cfg["characters"] = [chars[i] for i in new_order]
        save_cfg(self.cfg)
        self._sort_state = (None, False)
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

        chars, accounts = [], []
        for idx, c in self.filtered():
            if str(c.get("name", "")).strip():
                chars.append((idx, c))
            else:
                accounts.append((idx, c))

        def add_leaf(parent, idx, c):
            tag = f"cls_{c.get('class', '')}"
            label = c.get("name", "") or c.get("account", "")
            self.tree.insert(parent, "end", iid=str(idx), text=label, values=(
                class_disp(c.get("class", "")),
                c.get("gs", ""), c.get("account", ""),
                c.get("realm", ""), c.get("realmlist", "")), tags=(tag,))

        # Accounts block first, then characters
        if accounts:
            self.tree.insert("", "end", iid="grp_acc", open=True,
                             text=t("Аккаунты"), tags=("group",))
            for idx, c in accounts:
                add_leaf("grp_acc", idx, c)
        if chars:
            self.tree.insert("", "end", iid="grp_char", open=True,
                             text=t("Персонажи"), tags=("group",))
            for idx, c in chars:
                add_leaf("grp_char", idx, c)

        self.count_var.set(t("Персонажей: {c} · Аккаунтов: {a}").format(
            c=len(chars), a=len(accounts)))
        self._refresh_tray()

    def selected_idx(self, silent=False):
        sel = self.tree.selection()
        if not sel or sel[0].startswith("grp_"):
            if not silent:
                messagebox.showinfo(APP_TITLE, t("Выбери запись в списке."))
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
            items = [pystray.MenuItem(t("Показать"), show, default=True),
                     pystray.Menu.SEPARATOR]
            for i, c in enumerate(chars[:15]):
                lbl = c.get("name", "") or c.get("account", "") or f"#{i+1}"
                items.append(pystray.MenuItem(lbl, launch_factory(i)))
            items += [pystray.Menu.SEPARATOR,
                      pystray.MenuItem(t("Выход"), quit_)]
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

    def _on_activate(self, _e=None):
        # Double-click / Enter on a group header just toggles it (default
        # behaviour) — don't nag with a "select an entry" popup.
        sel = self.tree.selection()
        if sel and sel[0].startswith("grp_"):
            return
        self.launch_selected()

    def _async_err(self, msg):
        # Worker-thread callback for async errors (loader button not found etc).
        # tkinter is single-threaded — hop back to the UI thread via after().
        self.root.after(0, lambda m=msg: messagebox.showerror(APP_TITLE, m))

    def _launch_char(self, char):
        try:
            launch_wow(self.cfg, char, on_error=self._async_err)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def launch_selected(self):
        idx = self.selected_idx()
        if idx is None:
            return
        self._launch_char(self.cfg["characters"][idx])

    def launch_by_value(self, value):
        """Launch the entry whose character name (preferred) or account login
        matches `value`. Used by desktop shortcuts and the IPC channel."""
        chars = self.cfg.get("characters", [])
        match = next((c for c in chars
                      if str(c.get("name", "")).strip() == value), None)
        if match is None:
            match = next((c for c in chars
                          if str(c.get("account", "")).strip() == value), None)
        if match is None:
            messagebox.showerror(
                APP_TITLE, t("Запись «{name}» не найдена.").format(name=value))
            return
        self._launch_char(match)

    def _launch_then_hide(self, value):
        self.launch_by_value(value)
        self._hide_to_tray()

    def delete_selected(self):
        idx = self.selected_idx()
        if idx is None:
            return
        c = self.cfg["characters"][idx]
        name = c.get("name", "") or c.get("account", "") or "?"
        if messagebox.askyesno(APP_TITLE, t("Удалить «{name}»?").format(name=name)):
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
        dlg.title(t("Запись"))
        dlg.geometry("440x760")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Запись"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")
                 ).pack(padx=20, pady=(18, 10), anchor="w")

        name_var      = tk.StringVar(value=char.get("name", ""))
        account_var   = tk.StringVar(value=char.get("account", ""))
        password_var  = tk.StringVar(value=char.get("password", ""))
        _stored_class = char.get("class", "Паладин")
        class_var     = tk.StringVar(
            value=t(NO_CLASS) if not _stored_class
            else class_disp(_stored_class))
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

        first = field(t("Ник персонажа (пусто = только аккаунт)"), name_var)
        field(t("Логин аккаунта"), account_var)
        field(t("Пароль"),         password_var, show="●")

        tk.Label(dlg, text=t("Класс"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=class_var,
                     values=[t(NO_CLASS)] + [class_disp(c) for c in WOW_CLASSES],
                     state="readonly", font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        tk.Label(dlg, text=t("ГС (Gear Score)"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        gs_row = tk.Frame(dlg, bg=BG); gs_row.pack(fill="x", padx=20)
        _make_entry(gs_row, gs_var).pack(side="left", fill="x", expand=True,
                                         ipady=5)

        def refresh_gs():
            wow = self.cfg.get("wow_path", "")
            if not wow or not os.path.isdir(wow):
                messagebox.showwarning(
                    APP_TITLE,
                    t("Сначала укажи папку с Wow.exe в Настройках."),
                    parent=dlg)
                return
            gs = read_gearscore(wow, account_var.get().strip(),
                                name_var.get().strip())
            if gs:
                gs_var.set(str(gs))
            else:
                messagebox.showinfo(
                    APP_TITLE,
                    t("ГС не найден в SavedVariables.\nПроверь, что установлен "
                      "аддон GearScore и ты заходил за этого персонажа."),
                    parent=dlg)

        tk.Button(gs_row, text="↻", bg=BTN_BG, fg=TEXT, relief="flat", padx=9,
                  command=refresh_gs
                  ).pack(side="left", padx=(6, 0), ipady=4)
        tk.Label(dlg,
                 text=t("Обновить ГС из SavedVariables (нужен аддон GearScore)"),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)
                 ).pack(fill="x", padx=20, pady=(2, 0))

        tk.Label(dlg, text=t("Реалм"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=realm_var, values=self.cfg["realms"],
                     font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        tk.Label(dlg, text=t("Realmlist"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
        ttk.Combobox(dlg, textvariable=realmlist_var,
                     values=self.cfg["realmlists"], font=("Segoe UI", 10)
                     ).pack(fill="x", padx=20, ipady=4)

        # 2FA
        tk.Label(dlg,
                 text=t("Секрет 2FA (Google / 2FAS Auth / Yandex Authenticator)"),
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
        tk.Label(dlg, text=t("Если 2FA не подключена — оставь пусто."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)
                 ).pack(fill="x", padx=20, pady=(2, 0))

        def refresh_code(*_):
            secret = totp_var.get().strip()
            if not secret:
                totp_check_var.set("")
                return
            code = compute_totp(secret)
            totp_check_var.set(code if code else t("невалидно"))
        totp_var.trace_add("write", refresh_code)
        refresh_code()

        def save():
            name = name_var.get().strip()
            account = account_var.get().strip()
            # Allow account-only entries (no character name), but require at
            # least one of the two so the row isn't completely empty.
            if not name and not account:
                messagebox.showwarning(
                    APP_TITLE,
                    t("Введи ник персонажа или логин аккаунта."), parent=dlg)
                return
            cls_disp = class_var.get().strip()
            cls = "" if cls_disp == t(NO_CLASS) else class_canon(cls_disp)
            item = {
                "name":        name,
                "account":     account,
                "password":    password_var.get(),
                "class":       cls,
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

        tk.Button(dlg, text=t("Сохранить") if editing else t("Добавить"),
                  bg=PRIMARY_BG, fg=PRIMARY_FG, relief="flat", pady=9,
                  cursor="hand2", command=save
                  ).pack(fill="x", padx=20, pady=18)

        first.focus_set()

    # ── backup settings dialog ──────────────────────────────────────────────

    def backup_settings(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title(t("Настройки бэкапа"))
        dlg.geometry("500x430")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Настройки бэкапа"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")
                 ).pack(padx=20, pady=(16, 8), anchor="w")

        keep_var     = tk.StringVar(value=str(self.cfg.get("backup_keep", 3)))
        interval_var = tk.StringVar(
            value=str(self.cfg.get("backup_interval_min", 30)))
        dir_var      = tk.StringVar(value=self.cfg.get("backup_dir", ""))

        def num_field(label, hint, var):
            r = tk.Frame(dlg, bg=BG); r.pack(fill="x", padx=20, pady=(10, 0))
            tk.Label(r, text=label, bg=BG, fg=TEXT,
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            e = _make_entry(r, var)
            e.configure(width=8)
            e.pack(side="right", ipady=3)
            tk.Label(dlg, text=hint, bg=BG, fg=MUTED, font=("Segoe UI", 8),
                     justify="left", wraplength=440, anchor="w"
                     ).pack(fill="x", padx=20, pady=(1, 0))

        num_field(
            t("Сколько копий хранить"),
            t("Хранятся N последних снимков. Когда копий становится больше — "
              "самый старый удаляется автоматически (кольцевой буфер)."),
            keep_var)
        num_field(
            t("Интервал между копиями (мин)"),
            t("Новый снимок создаётся при запуске, только если с прошлого "
              "прошло не меньше указанных минут. 0 — копировать при каждом "
              "запуске."),
            interval_var)

        tk.Label(dlg, text=t("Папка для бэкапов (пусто = папка игры)"),
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(12, 0))
        drow = tk.Frame(dlg, bg=BG); drow.pack(fill="x", padx=20, pady=(2, 0))
        _make_entry(drow, dir_var).pack(side="left", fill="x", expand=True,
                                        ipady=4)

        def browse_dir():
            p = filedialog.askdirectory(parent=dlg,
                                        title=t("Выбери папку для бэкапов"))
            if p:
                dir_var.set(os.path.normpath(p))

        tk.Button(drow, text=t("Обзор"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=10, command=browse_dir
                  ).pack(side="left", padx=(8, 0), ipady=4)

        def save():
            keep_s = keep_var.get().strip()
            int_s  = interval_var.get().strip()
            if not (keep_s.isdigit() and int_s.isdigit()):
                messagebox.showwarning(
                    APP_TITLE,
                    t("Введи число (копии и интервал должны быть числами)."),
                    parent=dlg)
                return
            dirv = dir_var.get().strip()
            # If the chosen folder isn't writable, offer to elevate once and
            # grant the current user permanent write access to it.
            if dirv and not _dir_writable(dirv):
                if messagebox.askyesno(
                        APP_TITLE,
                        t("Папка требует прав администратора. "
                          "Выдать доступ к ней?"), parent=dlg):
                    _grant_write_access(dirv)
                if not _dir_writable(dirv):
                    messagebox.showwarning(
                        APP_TITLE,
                        t("Папка по-прежнему недоступна для записи.\n"
                          "Бэкапы в неё работать не будут."), parent=dlg)
            self.cfg["backup_keep"]         = max(1, int(keep_s))
            self.cfg["backup_interval_min"] = max(0, int(int_s))
            self.cfg["backup_dir"]          = dirv
            save_cfg(self.cfg)
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=(18, 14))
        tk.Button(btn_row, text=t("Восстановить…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=12, pady=8,
                  command=lambda: self.restore_backup(dlg)
                  ).pack(side="left")
        tk.Button(btn_row, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", padx=18, pady=8, command=save
                  ).pack(side="right")

    # ── restore-from-backup dialog ──────────────────────────────────────────

    def restore_backup(self, parent):
        wow_dir = self.cfg.get("wow_path", "")
        if not wow_dir or not os.path.isdir(wow_dir):
            messagebox.showwarning(
                APP_TITLE,
                t("Папка игры (Wow.exe) не задана в Настройках."),
                parent=parent)
            return
        dest_root = _backup_dest_root(self.cfg, wow_dir)
        snaps = list(reversed(_list_snapshots(dest_root)))  # newest first
        if not snaps:
            messagebox.showinfo(APP_TITLE, t("Бэкапов пока нет."),
                                parent=parent)
            return

        dlg = tk.Toplevel(parent)
        dlg.title(t("Восстановление из бэкапа"))
        dlg.geometry("520x360")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Восстановление из бэкапа"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")
                 ).pack(padx=20, pady=(16, 8), anchor="w")

        lb = tk.Listbox(dlg, bg=ENTRY_BG, fg=TEXT, selectbackground=SEL_BG,
                        selectforeground=SEL_FG, relief="flat",
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=ACCENT, font=("Segoe UI", 10),
                        activestyle="none")
        lb.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        for sp in snaps:
            stamp = os.path.basename(sp)[len("backup_"):-len(".zip")]
            # pretty: YYYYmmdd_HHMMSS → YYYY-mm-dd HH:MM
            try:
                pretty = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.strptime(stamp, "%Y%m%d_%H%M%S"))
            except ValueError:
                pretty = stamp
            lb.insert(tk.END, f"{pretty}    ({_zip_size_str(sp)})")
        lb.selection_set(0)

        def do_restore():
            sel = lb.curselection()
            if not sel:
                return
            zip_path = snaps[sel[0]]
            if not messagebox.askyesno(
                    APP_TITLE,
                    t("Восстановить выбранный снимок поверх текущих WTF и "
                      "аддонов?\nТекущие файлы будут перезаписаны."),
                    parent=dlg):
                return
            try:
                _restore_snapshot(wow_dir, zip_path)
                messagebox.showinfo(
                    APP_TITLE,
                    t("Готово. Восстановлено из:\n{name}").format(
                        name=os.path.basename(zip_path)),
                    parent=dlg)
                dlg.destroy()
            except Exception as e:
                messagebox.showerror(
                    APP_TITLE,
                    t("Не удалось восстановить:\n{e}").format(e=e),
                    parent=dlg)

        tk.Button(dlg, text=t("Восстановить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=do_restore
                  ).pack(fill="x", padx=20, pady=(0, 14))

    # ── settings dialog ───────────────────────────────────────────────────────

    def settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("Настройки"))
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

        tk.Label(body, text=t("Настройки"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")
                 ).pack(padx=20, pady=(18, 10), anchor="w")

        # ── WoW path ─────────────────────────────────────────────────────────
        tk.Label(body, text=t("Папка с Wow.exe"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20)
        path_var = tk.StringVar(value=self.cfg.get("wow_path", ""))
        row = tk.Frame(body, bg=BG); row.pack(fill="x", padx=20, pady=(4, 12))
        _make_entry(row, path_var).pack(side="left", fill="x", expand=True,
                                        ipady=5)

        def browse():
            p = filedialog.askopenfilename(
                parent=dlg, title=t("Выбери Wow.exe"),
                filetypes=[("WoW Client", "Wow.exe"),
                           ("Exe", "*.exe"), ("All", "*.*")])
            if p:
                path_var.set(os.path.normpath(os.path.dirname(p)))

        tk.Button(row, text=t("Обзор"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=10, command=browse
                  ).pack(side="left", padx=(8, 0), ipady=5)

        # ── Realms list ──────────────────────────────────────────────────────
        tk.Label(body, text=t("Список реалмов (по строке на реалм)"), bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=20)
        realms_text = tk.Text(body, height=6, bg=ENTRY_BG, fg=TEXT,
                              relief="flat", highlightthickness=1,
                              font=("Segoe UI", 10), wrap="none")
        realms_text.configure(highlightbackground=BORDER,
                              highlightcolor=ACCENT, insertbackground=TEXT)
        realms_text.insert("1.0", "\n".join(self.cfg.get("realms", [])))
        realms_text.pack(fill="x", padx=20, pady=(2, 12))

        # ── Realmlists ───────────────────────────────────────────────────────
        tk.Label(body, text=t("Список realmlist-серверов (по строке)"), bg=BG,
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
        tk.Label(body, text=t("Конфиг"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(4, 0))
        cfg_row = tk.Frame(body, bg=BG)
        cfg_row.pack(fill="x", padx=20, pady=(2, 12))

        def load_config():
            p = filedialog.askopenfilename(
                parent=dlg, title=t("Загрузить конфиг"),
                filetypes=[("JSON", "*.json"), ("All", "*.*")])
            if not p:
                return
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    new_cfg = json.load(fh)
                if not isinstance(new_cfg, dict):
                    raise ValueError(t("файл не содержит объект конфига"))
            except Exception as e:
                messagebox.showerror(
                    APP_TITLE,
                    t("Не удалось прочитать конфиг:\n{e}").format(e=e),
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
            messagebox.showinfo(
                APP_TITLE,
                t("Загружено персонажей: {n}").format(
                    n=len(self.cfg.get("characters", []))),
                parent=dlg)
            reload_settings_dialog()

        def download_config():
            p = filedialog.asksaveasfilename(
                parent=dlg, title=t("Сохранить конфиг как…"),
                initialfile="wow_autologin_config.json",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("All", "*.*")])
            if not p:
                return
            try:
                # Export plaintext (DPAPI keys are profile-specific and useless
                # outside this PC)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
                messagebox.showinfo(APP_TITLE,
                                    t("Сохранено:\n{p}").format(p=p),
                                    parent=dlg)
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e), parent=dlg)

        def clear_config():
            if not messagebox.askyesno(
                    APP_TITLE,
                    t("Очистить весь конфиг?\nВсе персонажи и настройки будут "
                      "удалены безвозвратно."),
                    parent=dlg):
                return
            self.cfg = _default_cfg()
            save_cfg(self.cfg)
            self.render_rows()
            reload_settings_dialog()

        for txt_key, bg_, fg_, cmd in (
            ("Загрузить", BTN_BG,    TEXT,      load_config),
            ("Скачать",   BTN_BG,    TEXT,      download_config),
            ("Очистить",  "#FBE5E7", "#9A2730", clear_config),
        ):
            tk.Button(cfg_row, text=t(txt_key), bg=bg_, fg=fg_, relief="flat",
                      padx=10, pady=6, command=cmd
                      ).pack(side="left", padx=(0, 6))

        # ══ Доп настройки ════════════════════════════════════════════════════
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(8, 8))
        tk.Label(body, text=t("Доп настройки"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 11, "bold")
                 ).pack(fill="x", padx=20, pady=(0, 6))

        # ── Theme + language ─────────────────────────────────────────────────
        theme_var = tk.StringVar(value=self.cfg.get("theme", "light"))
        lang_var  = tk.StringVar(value=self.cfg.get("lang", "ru"))
        tl_row = tk.Frame(body, bg=BG); tl_row.pack(fill="x", padx=20)
        tk.Label(tl_row, text=t("Тема:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Combobox(tl_row, textvariable=theme_var,
                     values=("light", "dark"), state="readonly",
                     width=8, font=("Segoe UI", 10)
                     ).pack(side="left", padx=(8, 16), ipady=2)
        tk.Label(tl_row, text=t("Язык:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Combobox(tl_row, textvariable=lang_var,
                     values=("ru", "en"), state="readonly",
                     width=6, font=("Segoe UI", 10)
                     ).pack(side="left", padx=(8, 0), ipady=2)

        # ── Encrypt secrets toggle ───────────────────────────────────────────
        encrypt_var = tk.BooleanVar(
            value=bool(self.cfg.get("encrypt_secrets", True)))
        tk.Checkbutton(
            body, text=t("Шифровать пароли (привязать к этому ПК)"),
            variable=encrypt_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=ENTRY_BG,
            font=("Segoe UI", 9), anchor="w"
        ).pack(fill="x", padx=18, pady=(8, 0))

        backup_var = tk.BooleanVar(value=bool(self.cfg.get("backup_wtf", False)))
        backup_row = tk.Frame(body, bg=BG)
        backup_row.pack(fill="x", padx=18, pady=(2, 0))
        tk.Checkbutton(
            backup_row, text=t("Авто-бэкап WTF и аддонов при запуске"),
            variable=backup_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=ENTRY_BG,
            font=("Segoe UI", 9), anchor="w"
        ).pack(side="left")
        tk.Button(backup_row, text=t("Настроить…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.backup_settings(dlg)
                  ).pack(side="right")

        # ── Global loader (optional) ─────────────────────────────────────────
        loader_path_var  = tk.StringVar(value=self.cfg.get("loader_path", ""))
        loader_title_var = tk.StringVar(value=self.cfg.get("loader_window_title", ""))
        loader_btn_var   = tk.StringVar(value=self.cfg.get("loader_launch_button", ""))

        tk.Label(body, text=t("Внешний лоадер (необязательно — используется "
                              "для всех персонажей)"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(12, 0))

        tk.Label(body, text=t("Путь к .exe лоадера"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(6, 0))
        loader_row = tk.Frame(body, bg=BG)
        loader_row.pack(fill="x", padx=20, pady=(2, 6))
        _make_entry(loader_row, loader_path_var).pack(side="left", fill="x",
                                                      expand=True, ipady=5)

        def browse_loader():
            p = filedialog.askopenfilename(
                parent=dlg, title=t("Выбери .exe лоадера"),
                filetypes=[("Exe", "*.exe"), ("All", "*.*")])
            if p:
                loader_path_var.set(os.path.normpath(p))

        tk.Button(loader_row, text=t("Обзор"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, command=browse_loader
                  ).pack(side="left", padx=(8, 0), ipady=5)

        sub_row = tk.Frame(body, bg=BG)
        sub_row.pack(fill="x", padx=20, pady=(0, 12))
        col_l = tk.Frame(sub_row, bg=BG)
        col_l.pack(side="left", fill="x", expand=True)
        col_r = tk.Frame(sub_row, bg=BG)
        col_r.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(col_l, text=t("Заголовок окна"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(col_l, loader_title_var).pack(fill="x", ipady=4)
        tk.Label(col_r, text=t("Текст кнопки запуска"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(col_r, loader_btn_var).pack(fill="x", ipady=4)

        # ── Desktop shortcut for an entry ────────────────────────────────────
        sc_entries = [(c.get("name", "").strip() or c.get("account", "").strip())
                      for c in self.cfg.get("characters", [])]
        sc_entries = [lbl for lbl in sc_entries if lbl]
        tk.Label(body, text=t("Ярлык на рабочем столе для записи"), bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(12, 0))
        sc_row = tk.Frame(body, bg=BG)
        sc_row.pack(fill="x", padx=20, pady=(2, 8))
        sc_var = tk.StringVar(value=(sc_entries[0] if sc_entries else ""))
        ttk.Combobox(sc_row, textvariable=sc_var, values=sc_entries,
                     state="readonly", font=("Segoe UI", 10)
                     ).pack(side="left", fill="x", expand=True, ipady=2)

        def make_shortcut():
            if not sc_entries:
                messagebox.showwarning(
                    APP_TITLE, t("Сначала добавь хотя бы одну запись."),
                    parent=dlg)
                return
            val = sc_var.get().strip()
            try:
                p = create_desktop_shortcut(val, val)
                messagebox.showinfo(
                    APP_TITLE,
                    t("Ярлык создан на рабочем столе:\n{path}").format(path=p),
                    parent=dlg)
            except Exception as e:
                messagebox.showerror(
                    APP_TITLE,
                    t("Не удалось создать ярлык:\n{e}").format(e=e), parent=dlg)

        tk.Button(sc_row, text=t("Сделать ярлык"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, command=make_shortcut
                  ).pack(side="left", padx=(8, 0), ipady=2)

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
            self.cfg["encrypt_secrets"]      = bool(encrypt_var.get())
            self.cfg["backup_wtf"]           = bool(backup_var.get())
            old_theme = self.cfg.get("theme", "light")
            old_lang  = self.cfg.get("lang", "ru")
            new_theme = theme_var.get()
            new_lang  = lang_var.get()
            self.cfg["theme"] = new_theme
            self.cfg["lang"]  = new_lang
            save_cfg(self.cfg)
            dlg.destroy()
            if old_theme != new_theme or old_lang != new_lang:
                apply_theme(new_theme)
                set_lang(new_lang)
                self.rebuild()
            else:
                self.render_rows()

        tk.Button(body, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(12, 14))


# ── single-instance lock ──────────────────────────────────────────────────────
# A tiny TCP server bound to localhost acts as both the lock and the IPC
# channel: a second copy of the app probes the port, and if it answers, the
# new copy sends a "SHOW" request and exits. The running instance picks up
# the request and brings its window forward.

_SINGLE_INSTANCE_PORT = 47823     # arbitrary, picked from the private range
_MSG_SHOW   = b"WowManagerShow"
_MSG_LAUNCH = b"WowManagerLaunch:"  # followed by a utf-8 entry name/account


def _send_to_existing(msg):
    """Send `msg` to a running instance. Return True if one answered."""
    try:
        c = socket.create_connection(("127.0.0.1", _SINGLE_INSTANCE_PORT),
                                     timeout=0.5)
    except OSError:
        return False
    try:
        c.sendall(msg)
        c.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    finally:
        c.close()
    return True


def _start_single_instance_listener(on_show, on_launch):
    """Bind the lock port and dispatch SHOW / LAUNCH pings in a daemon thread."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
    except OSError:
        # Lost a startup race against another instance — defer to it.
        _send_to_existing(_MSG_SHOW)
        sys.exit(0)
    srv.listen(4)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    data = conn.recv(512)
                if data == _MSG_SHOW:
                    on_show()
                elif data.startswith(_MSG_LAUNCH):
                    on_launch(data[len(_MSG_LAUNCH):].decode("utf-8", "replace"))
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()


def _parse_launch_arg(argv):
    if "--launch" in argv:
        i = argv.index("--launch")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


if __name__ == "__main__":
    target = _parse_launch_arg(sys.argv[1:])
    msg = (_MSG_LAUNCH + target.encode("utf-8")) if target else _MSG_SHOW

    # If another instance is running, hand it the request and exit silently.
    if _send_to_existing(msg):
        sys.exit(0)

    root = tk.Tk()
    app = App(root)
    _start_single_instance_listener(
        lambda: root.after(0, app._show_window),
        lambda v: root.after(0, lambda: app.launch_by_value(v)))

    if target:
        # Shortcut launch: fire the entry, then tuck the manager into the tray.
        root.after(300, lambda: app._launch_then_hide(target))

    root.mainloop()
