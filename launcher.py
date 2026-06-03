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
import urllib.request
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

GITHUB_REPO = "Zaifat/wow-autologin"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
# TOTP breaks if the PC clock drifts past ~half a 30s window; warn beyond this.
TIME_DRIFT_WARN_SEC = 20

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
    "Запускать через внешний лоадер":
        "Launch via external loader",
    "Настройки лоадера": "Loader settings",
    "Лоадер используется для всех персонажей.":
        "The loader is used for all characters.",
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
    # hover card / columns
    "Карточка персонажа при наведении": "Character card on hover",
    "Оверлей в игре: кнопка перезахода у миникарты":
        "In-game overlay: relog button by the minimap",
    "Столбцы в списке": "Columns in the list",
    "Конструктор столбцов": "Columns builder",
    "Конструктор карточки": "Card builder",
    "Тащи ≡ для порядка. Галочка — показывать. Ширину меняй прямо в таблице "
    "за край заголовка. Точка справа — сортировать по столбцу.":
        "Drag ≡ to reorder. Checkbox — show it. Resize widths in the table by "
        "the heading edge. Right dot — sort by that column.",
    "Тащи ≡ для порядка. Галочка — показывать. Название можно менять.":
        "Drag ≡ to reorder. Checkbox — show it. Names are editable.",
    "Показ": "Show",
    "Название": "Name",
    "Ширина": "Width",
    "Сорт.": "Sort",
    "Сортировать по убыванию": "Sort descending",
    "Сбросить названия": "Reset names",
    "Ур.": "Lvl",
    "Голд": "Gold",
    "iLvl": "iLvl",
    "Аккаунт:": "Account:",
    "Реалм:": "Realm:",
    "ГС:": "GS:",
    "Голд:": "Gold:",
    "Уровень:": "Level:",
    "iLvl:": "iLvl:",
    "Наиграно:": "Played:",
    "Зона:": "Zone:",
    "Профессии:": "Professions:",
    "Валюта:": "Currency:",
    "Рейд-локауты:": "Raid lockouts:",
    "Нет данных из игры.": "No in-game data yet.",
    # banners
    "⚠ Часы ПК расходятся на {n} сек — автоввод 2FA может не работать.":
        "⚠ PC clock is off by {n}s — 2FA auto-submit may fail.",
    "Синхронизировать время": "Sync time",
    "Доступна новая версия {v}": "New version {v} is available",
    "Скачать обновление": "Download update",
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
    "Ярлык на рабочем столе для записи ([П] персонаж / [А] аккаунт)":
        "Desktop shortcut ([П] character / [А] account)",
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


def _ig(char, field, default=""):
    """In-game value for a character (from the addon's SavedVariables)."""
    rec = INGAME.get(str(char.get("name", "")).lower())
    if not rec:
        return default
    v = rec.get(field)
    return default if v is None else v


# ── universal columns ──────────────────────────────────────────────────────────
# Columns come from two sources: fixed fields of the manager record (class /
# account / realm / realmlist) and ANY field the in-game addon collected
# (level, gs, gold, honor, currencies-count, …). The settings dialog offers
# exactly the columns for which data exists.

STATIC_COLUMNS = {
    "name":      ("Персонаж",  160, "w",      lambda c: c.get("name", "")),
    "class":     ("Класс",     110, "w",      lambda c: class_disp(c.get("class", ""))),
    "account":   ("Аккаунт",   110, "w",      lambda c: c.get("account", "")),
    "realm":     ("Реалм",     200, "w",      lambda c: c.get("realm", "")),
    "realmlist": ("Realmlist", 150, "w",      lambda c: c.get("realmlist", "")),
}
# Friendly labels + numeric flag for known in-game fields
IG_LABELS = {
    "level": "Ур.", "gs": "ГС", "ilvl": "iLvl", "gold": "Голд",
    "honor": "Хонор", "arena": "Арена", "achPoints": "Очки дост.",
    "spec": "Спек", "talents": "Таланты", "guild": "Гильдия", "zone": "Зона",
    "subzone": "Подзона", "bagFree": "Слоты", "played": "Наиграно",
    "race": "Раса", "faction": "Фракция",
}
IG_NUMERIC = {"level", "gs", "ilvl", "honor", "arena", "achPoints", "bagFree"}
# Fields that are structural/meta and never offered as columns
IG_SKIP = {"name", "realm", "updated", "currencies", "locks", "profs",
           "xp", "xpMax", "rested", "class"}
IG_ORDER = ["level", "gs", "ilvl", "gold", "honor", "arena", "achPoints",
            "spec", "guild", "zone", "subzone", "bagFree", "played",
            "race", "faction"]
DEFAULT_COLUMNS = ["name", "class", "gs", "realm", "realmlist"]


# Hover-card fields: scalar in-game fields + special sections
CARD_LABELS = {
    "level": "Уровень", "gs": "ГС", "ilvl": "iLvl", "gold": "Голд",
    "honor": "Хонор", "arena": "Арена", "achPoints": "Очки дост.",
    "spec": "Спек", "talents": "Таланты", "guild": "Гильдия", "zone": "Зона",
    "subzone": "Подзона", "bagFree": "Слоты", "played": "Наиграно",
    "race": "Раса", "faction": "Фракция",
    "currencies": "Валюта", "locks": "Рейд-локауты", "profs": "Профессии",
}
CARD_ORDER = ["level", "gs", "ilvl", "gold", "honor", "arena", "achPoints",
              "spec", "talents", "guild", "zone", "subzone", "bagFree",
              "played", "race", "faction", "currencies", "locks", "profs"]
CARD_SECTIONS = {"currencies", "locks", "profs"}


def available_card_fields():
    """Card fields for which data exists across collected records."""
    present = set()
    for rec in INGAME.values():
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            if k in CARD_LABELS and v not in (None, "", [], {}):
                present.add(k)
    return [k for k in CARD_ORDER if k in present]


def card_lines(char, card_fields=None, card_labels=None):
    """Flat 'Label: value' strings describing a character's collected in-game
    data (gold / GS / level / currencies / lockouts / …). Shared by the in-game
    relog-menu tooltip; returns [] when no data was collected for the name."""
    rec = INGAME.get(str(char.get("name", "")).lower())
    if not rec:
        return []
    fields = card_fields or CARD_ORDER
    labels = card_labels or {}

    def lbl(key):
        return labels.get(key) or t(CARD_LABELS.get(key, key))

    out = []
    for key in fields:
        if key == "currencies":
            cur = rec.get("currencies") or {}
            if isinstance(cur, dict) and cur:
                out.append(lbl(key) + ":")
                for cname, cnt in list(cur.items())[:14]:
                    out.append("  %s: %s" % (cname, cnt))
        elif key == "locks":
            locks = rec.get("locks") or []
            if isinstance(locks, dict):
                locks = [v for _k, v in sorted(locks.items())]
            if locks:
                out.append(lbl(key) + ":")
                now = time.time()
                for lk in locks[:14]:
                    if not isinstance(lk, dict):
                        continue
                    left = int((lk.get("resetAt") or 0) - now)
                    cd = _fmt_dhm(left) if left > 0 else "—"
                    out.append("  %s (%s) — %s"
                               % (lk.get("name", "?"), lk.get("diff", ""), cd))
        elif key == "profs":
            profs = rec.get("profs") or []
            if isinstance(profs, dict):
                profs = [v for _k, v in sorted(profs.items())]
            if profs:
                out.append(lbl(key) + ": "
                           + ", ".join(str(p) for p in profs[:4]))
        else:
            v = rec.get(key)
            if v in (None, ""):
                continue
            if key == "gold":
                v = fmt_gold(v)
            elif key == "played":
                v = _fmt_played(v)
            out.append("%s: %s" % (lbl(key), v))
    return out


def _ig_column_getter(key):
    def g(c, k=key):
        v = _ig(c, k)
        if v == "":
            return ""
        if k == "gold":
            return fmt_gold(v)
        if k == "played":
            return _fmt_played(v)
        return v
    return g


def _cur_column_getter(name):
    def g(c, nm=name):
        rec = INGAME.get(str(c.get("name", "")).lower())
        cur = rec.get("currencies") if rec else None
        if isinstance(cur, dict):
            v = cur.get(nm)
            return v if v is not None else ""
        return ""
    return g


def col_meta(key):
    """(label, width, anchor, getter) for a column key. Keys:
       static (class/account/…), in-game field, or 'cur:<currency name>'."""
    if key in STATIC_COLUMNS:
        return STATIC_COLUMNS[key]
    if key.startswith("cur:"):
        name = key[4:]
        return (name, 90, "center", _cur_column_getter(name))
    label = IG_LABELS.get(key, key)
    if key in IG_NUMERIC:
        return (label, 60, "center", _ig_column_getter(key))
    if key == "gold":
        return (label, 95, "w", _ig_column_getter(key))
    return (label, 110, "w", _ig_column_getter(key))


def available_columns():
    """All columns for which data exists: the static ones, every scalar in-game
    field present, plus a column per distinct currency that anyone has."""
    present, currencies = set(), set()
    for rec in INGAME.values():
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            if k == "currencies" and isinstance(v, dict):
                currencies.update(v.keys())
                continue
            if k in IG_SKIP or k in STATIC_COLUMNS:
                continue
            if isinstance(v, (dict, list)) or v in (None, ""):
                continue
            present.add(k)
    ordered_ig = [k for k in IG_ORDER if k in present]
    ordered_ig += sorted(k for k in present if k not in IG_ORDER)
    cur_cols = ["cur:" + n for n in sorted(currencies)]
    return list(STATIC_COLUMNS.keys()) + ordered_ig + cur_cols


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
    "logon.wowcircle.me",
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
                  # Selection = a darkening overlay (not a colour fill)
                  SEL_BG="#33405A", SEL_FG="#FFFFFF",
                  # Primary buttons (Добавить, Сохранить, Запустить)
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
    "dark":  dict(BG="#1A1D2A", PANEL="#252A3A", BORDER="#3A3F50",
                  TEXT="#E8EBF2", MUTED="#8E96AA", HEADER="#0F1119",
                  ACCENT="#D9B95E", LINK="#7DB6E8",
                  ENTRY_BG="#1F2330", BTN_BG="#3A3F50",
                  SEL_BG="#0E1118", SEL_FG="#FFFFFF",
                  PRIMARY_BG="#D9B95E", PRIMARY_FG="#171717"),
    # WotLK-styled gold/parchment theme
    "wow":   dict(BG="#15110A", PANEL="#241D12", BORDER="#5C4A2A",
                  TEXT="#EAD9B0", MUTED="#A8946A", HEADER="#0C0905",
                  ACCENT="#E2C158", LINK="#D9B95E",
                  ENTRY_BG="#1E180E", BTN_BG="#4A3B22",
                  SEL_BG="#6B5526", SEL_FG="#FFF3D0",
                  PRIMARY_BG="#E2C158", PRIMARY_FG="#1A1206"),
}

CURRENT_THEME = "light"

# Module-level colour vars get rebound by apply_theme()
BG = PANEL = BORDER = TEXT = MUTED = HEADER = ACCENT = LINK = "#000"
ENTRY_BG = BTN_BG = SEL_BG = SEL_FG = "#000"
PRIMARY_BG = PRIMARY_FG = "#000"

def apply_theme(name):
    global BG, PANEL, BORDER, TEXT, MUTED, HEADER, ACCENT, LINK
    global ENTRY_BG, BTN_BG, SEL_BG, SEL_FG
    global PRIMARY_BG, PRIMARY_FG, CURRENT_THEME
    t = THEMES.get(name, THEMES["light"])
    CURRENT_THEME                    = name if name in THEMES else "light"
    BG, PANEL, BORDER, TEXT, MUTED   = t["BG"], t["PANEL"], t["BORDER"], t["TEXT"], t["MUTED"]
    HEADER, ACCENT, LINK             = t["HEADER"], t["ACCENT"], t["LINK"]
    ENTRY_BG, BTN_BG                 = t["ENTRY_BG"], t["BTN_BG"]
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

def _detect_os_lang():
    """Default UI language from the OS: Russian → 'ru', anything else → 'en'."""
    try:
        if sys.platform == "win32":
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "ru" if (lid & 0x3FF) == 0x19 else "en"   # 0x19 = Russian
    except Exception:
        pass
    try:
        import locale
        loc = (locale.getdefaultlocale()[0] or "")
        return "ru" if loc.lower().startswith("ru") else "en"
    except Exception:
        return "en"


def _default_cfg():
    return {
        "wow_path":             r"E:\WOW",
        "realmlist":            REALMLISTS_DEFAULT[0],
        "realms":               list(REALMS_DEFAULT),
        "realmlists":           list(REALMLISTS_DEFAULT),
        "characters":           [],
        "theme":                "light",   # "light" | "dark"
        "lang":                 _detect_os_lang(),  # auto by OS on first run
        # Encrypt passwords / 2FA secrets at rest with Windows DPAPI (bound to
        # this PC + user). Turn off to store them as plaintext (portable).
        "encrypt_secrets":      True,
        # Snapshot the game's WTF folder + Interface/AddOns before launch.
        "backup_wtf":           False,
        "backup_keep":          3,    # ring buffer size
        "backup_interval_min":  30,   # min minutes between snapshots
        "backup_dir":           "",   # empty = <wow_dir>/_WowManagerBackups
        # UI extras
        "hover_card":           True,    # info card on row hover (deploys addon)
        "overlay":              False,   # in-game minimap relog button
        # Columns: ordered keys + per-column label/width overrides + sort
        "columns":              ["class", "gs", "account", "realm", "realmlist"],
        "column_labels":        {},      # key -> custom heading text
        "column_widths":        {},      # key -> px width
        "sort":                 {},      # {"col": key, "reverse": bool}
        # Hover card: ordered field keys + per-field label overrides
        "card_fields":          ["level", "gs", "ilvl", "gold", "zone",
                                 "played", "currencies", "locks", "profs"],
        "card_labels":          {},      # key -> custom label
        # Window state
        "win_geometry":         "",      # last "WxH+X+Y"
        "sash_pos":             0,       # accounts-table divider position (px)
        # Optional external loader used for ALL characters (enable with
        # `use_loader`). If off, characters launch WoW.exe directly.
        "use_loader":           False,
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

    # Migrate: older builds enabled the loader whenever loader_path was set.
    # Preserve that for users upgrading from before the use_loader flag.
    if "use_loader" not in cfg and (cfg.get("loader_path") or "").strip():
        cfg["use_loader"] = True
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


def _file_hash(path):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def deploy_patch(wow_dir):
    src_dll = _bundled(AWESOME_DLL)
    if not os.path.isfile(src_dll):
        raise RuntimeError(t("В программу не зашит {dll}").format(dll=AWESOME_DLL))
    dst_dll = os.path.join(wow_dir, AWESOME_DLL)
    # Re-deploy whenever the deployed DLL differs by CONTENT (not just size) —
    # a size-only check could leave a stale DLL in place (e.g. one without
    # 2FA/totp support), which silently breaks token entry.
    if (not os.path.isfile(dst_dll)
            or _file_hash(dst_dll) != _file_hash(src_dll)):
        try:
            shutil.copy2(src_dll, dst_dll)
        except OSError:
            pass  # DLL is loaded by a running client — keep the existing one
    wow_exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(wow_exe):
        raise RuntimeError(t("Не найден Wow.exe в {dir}").format(dir=wow_dir))
    if not is_wow_patched(wow_exe):
        patch_wow_exe(wow_exe)


def update_realmlist(wow_dir, realmlist):
    with open(os.path.join(wow_dir, "realmlist.wtf"), "w", encoding="ascii") as f:
        f.write(f"set realmlist {realmlist}\n")


# ── WowManager addon: deploy + read its SavedVariables ─────────────────────────

ADDON_NAME = "WowManager"
ADDON_SV_FILE = "WowManager.lua"
INGAME = {}   # name(lower) -> collected data dict, filled from the addon's SV


def _addon_src_dir():
    """Folder holding the bundled addon source (Interface/AddOns/WowManager)."""
    for base in (os.path.dirname(os.path.abspath(sys.argv[0])),
                 os.path.dirname(os.path.abspath(sys.executable)),
                 os.path.dirname(os.path.abspath(__file__))
                 if "__file__" in globals() else "."):
        cand = os.path.join(base, "addon", ADDON_NAME)
        if os.path.isdir(cand):
            return cand
    return None


def _lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def deploy_addon(wow_dir, enabled, show_minimap, characters=None,
                 hover_card=True, card_fields=None, card_labels=None):
    """Copy the WowManager addon into the game (or remove it). Writes Config.lua
    with the minimap-overlay flag, the hover-card flag and the manager's
    character list — including each character's class colour and a snapshot of
    its collected info — so the in-game relog menu can colour names by class and
    show the same hover card as the desktop app. Best-effort."""
    dst = os.path.join(wow_dir, "Interface", "AddOns", ADDON_NAME)
    if not enabled:
        shutil.rmtree(dst, ignore_errors=True)
        return
    src = _addon_src_dir()
    if not src:
        return
    try:
        os.makedirs(dst, exist_ok=True)
        for fn in ("WowManager.toc", "Core.lua"):
            sp = os.path.join(src, fn)
            if os.path.isfile(sp):
                shutil.copy2(sp, os.path.join(dst, fn))
        lines = ["WowManagerConfig = {",
                 "    showMinimap = %s," % ("true" if show_minimap else "false"),
                 "    hoverCard = %s," % ("true" if hover_card else "false"),
                 "    characters = {"]
        for c in (characters or []):
            nm = (c.get("name") or "").strip()
            acc = (c.get("account") or "").strip()
            label = nm or acc           # account-only entries show the account
            if not label:
                continue
            is_account = "true" if not nm else "false"
            color = CLASS_COLORS.get(c.get("class", ""), "").lstrip("#").lower()
            info = card_lines(c, card_fields, card_labels) if nm else []
            info_lua = "{ %s }" % ", ".join(_lua_str(s) for s in info)
            lines.append(
                "        { name = %s, account = %s, isAccount = %s, "
                "color = %s, info = %s },"
                % (_lua_str(label), _lua_str(acc), is_account,
                   _lua_str(color), info_lua))
        lines += ["    },", "}", ""]
        with open(os.path.join(dst, "Config.lua"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass


# ── minimal Lua-table (SavedVariables) parser ──────────────────────────────────

class _LuaReader:
    def __init__(self, s):
        self.s, self.i, self.n = s, 0, len(s)

    def _skip(self):
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("--", self.i):
                if s.startswith("--[[", self.i):
                    e = s.find("]]", self.i + 4)
                    self.i = e + 2 if e >= 0 else n
                else:
                    nl = s.find("\n", self.i)
                    self.i = nl + 1 if nl >= 0 else n
            else:
                break

    def value(self):
        self._skip()
        if self.i >= self.n:
            return None
        c = self.s[self.i]
        if c == "{":
            return self._table()
        if c in "\"'":
            return self._string()
        return self._scalar()

    def _string(self):
        q = self.s[self.i]; self.i += 1; out = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\" and self.i + 1 < self.n:
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                self.i += 2
            elif c == q:
                self.i += 1; break
            else:
                out.append(c); self.i += 1
        return "".join(out)

    def _scalar(self):
        j = self.i
        while self.i < self.n and self.s[self.i] not in ",}=]\r\n \t":
            self.i += 1
        tok = self.s[j:self.i].strip()
        if tok == "true":  return True
        if tok == "false": return False
        if tok == "nil":   return None
        try:    return int(tok)
        except ValueError:
            try:    return float(tok)
            except ValueError: return tok

    def _table(self):
        self.i += 1  # consume {
        result, array = {}, []
        while True:
            self._skip()
            if self.i >= self.n or self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[":                       # ["key"]= or [n]=
                self.i += 1
                k = self.value()
                self._skip()
                if self.i < self.n and self.s[self.i] == "]":
                    self.i += 1
                self._skip()
                if self.i < self.n and self.s[self.i] == "=":
                    self.i += 1
                result[k] = self.value()
            else:
                m = re.match(r"[A-Za-z_]\w*", self.s[self.i:])
                if m:
                    j = self.i + m.end()
                    k2 = m.group(0)
                    while j < self.n and self.s[j] in " \t":
                        j += 1
                    if (j < self.n and self.s[j] == "="
                            and (j + 1 >= self.n or self.s[j + 1] != "=")):
                        self.i = j + 1
                        result[k2] = self.value()
                        self._after_item()
                        continue
                array.append(self.value())
            self._after_item()
        if array and not result:
            return array
        for idx, v in enumerate(array, 1):
            result[idx] = v
        return result

    def _after_item(self):
        self._skip()
        if self.i < self.n and self.s[self.i] in ",;":
            self.i += 1


def parse_lua_savedvars(text):
    """Parse top-level `Name = {…}` assignments into a dict of name -> value."""
    out = {}
    for m in re.finditer(r"(?m)^(\w+)\s*=\s*", text):
        r = _LuaReader(text)
        r.i = m.end()
        try:
            out[m.group(1)] = r.value()
        except Exception:
            pass
    return out


def read_ingame_data(wow_dir, account):
    """Read WowManagerDB from the addon's account-wide SavedVariables. Returns
    {character_name_lower: data}. Empty if the addon hasn't run yet."""
    if not (wow_dir and account):
        return {}
    base = os.path.join(wow_dir, "WTF", "Account")
    out = {}
    try:
        accs = [d for d in os.listdir(base)
                if d.upper() == account.strip().upper()]
    except OSError:
        return {}
    for acc in accs:
        sv = os.path.join(base, acc, "SavedVariables", ADDON_SV_FILE)
        if not os.path.isfile(sv):
            continue
        try:
            with open(sv, "r", encoding="utf-8", errors="ignore") as f:
                data = parse_lua_savedvars(f.read())
        except OSError:
            continue
        db = data.get("WowManagerDB")
        if isinstance(db, dict):
            for key, rec in db.items():
                if isinstance(rec, dict) and rec.get("name"):
                    out[str(rec["name"]).lower()] = rec
    return out


def read_relog_request(wow_dir, account):
    """Return (char_name, at_epoch) of a pending overlay relog request, or
    (None, 0). Stored by the addon as WowManagerDB.__relog."""
    if not (wow_dir and account):
        return None, 0
    base = os.path.join(wow_dir, "WTF", "Account")
    try:
        accs = [d for d in os.listdir(base)
                if d.upper() == account.strip().upper()]
    except OSError:
        return None, 0
    for acc in accs:
        sv = os.path.join(base, acc, "SavedVariables", ADDON_SV_FILE)
        if not os.path.isfile(sv):
            continue
        try:
            with open(sv, "r", encoding="utf-8", errors="ignore") as f:
                data = parse_lua_savedvars(f.read())
        except OSError:
            continue
        db = data.get("WowManagerDB")
        if isinstance(db, dict):
            req = db.get("__relog")
            if isinstance(req, dict) and req.get("char"):
                return str(req["char"]), int(req.get("at") or 0)
    return None, 0


def is_wow_running():
    """True if a Wow.exe process is currently running (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        TH32CS_SNAPPROCESS = 0x2

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.c_ulong),
                        ("cntUsage", ctypes.c_ulong),
                        ("th32ProcessID", ctypes.c_ulong),
                        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                        ("th32ModuleID", ctypes.c_ulong),
                        ("cntThreads", ctypes.c_ulong),
                        ("th32ParentProcessID", ctypes.c_ulong),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", ctypes.c_ulong),
                        ("szExeFile", ctypes.c_char * 260)]

        k = ctypes.windll.kernel32
        snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return False
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        found = False
        if k.Process32First(snap, ctypes.byref(entry)):
            while True:
                if entry.szExeFile.lower() == b"wow.exe":
                    found = True
                    break
                if not k.Process32Next(snap, ctypes.byref(entry)):
                    break
        k.CloseHandle(snap)
        return found
    except Exception:
        return False


def fmt_gold(copper):
    """Copper int → 'Ng Ms Кc'."""
    try:
        copper = int(copper)
    except (TypeError, ValueError):
        return ""
    g, rem = divmod(copper, 10000)
    s, c = divmod(rem, 100)
    if g:
        return f"{g:,}g {s}s".replace(",", " ")
    if s:
        return f"{s}s {c}c"
    return f"{c}c"


def _fmt_dhm(secs):
    d, rem = divmod(max(0, int(secs)), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if LANG == "en":
        return (f"{d}d " if d else "") + f"{h}h {m}m"
    return (f"{d}д " if d else "") + f"{h}ч {m}м"


def _fmt_played(secs):
    try:
        secs = int(secs)
    except (TypeError, ValueError):
        return ""
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    if LANG == "en":
        return f"{d}d {h}h"
    return f"{d}д {h}ч"


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
            fh.write("Не найдено. Список всех контролов окна:\n\n")
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

    # Deploy (or remove) the data-collector / overlay addon based on settings
    addon_on = bool(cfg.get("hover_card", True) or cfg.get("overlay", False))
    deploy_addon(wow_dir, addon_on,
                 show_minimap=bool(cfg.get("overlay", False)),
                 characters=cfg.get("characters", []),
                 hover_card=bool(cfg.get("hover_card", True)),
                 card_fields=cfg.get("card_fields"),
                 card_labels=cfg.get("card_labels"))

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

    if cfg.get("use_loader") and (cfg.get("loader_path") or "").strip():
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
    if CURRENT_THEME in ("dark", "wow"):
        tr, tg, tb = (int(PANEL[1:3], 16), int(PANEL[3:5], 16),
                      int(PANEL[5:7], 16))
        a = 0.34          # subtle class hue on dark panel
    else:
        tr, tg, tb = 255, 255, 255
        a = 0.28          # subtle class hue on white — keeps text readable
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


# ── system-clock drift (TOTP depends on it) ────────────────────────────────────

def ntp_offset(hosts=("pool.ntp.org", "time.windows.com", "time.google.com"),
               timeout=3):
    """Seconds the local clock is OFF from real (NTP) time. Positive = the PC
    is behind. Returns None if no NTP server could be reached."""
    NTP_EPOCH = 2208988800  # seconds between 1900-01-01 and 1970-01-01
    packet = b"\x1b" + 47 * b"\0"
    for host in hosts:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            t0 = time.time()
            s.sendto(packet, (host, 123))
            data, _ = s.recvfrom(48)
            t3 = time.time()
            s.close()
            if len(data) < 48:
                continue
            transmit = struct.unpack("!12I", data)[10]
            server_time = transmit - NTP_EPOCH
            return server_time - (t0 + t3) / 2.0   # midpoint cancels round-trip
        except Exception:
            continue
    return None


def open_time_settings():
    """Open the Windows date/time settings page so the user can sync."""
    try:
        if sys.platform == "win32":
            os.startfile("ms-settings:dateandtime")  # noqa
        return True
    except Exception:
        try:
            subprocess.Popen(["control", "timedate.cpl"])
            return True
        except Exception:
            return False


# ── update check (GitHub Releases) ─────────────────────────────────────────────

def _ver_tuple(s):
    out = []
    for part in str(s).strip().lstrip("vV").split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out) or (0,)


def check_latest_version():
    """Return (tag, html_url) of the latest GitHub release, or (None, None)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"User-Agent": "WowManager",
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
        return data.get("tag_name"), data.get("html_url")
    except Exception:
        return None, None


def is_update_available(latest_tag):
    if not latest_tag:
        return False
    return _ver_tuple(latest_tag) > _ver_tuple(__version__)


# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        apply_theme(self.cfg.get("theme", "light"))
        set_lang(self.cfg.get("lang", "ru"))
        self.search_var = tk.StringVar()
        self.count_var  = tk.StringVar()
        self._tray_icon = None
        self._banners = {}   # kind -> dict(text, action_label, action, accent)
        self._card = None
        self._card_row = None
        root.title(APP_TITLE)
        root.geometry(self.cfg.get("win_geometry") or f"{WIN_W}x{WIN_H}")
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
        self._start_background_checks()

    # ── top banners (clock drift, updates) ──────────────────────────────────

    def _add_banner(self, kind, text, action_label=None, action=None,
                    accent="#F4C24B"):
        self._banners[kind] = dict(text=text, action_label=action_label,
                                   action=action, accent=accent)
        self.root.after(0, self._render_banners)

    def _dismiss_banner(self, kind):
        self._banners.pop(kind, None)
        self._render_banners()

    def _render_banners(self):
        area = getattr(self, "_banner_area", None)
        if not area or not area.winfo_exists():
            return
        for w in area.winfo_children():
            w.destroy()
        for kind, b in list(self._banners.items()):
            row = tk.Frame(area, bg=b["accent"])
            row.pack(fill="x")
            tk.Label(row, text=b["text"], bg=b["accent"], fg="#171717",
                     font=("Segoe UI", 9, "bold"), anchor="w"
                     ).pack(side="left", padx=(14, 8), pady=6)
            tk.Button(row, text="✕", bg=b["accent"], fg="#171717",
                      relief="flat", bd=0, padx=8,
                      command=lambda k=kind: self._dismiss_banner(k)
                      ).pack(side="right", padx=(0, 8))
            if b["action_label"] and b["action"]:
                tk.Button(row, text=b["action_label"], bg="#171717",
                          fg=b["accent"], relief="flat", padx=12, pady=2,
                          cursor="hand2", command=b["action"]
                          ).pack(side="right", padx=(0, 4), pady=4)

    def _start_background_checks(self):
        # Clock drift — TOTP auto-submit silently fails when the PC clock is off
        def _clock():
            off = ntp_offset()
            if off is not None and abs(off) > TIME_DRIFT_WARN_SEC:
                self._add_banner(
                    "time",
                    t("⚠ Часы ПК расходятся на {n} сек — автоввод 2FA может "
                      "не работать.").format(n=int(abs(off))),
                    t("Синхронизировать время"),
                    lambda: open_time_settings(),
                    accent="#F4C24B")

        # Update check — notify when a newer GitHub release exists
        def _update():
            tag, url = check_latest_version()
            if is_update_available(tag):
                self._add_banner(
                    "update",
                    t("Доступна новая версия {v}").format(v=tag),
                    t("Скачать обновление"),
                    lambda u=(url or RELEASES_URL): webbrowser.open(u),
                    accent="#7FB7E8")

        threading.Thread(target=_clock, daemon=True).start()
        threading.Thread(target=_update, daemon=True).start()
        threading.Thread(target=self._refresh_ingame, daemon=True).start()
        # Re-read in-game data when the window regains focus (after playing)
        self.root.bind("<FocusIn>", self._on_focus_in)
        # Overlay relog watcher
        self._relog_seen = int(time.time())
        threading.Thread(target=self._relog_watcher, daemon=True).start()

    def _relog_watcher(self):
        """Poll the addon for an overlay relog request; once Wow.exe has closed,
        relaunch the chosen character through the manager."""
        while True:
            time.sleep(3)
            try:
                if not self.cfg.get("overlay"):
                    continue
                wow = self.cfg.get("wow_path", "")
                if not wow or not os.path.isdir(wow):
                    continue
                accounts = {(c.get("account") or "").strip()
                            for c in self.cfg.get("characters", [])}
                target, at = None, 0
                for a in accounts:
                    if not a:
                        continue
                    tch, tat = read_relog_request(wow, a)
                    if tch and tat > at:
                        target, at = tch, tat
                if target and at > self._relog_seen and not is_wow_running():
                    self._relog_seen = at
                    self.root.after(0, lambda c=target: self.launch_by_value(c))
            except Exception:
                pass

    def _on_focus_in(self, _e=None):
        if getattr(self, "_ig_refreshing", False):
            return
        self._ig_refreshing = True
        threading.Thread(target=self._refresh_ingame, daemon=True).start()

    def _refresh_ingame(self):
        """Reload the addon's collected data for all accounts into INGAME."""
        try:
            wow = self.cfg.get("wow_path", "")
            if wow and os.path.isdir(wow):
                accounts = {(c.get("account") or "").strip()
                            for c in self.cfg.get("characters", [])}
                fresh = {}
                for a in accounts:
                    if a:
                        fresh.update(read_ingame_data(wow, a))
                INGAME.clear()
                INGAME.update(fresh)
                self.root.after(0, self.render_rows)
        finally:
            self._ig_refreshing = False

    def _apply_ttk_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Treeview",
                     background=PANEL, foreground=TEXT,
                     fieldbackground=PANEL, borderwidth=0, rowheight=22)
        # Barely-visible separators between column headers only
        st.configure("Treeview.Heading",
                     background=BORDER, foreground=TEXT, borderwidth=1,
                     relief="groove", font=("Segoe UI", 9, "bold"))
        # Selection reads as a darkening of the row, not a colour fill
        st.map("Treeview",
               background=[("selected", SEL_BG)],
               foreground=[("selected", SEL_FG)])
        st.map("Treeview.Heading",
               background=[("active", BORDER)])

    def _save_window_state(self):
        try:
            self.cfg["win_geometry"] = self.root.geometry()
            if getattr(self, "_acc_in_pane", False):
                self.cfg["sash_pos"] = self._paned.sashpos(0)
            save_cfg(self.cfg)
        except Exception:
            pass

    def rebuild(self):
        self._save_window_state()
        self._hide_card()
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self.build()

    def build(self):
        self._apply_ttk_styles()

        # Banner strip at the very top (clock-drift / update notices)
        self._banner_area = tk.Frame(self.root, bg=BG)
        self._banner_area.pack(fill="x", side="top")
        self._render_banners()

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

        # ── Characters table (configurable columns) ──────────────────────────
        self._cols = [c for c in self.cfg.get("columns", DEFAULT_COLUMNS)
                      if c] or list(DEFAULT_COLUMNS)
        labels = self.cfg.get("column_labels", {})
        widths = self.cfg.get("column_widths", {})

        # Vertical paned window → the divider between the two tables can be
        # dragged to resize the accounts table.
        paned = ttk.PanedWindow(self.root, orient="vertical")
        paned.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        self._paned = paned

        table_wrap = tk.Frame(paned, bg=PANEL,
                              highlightbackground=BORDER, highlightthickness=1)
        paned.add(table_wrap, weight=4)

        self.tree = ttk.Treeview(table_wrap, columns=tuple(self._cols),
                                 show="headings", selectmode="browse")
        for col in self._cols:
            default_label, w, anchor, _getter = col_meta(col)
            self.tree.heading(col, text=(labels.get(col) or t(default_label)))
            self.tree.column(col, width=int(widths.get(col, w)), anchor=anchor,
                             stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Configure>", self._fit_columns)
        self.tree.bind("<Double-1>", self._on_activate)
        self.tree.bind("<Return>",   self._on_activate)
        self._drag_iid = None
        self._drag_moved = False
        self.tree.bind("<ButtonPress-1>",   self._on_drag_start)
        self.tree.bind("<B1-Motion>",       self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_drop)
        self._card = None
        self._card_row = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>",  lambda _e: self._hide_card())
        self.tree.bind("<ButtonPress-1>", lambda _e: self._hide_card(), add="+")
        self.tree.bind("<Button-1>",
                       lambda e: self._table_click(self.tree, e), add="+")
        # Focus-follows-mouse: the table under the cursor becomes active right
        # away, so a single click selects a row (no "activating" first click).
        self.tree.bind("<Enter>", lambda _e: self._activate_table(self.tree))
        self.tree.bind("<<TreeviewSelect>>",
                       lambda _e: self._strip_focus_ring(self.tree), add="+")
        self.tree.bind("<ButtonRelease-1>", self._save_col_widths, add="+")

        for cls, color in CLASS_COLORS.items():
            bg_, fg_ = _row_colors(color)
            self.tree.tag_configure(f"cls_{cls}",
                                    background=bg_, foreground=fg_)

        sb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        # ── Accounts table (separate pane: login / realm / server) ────────────
        # Added to / removed from the paned window in render_rows.
        self._acc_cols = ("account", "realm", "realmlist")
        acc_wrap = tk.Frame(paned, bg=PANEL,
                            highlightbackground=BORDER, highlightthickness=1)
        self._acc_wrap = acc_wrap
        self._acc_in_pane = False
        self._sash_restored = False
        self.acc_tree = ttk.Treeview(acc_wrap, columns=self._acc_cols,
                                     show="headings", selectmode="browse",
                                     height=6)
        self.acc_tree.heading("account",   text=t("Аккаунт"))
        self.acc_tree.heading("realm",     text=t("Реалм"))
        self.acc_tree.heading("realmlist", text=t("Realmlist"))
        self.acc_tree.column("account",   width=160, anchor="w")
        self.acc_tree.column("realm",     width=240, anchor="w")
        self.acc_tree.column("realmlist", width=180, anchor="w", stretch=True)
        self.acc_tree.pack(side="left", fill="both", expand=True)
        self.acc_tree.bind("<Double-1>", self._on_activate)
        self.acc_tree.bind("<Return>",   self._on_activate)
        self.acc_tree.bind("<Button-1>",
                           lambda e: self._table_click(self.acc_tree, e), add="+")
        self.acc_tree.bind("<Enter>",
                           lambda _e: self._activate_table(self.acc_tree))
        self.acc_tree.bind("<<TreeviewSelect>>",
                           lambda _e: self._strip_focus_ring(self.acc_tree),
                           add="+")
        acc_sb = ttk.Scrollbar(acc_wrap, orient="vertical",
                               command=self.acc_tree.yview)
        acc_sb.pack(side="right", fill="y")
        self.acc_tree.configure(yscrollcommand=acc_sb.set)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=16, pady=(4, 10))
        self._bottom = bottom

        tk.Label(bottom, textvariable=self.count_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(bottom, text=t("    •    Отблагодарить:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        _hyperlink(bottom, TELEGRAM_HANDLE, TELEGRAM_URL, bg=BG
                   ).pack(side="left", padx=(2, 0))

        # Theme + language switchers (live here, not in Settings)
        lang_var = tk.StringVar(value=LANG)
        theme_var = tk.StringVar(value=CURRENT_THEME)

        def _on_lang(_e=None):
            new = lang_var.get()
            if new != self.cfg.get("lang"):
                self.cfg["lang"] = new
                save_cfg(self.cfg)
                set_lang(new)
                self.rebuild()

        def _on_theme(_e=None):
            new = theme_var.get()
            if new != self.cfg.get("theme"):
                self.cfg["theme"] = new
                save_cfg(self.cfg)
                apply_theme(new)
                self.rebuild()

        lang_cb = ttk.Combobox(bottom, textvariable=lang_var,
                               values=("ru", "en"), state="readonly",
                               width=4, font=("Segoe UI", 9))
        lang_cb.pack(side="right", padx=(8, 12))
        lang_cb.bind("<<ComboboxSelected>>", _on_lang)
        tk.Label(bottom, text=t("Язык:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right")

        theme_cb = ttk.Combobox(bottom, textvariable=theme_var,
                                values=("light", "dark", "wow"),
                                state="readonly", width=6, font=("Segoe UI", 9))
        theme_cb.pack(side="right", padx=(8, 14))
        theme_cb.bind("<<ComboboxSelected>>", _on_theme)
        tk.Label(bottom, text=t("Тема:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right")

        self.render_rows()

    def _fit_columns(self, _e=None):
        """Auto-fit columns to the table width: shrink proportionally when the
        configured widths would overflow, else give spare space to the last
        column. Display-only — does not change the saved widths."""
        try:
            avail = self.tree.winfo_width()
            if avail <= 1 or not self._cols:
                return
            wcfg = self.cfg.get("column_widths", {})
            desired = [int(wcfg.get(c, col_meta(c)[1])) for c in self._cols]
            total = sum(desired)
            if total <= avail:
                extra = avail - total
                for i, col in enumerate(self._cols):
                    w = desired[i] + (extra if i == len(self._cols) - 1 else 0)
                    self.tree.column(col, width=w)
            else:
                scale = avail / total
                for i, col in enumerate(self._cols):
                    self.tree.column(col, width=max(28, int(desired[i] * scale)))
        except Exception:
            pass

    def _save_col_widths(self, _e=None):
        """Persist column widths only when the user dragged a heading edge."""
        if not getattr(self, "_resizing", False):
            return
        self._resizing = False
        try:
            widths = dict(self.cfg.get("column_widths", {}))
            changed = False
            for col in self._cols:
                cur = self.tree.column(col, "width")
                if widths.get(col) != cur:
                    widths[col] = cur; changed = True
            if changed:
                self.cfg["column_widths"] = widths
                save_cfg(self.cfg)
        except Exception:
            pass

    # ── sort key (configured in the columns constructor) ────────────────────

    def _sorted_items(self, items):
        """Apply the configured default sort to (idx, char) pairs, if any."""
        srt = self.cfg.get("sort") or {}
        col = srt.get("col")
        if not col:
            return items
        numeric = col in IG_NUMERIC or col == "gold" or col.startswith("cur:")

        def _key(pair):
            c = pair[1]
            if col == "name":
                v = c.get("name", "")
            elif col in STATIC_COLUMNS:
                v = c.get(col, "")
            else:
                v = col_meta(col)[3](c)
            if numeric:
                digits = "".join(ch for ch in str(v) if ch.isdigit())
                return int(digits) if digits else 0
            return str(v).lower()
        return sorted(items, key=_key, reverse=bool(srt.get("reverse")))

    # ── drag-and-drop reorder ───────────────────────────────────────────────

    def _on_drag_start(self, e):
        # heading-edge drag = column resize (so we persist widths on release)
        self._resizing = (self.tree.identify_region(e.x, e.y) == "separator")
        iid = self.tree.identify_row(e.y)
        self._drag_iid = iid or None
        self._drag_moved = False

    def _on_drag_motion(self, e):
        src = self._drag_iid
        if not src:
            return
        tgt = self.tree.identify_row(e.y)
        if not tgt or tgt == src:
            return
        # Live-move the row to the target position for instant feedback
        self.tree.move(src, "", self.tree.index(tgt))
        self._drag_moved = True

    def _on_drag_drop(self, _e):
        if not self._drag_iid or not self._drag_moved:
            self._drag_iid = None
            return
        self._drag_iid = None
        self._drag_moved = False
        # Reorder character entries to match the visual order; keep account
        # entries (in the separate table) in their original positions.
        visual = [int(iid) for iid in self.tree.get_children("")]
        if not visual:
            return
        chars_list = self.cfg["characters"]
        char_positions = [i for i, c in enumerate(chars_list)
                          if str(c.get("name", "")).strip()]
        reordered = [chars_list[i] for i in visual]
        result = list(chars_list)
        for pos, c in zip(char_positions, reordered):
            result[pos] = c
        self.cfg["characters"] = result
        save_cfg(self.cfg)
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
        for it in self.acc_tree.get_children():
            self.acc_tree.delete(it)

        chars, accounts = [], []
        for idx, c in self._sorted_items(self.filtered()):
            if str(c.get("name", "")).strip():
                chars.append((idx, c))
            else:
                accounts.append((idx, c))

        for idx, c in chars:
            tag = f"cls_{c.get('class', '')}"
            values = tuple(col_meta(col)[3](c) for col in self._cols)
            self.tree.insert("", "end", iid=str(idx), values=values, tags=(tag,))

        for idx, c in accounts:
            self.acc_tree.insert("", "end", iid=str(idx), values=(
                c.get("account", ""), c.get("realm", ""),
                c.get("realmlist", "")))

        # Show the accounts pane only when there are account-only entries.
        if accounts:
            if not self._acc_in_pane:
                self._paned.add(self._acc_wrap, weight=1)
                self._acc_in_pane = True
            # Restore the saved divider position once, after layout settles
            if not self._sash_restored:
                self._sash_restored = True
                pos = int(self.cfg.get("sash_pos") or 0)
                if pos > 0:
                    self.root.after(120, lambda p=pos:
                                    self._safe_sashpos(p))
        elif self._acc_in_pane:
            self._paned.forget(self._acc_wrap)
            self._acc_in_pane = False

        self.count_var.set(t("Персонажей: {c} · Аккаунтов: {a}").format(
            c=len(chars), a=len(accounts)))
        self._refresh_tray()

    def _safe_sashpos(self, pos):
        try:
            if self._acc_in_pane:
                self._paned.sashpos(0, pos)
        except Exception:
            pass

    def _activate_table(self, tree):
        # Give keyboard focus to whichever table the mouse is over. On Windows a
        # click on an unfocused control is otherwise "eaten" just to activate it,
        # forcing a second click to actually select a row. Grabbing focus on
        # hover removes that activating click entirely.
        try:
            if tree.focus_get() is not tree:
                tree.focus_set()
        except Exception:
            try:
                tree.focus_set()
            except Exception:
                pass
        self._strip_focus_ring(tree)

    def _strip_focus_ring(self, tree):
        # Keep keyboard focus (needed so a single click selects a row) but drop
        # the dotted/active rectangle ttk draws around the focus item — the
        # selection fill alone is enough. Cleared after idle so it runs once
        # ttk's own click handler (which sets the focus item) has finished.
        def _clear():
            try:
                tree.focus("")
            except Exception:
                pass
        try:
            tree.after_idle(_clear)
        except Exception:
            pass

    def _table_click(self, tree, e):
        # Make a single click on EITHER table select the row under the cursor
        # immediately — and drop the highlight in the other table so only one
        # row is ever selected. This kills the "extra click just selects the
        # table" behaviour when switching between the two tables.
        row = tree.identify_row(e.y)
        if not row:
            return
        tree.focus_set()
        tree.selection_set(row)
        other = self.acc_tree if tree is self.tree else self.tree
        try:
            cur = other.selection()
            if cur:
                other.selection_remove(*cur)
        except Exception:
            pass
        self._strip_focus_ring(tree)

    def selected_idx(self, silent=True):
        # Prefer the table that currently has keyboard focus (the one the user
        # last clicked); fall back to whichever has a selection.
        focused = None
        try:
            focused = self.root.focus_get()
        except Exception:
            pass
        order = ([self.acc_tree, self.tree] if focused is self.acc_tree
                 else [self.tree, self.acc_tree])
        for tr in order:
            sel = tr.selection()
            if sel:
                try:
                    return int(sel[0])
                except (ValueError, IndexError):
                    pass
        return None

    # ── hover info-card ─────────────────────────────────────────────────────

    def _hide_card(self):
        if self._card is not None:
            try:
                self._card.destroy()
            except Exception:
                pass
            self._card = None
        self._card_row = None

    def _on_tree_motion(self, e):
        if not self.cfg.get("hover_card", True):
            return
        iid = self.tree.identify_row(e.y)
        if not iid:
            self._hide_card()
            return
        if iid == self._card_row:
            return
        self._hide_card()
        try:
            idx = int(iid)
        except ValueError:
            return
        if 0 <= idx < len(self.cfg.get("characters", [])):
            c = self.cfg["characters"][idx]
            # No card for account-only entries (no character)
            if not str(c.get("name", "")).strip():
                return
            self._card_row = iid
            self._show_card(c, e.x_root + 18, e.y_root + 12)

    def _show_card(self, char, x, y):
        cls = char.get("class", "")
        color = CLASS_COLORS.get(cls, ACCENT)
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.97)
        except Exception:
            pass
        outer = tk.Frame(win, bg=color)            # class-colored border
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=PANEL)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        PX = 11
        F = ("Segoe UI", 9)
        FB = ("Segoe UI", 9, "bold")
        name = char.get("name", "") or char.get("account", "") or "—"
        head = name + (f"  ·  {class_disp(cls)}" if cls else "")
        tk.Label(body, text=head, bg=PANEL, fg=color,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=PX,
                                                     pady=(7, 3))

        def row(label, value):
            if value in (None, "", 0):
                return
            r = tk.Frame(body, bg=PANEL); r.pack(fill="x", padx=PX, pady=0)
            tk.Label(r, text=label, bg=PANEL, fg=MUTED, font=F).pack(side="left")
            tk.Label(r, text=str(value), bg=PANEL, fg=TEXT,
                     font=FB).pack(side="left", padx=(5, 0))

        rec = INGAME.get(str(char.get("name", "")).lower())
        labels = self.cfg.get("card_labels", {})

        def field_label(key):
            return labels.get(key) or t(CARD_LABELS.get(key, key))

        if not rec:
            tk.Label(body, text=t("Нет данных из игры."),
                     bg=PANEL, fg=MUTED, font=F).pack(anchor="w", padx=PX,
                                                      pady=(2, 8))
        else:
            tk.Frame(body, bg=BORDER, height=1).pack(fill="x", padx=PX,
                                                     pady=(4, 4))
            for key in self.cfg.get("card_fields", CARD_ORDER):
                if key == "currencies":
                    cur = rec.get("currencies") or {}
                    if isinstance(cur, dict) and cur:
                        tk.Label(body, text=field_label(key) + ":", bg=PANEL,
                                 fg=MUTED, font=F).pack(anchor="w", padx=PX,
                                                        pady=(4, 0))
                        for cname, cnt in list(cur.items())[:14]:
                            tk.Label(body, text=f"  {cname}: {cnt}", bg=PANEL,
                                     fg=TEXT, font=F).pack(anchor="w", padx=PX,
                                                           pady=0)
                elif key == "locks":
                    locks = rec.get("locks") or []
                    if isinstance(locks, dict):
                        locks = [v for _k, v in sorted(locks.items())]
                    if locks:
                        tk.Label(body, text=field_label(key) + ":", bg=PANEL,
                                 fg=MUTED, font=F).pack(anchor="w", padx=PX,
                                                        pady=(4, 0))
                        now = time.time()
                        for lk in locks[:14]:
                            if not isinstance(lk, dict):
                                continue
                            left = int((lk.get("resetAt") or 0) - now)
                            cd = _fmt_dhm(left) if left > 0 else "—"
                            tk.Label(body, text=f"  {lk.get('name','?')} "
                                                f"({lk.get('diff','')}) — {cd}",
                                     bg=PANEL, fg=TEXT, font=F).pack(
                                         anchor="w", padx=PX, pady=0)
                elif key == "profs":
                    profs = rec.get("profs") or []
                    if isinstance(profs, dict):
                        profs = [v for _k, v in sorted(profs.items())]
                    if profs:
                        row(field_label(key) + ":",
                            ", ".join(str(p) for p in profs[:4]))
                else:
                    v = rec.get(key)
                    if v in (None, ""):
                        continue
                    if key == "gold":
                        v = fmt_gold(v)
                    elif key == "played":
                        v = _fmt_played(v)
                    row(field_label(key) + ":", v)

        tk.Frame(body, bg=PANEL, height=5).pack()

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = min(x, sw - w - 8)
        y = min(y, sh - h - 8)
        win.geometry(f"+{x}+{y}")
        self._card = win

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
        self._save_window_state()
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
        self._save_window_state()
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self.root.destroy()

    def _on_activate(self, _e=None):
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
        self._fit_dialog(dlg, 440)

    # ── loader settings dialog ──────────────────────────────────────────────

    def loader_settings(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title(t("Настройки лоадера"))
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Настройки лоадера"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")
                 ).pack(padx=20, pady=(16, 4), anchor="w")
        tk.Label(dlg, text=t("Лоадер используется для всех персонажей."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)
                 ).pack(padx=20, anchor="w")

        path_var  = tk.StringVar(value=self.cfg.get("loader_path", ""))
        title_var = tk.StringVar(value=self.cfg.get("loader_window_title", ""))
        btn_var   = tk.StringVar(value=self.cfg.get("loader_launch_button", ""))

        tk.Label(dlg, text=t("Путь к .exe лоадера"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(10, 0))
        prow = tk.Frame(dlg, bg=BG); prow.pack(fill="x", padx=20, pady=(2, 0))
        _make_entry(prow, path_var).pack(side="left", fill="x", expand=True,
                                         ipady=5)

        def browse_loader():
            p = filedialog.askopenfilename(
                parent=dlg, title=t("Выбери .exe лоадера"),
                filetypes=[("Exe", "*.exe"), ("All", "*.*")])
            if p:
                path_var.set(os.path.normpath(p))

        tk.Button(prow, text=t("Обзор"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=10, command=browse_loader
                  ).pack(side="left", padx=(8, 0), ipady=5)

        sub = tk.Frame(dlg, bg=BG); sub.pack(fill="x", padx=20, pady=(10, 0))
        cl = tk.Frame(sub, bg=BG); cl.pack(side="left", fill="x", expand=True)
        cr = tk.Frame(sub, bg=BG); cr.pack(side="left", fill="x", expand=True,
                                          padx=(8, 0))
        tk.Label(cl, text=t("Заголовок окна"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(cl, title_var).pack(fill="x", ipady=4)
        tk.Label(cr, text=t("Текст кнопки запуска"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x")
        _make_entry(cr, btn_var).pack(fill="x", ipady=4)

        def save():
            self.cfg["loader_path"]          = path_var.get().strip()
            self.cfg["loader_window_title"]  = title_var.get().strip()
            self.cfg["loader_launch_button"] = btn_var.get().strip()
            save_cfg(self.cfg)
            dlg.destroy()

        tk.Button(dlg, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(18, 14))
        self._fit_dialog(dlg, 470)

    # ── live drag-to-reorder for constructor rows ───────────────────────────

    def _attach_drag(self, handle, item, items, rows_by_item):
        """Reorder live while dragging: as the cursor passes another row, the
        dragged row is repacked before/after it (no rebuild → smooth)."""
        def motion(e):
            frame = rows_by_item.get(id(item))
            if not frame or not frame.winfo_exists():
                return
            py = e.y_root
            for other in list(items):
                if other is item:
                    continue
                of = rows_by_item.get(id(other))
                if not of or not of.winfo_ismapped():
                    continue
                ry, rh = of.winfo_rooty(), of.winfo_height()
                if rh and ry <= py <= ry + rh:
                    ci, ti = items.index(item), items.index(other)
                    items.pop(ci)
                    items.insert(ti, item)
                    if ci < ti:
                        frame.pack_configure(after=of)
                    else:
                        frame.pack_configure(before=of)
                    break
        handle.configure(cursor="fleur")
        handle.bind("<B1-Motion>", motion)

    # ── dialog auto-fit helpers ─────────────────────────────────────────────

    def _fit_dialog(self, dlg, width):
        """Size a (non-scrolling) dialog to its content height, capped."""
        dlg.update_idletasks()
        sh = dlg.winfo_screenheight()
        h = min(int(sh * 0.92), max(200, dlg.winfo_reqheight()))
        dlg.geometry(f"{int(width)}x{h}")

    def _fit_scroll(self, dlg, body, width, extra=80):
        """Size a scrollable dialog to its content, capped to the screen."""
        dlg.update_idletasks()
        sh = dlg.winfo_screenheight()
        h = min(int(sh * 0.92), max(260, body.winfo_reqheight() + extra))
        dlg.geometry(f"{int(width)}x{h}")

    # ── scrollable dialog body helper ───────────────────────────────────────

    def _scroll_body(self, dlg):
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
        return body

    # ── columns builder ─────────────────────────────────────────────────────

    def columns_constructor(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title(t("Конструктор столбцов"))
        dlg.minsize(600, 300)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Конструктор столбцов"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(padx=20, pady=(14, 2),
                                                     anchor="w")
        tk.Label(dlg, text=t("Тащи ≡ для порядка. Галочка — показывать. "
                             "Ширину меняй прямо в таблице за край заголовка. "
                             "Точка справа — сортировать по столбцу."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=600,
                 justify="left").pack(padx=20, anchor="w", pady=(0, 6))

        body = self._scroll_body(dlg)

        avail = available_columns()
        selected = [k for k in self.cfg.get("columns", DEFAULT_COLUMNS) if k]
        for k in selected:
            if k not in avail:
                avail.append(k)
        order = selected + [k for k in avail if k not in selected]
        labels = dict(self.cfg.get("column_labels", {}))
        srt = self.cfg.get("sort", {}) or {}
        sort_var = tk.StringVar(value=srt.get("col", ""))
        rev_var = tk.BooleanVar(value=bool(srt.get("reverse")))

        items = []
        for k in order:
            items.append({
                "key": k,
                "show": tk.BooleanVar(value=(k in selected)),
                "label": tk.StringVar(value=labels.get(k) or t(col_meta(k)[0])),
            })

        rows_by_item = {}

        def make_row(it):
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", padx=20, pady=1)
            rows_by_item[id(it)] = r
            grip = tk.Label(r, text="≡", bg=BG, fg=MUTED, width=2,
                            font=("Segoe UI", 12))
            grip.pack(side="left")
            self._attach_drag(grip, it, items, rows_by_item)
            tk.Checkbutton(r, variable=it["show"], bg=BG, activebackground=BG,
                           selectcolor=ENTRY_BG).pack(side="left", padx=(2, 4))
            tk.Radiobutton(r, variable=sort_var, value=it["key"], bg=BG,
                           activebackground=BG, selectcolor=ENTRY_BG
                           ).pack(side="right")
            _make_entry(r, it["label"]).pack(side="left", fill="x",
                                             expand=True, ipady=2)

        for it in items:
            make_row(it)

        tk.Checkbutton(dlg, text=t("Сортировать по убыванию"),
                       variable=rev_var, bg=BG, fg=TEXT, activebackground=BG,
                       activeforeground=TEXT, selectcolor=ENTRY_BG,
                       font=("Segoe UI", 9), anchor="w"
                       ).pack(fill="x", padx=18, pady=(6, 0))

        def save():
            new_cols, new_labels = [], {}
            new_widths = dict(self.cfg.get("column_widths", {}))
            for it in items:
                k = it["key"]
                if it["show"].get():
                    new_cols.append(k)
                lab = it["label"].get().strip()
                if lab and lab != t(col_meta(k)[0]):
                    new_labels[k] = lab
            self.cfg["columns"] = new_cols or list(DEFAULT_COLUMNS)
            self.cfg["column_labels"] = new_labels
            self.cfg["column_widths"] = new_widths
            self.cfg["sort"] = ({"col": sort_var.get(),
                                 "reverse": bool(rev_var.get())}
                                if sort_var.get() else {})
            save_cfg(self.cfg)
            dlg.destroy()
            self.rebuild()

        tk.Button(dlg, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(8, 12))
        self._fit_scroll(dlg, body, 640, extra=150)

    # ── card builder ────────────────────────────────────────────────────────

    def card_constructor(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title(t("Конструктор карточки"))
        dlg.minsize(440, 280)
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Конструктор карточки"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(padx=20, pady=(14, 2),
                                                     anchor="w")
        tk.Label(dlg, text=t("Тащи ≡ для порядка. Галочка — показывать. "
                             "Название можно менять."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=440,
                 justify="left").pack(padx=20, anchor="w")

        body = self._scroll_body(dlg)

        avail = available_card_fields()
        selected = [k for k in self.cfg.get("card_fields", CARD_ORDER)
                    if k in CARD_LABELS]
        for k in selected:
            if k not in avail:
                avail.append(k)
        # offer every known field, selected ones first in their order
        order = selected + [k for k in CARD_ORDER if k not in selected]
        labels = dict(self.cfg.get("card_labels", {}))

        items = []
        for k in order:
            items.append({
                "key": k,
                "show": tk.BooleanVar(value=(k in selected)),
                "label": tk.StringVar(value=labels.get(k) or t(CARD_LABELS[k])),
                "has": (k in avail),
            })

        rows_by_item = {}
        for it in items:
            r = tk.Frame(body, bg=BG); r.pack(fill="x", padx=20, pady=1)
            rows_by_item[id(it)] = r
            grip = tk.Label(r, text="≡", bg=BG, fg=MUTED, width=2,
                            font=("Segoe UI", 12))
            grip.pack(side="left")
            self._attach_drag(grip, it, items, rows_by_item)
            tk.Checkbutton(r, variable=it["show"], bg=BG, activebackground=BG,
                           selectcolor=ENTRY_BG).pack(side="left", padx=(2, 4))
            if not it["has"]:
                tk.Label(r, text="—", bg=BG, fg=MUTED,
                         font=("Segoe UI", 8)).pack(side="right")
            _make_entry(r, it["label"]).pack(side="left", fill="x",
                                             expand=True, ipady=2)

        def save():
            new_fields, new_labels = [], {}
            for it in items:
                k = it["key"]
                if it["show"].get():
                    new_fields.append(k)
                lab = it["label"].get().strip()
                if lab and lab != t(CARD_LABELS[k]):
                    new_labels[k] = lab
            self.cfg["card_fields"] = new_fields
            self.cfg["card_labels"] = new_labels
            save_cfg(self.cfg)
            dlg.destroy()

        tk.Button(dlg, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(8, 12))
        self._fit_scroll(dlg, body, 480, extra=110)

    # ── backup settings dialog ──────────────────────────────────────────────

    def backup_settings(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title(t("Настройки бэкапа"))
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
        self._fit_dialog(dlg, 500)

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
        dlg.minsize(560, 360)
        dlg.resizable(False, True)
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

        # ── WoW path ─────────────────────────────────────────────────────────
        tk.Label(body, text=t("Папка с Wow.exe"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(16, 0))
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

        # ── Config management (functions; buttons are packed at the bottom) ──
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

        # ── UI extras ────────────────────────────────────────────────────────
        hover_var = tk.BooleanVar(value=bool(self.cfg.get("hover_card", True)))
        hover_row = tk.Frame(body, bg=BG)
        hover_row.pack(fill="x", padx=18, pady=(2, 0))
        tk.Checkbutton(
            hover_row, text=t("Карточка персонажа при наведении"),
            variable=hover_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=ENTRY_BG,
            font=("Segoe UI", 9), anchor="w"
        ).pack(side="left")
        tk.Button(hover_row, text=t("Настроить…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.card_constructor(dlg)
                  ).pack(side="right")

        overlay_var = tk.BooleanVar(value=bool(self.cfg.get("overlay", False)))
        tk.Checkbutton(
            body, text=t("Оверлей в игре: кнопка перезахода у миникарты"),
            variable=overlay_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=ENTRY_BG,
            font=("Segoe UI", 9), anchor="w"
        ).pack(fill="x", padx=18, pady=(2, 0))

        # ── External loader (checkbox + Configure) ───────────────────────────
        loader_var = tk.BooleanVar(value=bool(self.cfg.get("use_loader", False)))
        loader_row = tk.Frame(body, bg=BG)
        loader_row.pack(fill="x", padx=18, pady=(2, 0))
        tk.Checkbutton(
            loader_row, text=t("Запускать через внешний лоадер"),
            variable=loader_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=ENTRY_BG,
            font=("Segoe UI", 9), anchor="w"
        ).pack(side="left")
        tk.Button(loader_row, text=t("Настроить…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.loader_settings(dlg)
                  ).pack(side="right")

        # ── Columns: full builder (above shortcuts) ──────────────────────────
        cols_row = tk.Frame(body, bg=BG)
        cols_row.pack(fill="x", padx=18, pady=(0, 2))
        tk.Label(cols_row, text=t("Столбцы в списке"), bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Button(cols_row, text=t("Настроить…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.columns_constructor(dlg)
                  ).pack(side="right")

        # ── Desktop shortcut for an entry (marked char / account) ────────────
        sc_map = {}     # display label -> launch value
        for c in self.cfg.get("characters", []):
            nm = (c.get("name") or "").strip()
            acc = (c.get("account") or "").strip()
            if nm:
                disp = "[П] " + nm
                sc_map[disp] = nm
            elif acc:
                disp = "[А] " + acc
                sc_map[disp] = acc
        sc_displays = list(sc_map.keys())
        tk.Label(body, text=t("Ярлык на рабочем столе для записи ([П] персонаж "
                              "/ [А] аккаунт)"), bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=20, pady=(12, 0))
        sc_row = tk.Frame(body, bg=BG)
        sc_row.pack(fill="x", padx=20, pady=(2, 8))
        sc_var = tk.StringVar(value=(sc_displays[0] if sc_displays else ""))
        ttk.Combobox(sc_row, textvariable=sc_var, values=sc_displays,
                     state="readonly", font=("Segoe UI", 10)
                     ).pack(side="left", fill="x", expand=True, ipady=2)

        def make_shortcut():
            if not sc_displays:
                messagebox.showwarning(
                    APP_TITLE, t("Сначала добавь хотя бы одну запись."),
                    parent=dlg)
                return
            val = sc_map.get(sc_var.get(), "")
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

        # ── Config management (moved to the bottom) ──────────────────────────
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(12, 6))
        tk.Label(body, text=t("Конфиг"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=20)
        cfg_row = tk.Frame(body, bg=BG)
        cfg_row.pack(fill="x", padx=20, pady=(2, 8))
        for txt_key, bg_, fg_, cmd in (
            ("Загрузить", BTN_BG,    TEXT,      load_config),
            ("Скачать",   BTN_BG,    TEXT,      download_config),
            ("Очистить",  "#FBE5E7", "#9A2730", clear_config),
        ):
            tk.Button(cfg_row, text=t(txt_key), bg=bg_, fg=fg_, relief="flat",
                      padx=10, pady=6, command=cmd
                      ).pack(side="left", padx=(0, 6))

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
            self.cfg["use_loader"]      = bool(loader_var.get())
            self.cfg["encrypt_secrets"] = bool(encrypt_var.get())
            self.cfg["backup_wtf"]      = bool(backup_var.get())
            self.cfg["hover_card"]      = bool(hover_var.get())
            self.cfg["overlay"]         = bool(overlay_var.get())
            save_cfg(self.cfg)
            dlg.destroy()
            self.rebuild()

        tk.Button(body, text=t("Сохранить"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", pady=8, command=save
                  ).pack(fill="x", padx=20, pady=(12, 14))
        self._fit_scroll(dlg, body, 580, extra=20)


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
