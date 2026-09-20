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
import tkinter.font as tkfont
import re
import urllib.request
import webbrowser
import zipfile
from tkinter import filedialog, messagebox, ttk

__version__ = "1.7.0"


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
# Ignore a repeat launch of the same entry within this window.
LAUNCH_COOLDOWN_SEC = 10
# Shortest master password we accept.
MASTER_MIN_LEN = 6

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
    "Запись:": "Entry:",
    "Сделать ярлык": "Create shortcut",
    "Сначала добавь хотя бы одну запись.": "Add at least one entry first.",
    "Ярлык создан на рабочем столе:\n{path}":
        "Shortcut created on the desktop:\n{path}",
    "Не удалось создать ярлык:\n{e}": "Failed to create shortcut:\n{e}",
    "Запись «{name}» не найдена.": "Entry «{name}» was not found.",
    "Сначала укажи папку с Wow.exe в Настройках.":
        "Set the Wow.exe folder in Settings first.",
    "Realmlist пустой или содержит недопустимые символы: {r}":
        "The realmlist is empty or has characters that cannot be used: {r}",
    "Не удалось обновить {dll} — файл занят запущенным клиентом.\n"
    "Закрой все окна WoW и запусти снова, иначе останется старая версия "
    "патча.":
        "Could not update {dll} — a running client is holding the file.\n"
        "Close every WoW window and launch again, otherwise the old patch "
        "stays in place.",
    # secrets / master password
    "Хранение паролей:": "Password storage:",
    "Ключ Windows (этот ПК)": "Windows key (this PC)",
    "Мастер-пароль": "Master password",
    "Без шифрования": "No encryption",
    "Сменить мастер-пароль…": "Change master password…",
    "Задать мастер-пароль…": "Set master password…",
    "Мастер-пароль делает конфиг переносимым: его можно взять на другой ПК, "
    "но без пароля он бесполезен.":
        "A master password makes the config portable — you can carry it to "
        "another PC, and it is useless to anyone without the password.",
    "Введи мастер-пароль": "Enter the master password",
    "Новый мастер-пароль": "New master password",
    "Повтори пароль": "Repeat the password",
    "Пароли не совпадают.": "The passwords do not match.",
    "Пароль слишком короткий — минимум {n} символов.":
        "That password is too short — {n} characters minimum.",
    "Неверный пароль.": "Wrong password.",
    "Пароли заблокированы — мастер-пароль не введён.":
        "Passwords are locked — no master password was entered.",
    "Ввести пароль": "Enter password",
    "В игре": "In game",
    "Патч «4 ГБ памяти» для Wow.exe — меньше вылетов в ЦЛК и на БГ":
        "“4 GB” patch for Wow.exe — fewer crashes in ICC and battlegrounds",
    "Анти-АФК: персонаж не уходит в «Отошёл» и не выходит из игры через 30 "
    "минут":
        "Anti-AFK: the character never goes “Away” or gets logged out after "
        "30 minutes",
    "Общий список друзей и игнора для всех персонажей":
        "One friends and ignore list for all characters",
    "Поиск группы из чата (/wm lfg)": "Group finder from chat (/wm lfg)",
    "Собирать персонажей при входе в аккаунт":
        "Collect the account's characters when logging in",
    "Собрать данные со всех персонажей…": "Collect data for every character…",
    "Сбор данных": "Collecting data",
    "Сбор данных со всех персонажей": "Collect data for every character",
    "Менеджер сам зайдёт в каждый аккаунт и за каждого персонажа, соберёт "
    "данные и закроет игру. Клиент запускается один раз на аккаунт — "
    "персонажи переключаются внутри него.\nПока идёт сбор, не трогай игру.":
        "The manager logs into every account and character, collects the data "
        "and closes the game. The client starts once per account — characters "
        "are switched inside it.\nLeave the game alone while it runs.",
    "Аккаунтов: {a} · персонажей: {c} · примерно {m} мин":
        "Accounts: {a} · characters: {c} · about {m} min",
    "Готов к запуску": "Ready",
    "Начать": "Start",
    "Остановить": "Stop",
    "Останавливаю…": "Stopping…",
    "Остановлено.": "Stopped.",
    "Сначала закрой запущенный WoW.": "Close the running WoW first.",
    "  Клиент не запустился.": "  The client never started.",
    "Запуск идёт через внешний лоадер: не трогай его окно, пока идёт сбор.":
        "Launching through an external loader: leave its window alone while "
        "the run is going.",
    "Список персонажей восстановлен из резервной копии.":
        "The roster was recovered from the backup copy.",
    "Нет аккаунтов для сбора.": "There are no accounts to collect from.",
    "Идёт сбор данных — дождись окончания.":
        "Data collection is running — wait for it to finish.",
    "Аккаунт {n} из {total}: {login}": "Account {n} of {total}: {login}",
    "{login}: персонажей {c}": "{login}: {c} characters",
    "  Через внешний лоадер сбор не работает.":
        "  Collection doesn't work through an external loader.",
    "  Список персонажей получен.": "  Character list received.",
    "  Не уложился во время — закрываю клиент.":
        "  Took too long — closing the client.",
    "  Готово: {c}": "  Done: {c}",
    "Собрано персонажей: {c}": "Characters collected: {c}",
    "Графика при запуске": "Graphics on launch",
    "Конструктор графики": "Graphics presets",
    "Конструктор графики…": "Graphics presets…",
    "Пресет меняет только отмеченные настройки, остальные останутся как в "
    "игре.":
        "A preset only changes the settings you tick; the rest stay as they "
        "are in the game.",
    "Новый": "New",
    "Копия": "Copy",
    "(встроенный)": "(built-in)",
    "Мой пресет": "My preset",
    "{name} — копия": "{name} — copy",
    "Встроенный пресет нельзя удалить — сделай копию.":
        "A built-in preset can't be deleted — make a copy instead.",
    "Удалить пресет «{name}»?": "Delete preset «{name}»?",
    "Готово": "Done",
    "вкл": "on",
    "выкл": "off",
    "Дальность обзора": "View distance",
    "Густота травы": "Ground clutter density",
    "Дальность травы": "Ground clutter distance",
    "Детализация окружения": "Environment detail",
    "Частицы": "Particles",
    "Погода": "Weather",
    "Тени": "Shadows",
    "Эффекты заклинаний": "Spell detail",
    "Мелкие объекты": "Small objects",
    "Проецируемые текстуры": "Projected textures",
    "Ограничение FPS (0 — без него)": "FPS limit (0 = none)",
    "FPS в фоне": "FPS in background",
    "Звук": "Sound",
    "Музыка": "Music",
    "Режим окна": "Window mode",
    "Разрешение": "Resolution",
    "Полный экран": "Fullscreen",
    "Окно": "Windowed",
    "Окно без рамки": "Borderless window",
    "Как в настройках игры": "As set in the game",
    "Как у аккаунта": "Same as the account",
    "Лёгкая": "Light",
    "Минимальная, без звука (фон / твинк)":
        "Minimal, muted (background / alt window)",
    "Менеджер персонажей WOW 3.3.5a (by Zaifat)":
        "WoW 3.3.5a Character Manager (by Zaifat)",
    # account -> characters tree
    "Играть": "Play",
    "Поиск персонажа или аккаунта": "Search a character or account",
    "Аккаунт / персонаж": "Account / character",
    "Аккаунтов": "Accounts",
    "Персонажей": "Characters",
    "Без аккаунта": "No account",
    "ждёт первого входа": "waiting for first login",
    "Добавь первый аккаунт": "Add your first account",
    "Логин и пароль — персонажи подтянутся сами при первом входе в игру.":
        "Login and password — characters are picked up on your first login.",
    "Добавить аккаунт": "Add account",
    "Двойной клик или Enter — играть  ·  ПКМ — все действия":
        "Double-click or Enter — play  ·  Right-click — all actions",
    "Сортировка": "Sort by",
    "Вручную": "Manual",
    "Войти в аккаунт": "Log in to account",
    "Добавить персонажа": "Add character",
    "Изменить аккаунт": "Edit account",
    "Ярлык на рабочий стол": "Desktop shortcut",
    "Удалить аккаунт «{name}» и его персонажей ({n})?":
        "Delete account «{name}» and its characters ({n})?",
    "Показать пароль": "Show password",
    "Персонажей вводить не нужно: при первом входе в аккаунт они добавятся "
    "сами.":
        "No need to enter characters: they are added on your first login.",
    "Введи логин аккаунта.": "Enter the account login.",
    "Аккаунт «{name}» уже есть.": "Account «{name}» already exists.",
    "Аккаунт «{name}» добавлен. Войди в него — персонажи подтянутся сами.":
        "Account «{name}» added. Log in once and its characters appear.",
    "Войти": "Log in",
    "Ник персонажа": "Character name",
    "Пароль и 2FA берутся из аккаунта.":
        "Password and 2FA come from the account.",
    "Введи ник персонажа.": "Enter the character name.",
    "«{name}» уже есть на этом аккаунте.":
        "«{name}» is already on this account.",
    "Добавлены персонажи ({n}): {names}": "Characters added ({n}): {names}",
    "Уже запущена старая версия менеджера (значок в трее).\n"
    "Закрой её через меню трея и запусти программу снова.":
        "An older version of the manager is already running (tray icon).\n"
        "Close it from the tray menu and start the program again.",
    # roster export
    "Ростер для форума…": "Roster for the forum…",
    "Ростер": "Roster",
    "Формат:": "Format:",
    "Копировать": "Copy",
    "Сохранить в файл…": "Save to file…",
    "Закрыть": "Close",
    "Скопировано в буфер обмена.": "Copied to the clipboard.",
    "Нет персонажей с данными. Зайди в игру с аддоном хотя бы раз.":
        "No characters with data yet. Log in once with the addon enabled.",
    "Сохранить ростер": "Save the roster",
    # (Персонаж / Класс / Ур. are already above, with the table headings)
    "Гильдия": "Guild",
    "Профессии": "Professions",
    # WTF transfer
    "Перенос настроек…": "Copy settings…",
    "Перенос настроек персонажа": "Copy character settings",
    "Откуда:": "From:",
    "Куда (можно выбрать несколько):": "To (select one or more):",
    "Что переносить:": "What to copy:",
    "Интерфейс и бинды": "Interface and keybinds",
    "Список включённых аддонов": "Enabled addon list",
    "Макросы персонажа": "Character macros",
    "Настройки аддонов (SavedVariables)": "Addon settings (SavedVariables)",
    "Применить": "Apply",
    "Перед переносом делается бэкап WTF — его можно откатить в «Настройки → "
    "Авто-бэкап → Восстановить».":
        "A WTF snapshot is taken first — you can roll it back from "
        "Settings → Auto-backup → Restore.",
    "Сначала закрой все окна WoW — клиент перезапишет WTF при выходе.":
        "Close every WoW window first — the client rewrites WTF when it exits.",
    "Выбери источник и хотя бы одного получателя.":
        "Pick a source and at least one target.",
    "Выбери, что переносить.": "Pick what to copy.",
    "Перенести настройки «{src}» на выбранных персонажей ({n})?\n"
    "Их текущие настройки будут перезаписаны.":
        "Copy the settings of «{src}» onto the selected characters ({n})?\n"
        "Their current settings will be overwritten.",
    "Готово. Скопировано файлов: {n}": "Done. Files copied: {n}",
    "Готово, но с ошибками ({e}). Скопировано файлов: {n}":
        "Done, with errors ({e}). Files copied: {n}",
    "В папке WTF нет ни одного персонажа.":
        "There is not a single character in the WTF folder.",
    "Переношу…": "Copying…",
    "Сначала задай мастер-пароль кнопкой справа от списка.":
        "Set a master password first, with the button next to the list.",
    "Сейчас пароли заблокированы — сначала введи мастер-пароль, иначе их "
    "нечем перешифровать.":
        "The passwords are locked right now — enter the master password "
        "first, otherwise there is nothing to re-encrypt.",
    "Пароли и 2FA-секреты зашифрованы мастер-паролем.":
        "Passwords and 2FA secrets are encrypted with a master password.",
    "Мастер-пароль задан. Не потеряй его — восстановить нечем.":
        "Master password set. Do not lose it — there is no recovery.",
    "Пароли заблокированы. Введи мастер-пароль, чтобы запускать игру.":
        "Passwords are locked. Enter the master password to launch the game.",
    "Отмена": "Cancel",
    "ОК": "OK",
    # realm status
    # account summary
    "Всего золота: {g}": "Total gold: {g}",
    "Лучший ГС: {n} ({gs})": "Top GS: {n} ({gs})",
    "Наиграно: {t}": "Played: {t}",
    "Данных пока нет — зайди в игру с аддоном.":
        "No data yet — log in once with the addon enabled.",
    # weekly progress
    "Дейлики": "Dailies",
    "Арена/нед.": "Arena/wk",
    "Квесты": "Quests",
    "Команды арены": "Arena teams",
    "сброс через {t}": "resets in {t}",
    "{size} — рейтинг {r}, игр {n}": "{size} — rating {r}, {n} games",
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
    "dailyDone": "Дейлики", "arenaGames": "Арена/нед.", "questsDone": "Квесты",
}
IG_NUMERIC = {"level", "gs", "ilvl", "honor", "arena", "achPoints", "bagFree",
              "arenaGames"}
# Fields that are structural/meta and never offered as columns: either raw
# building blocks for a composite value (dailyMax feeds "7 / 25") or data the
# card renders as its own section.
IG_SKIP = {"name", "realm", "updated", "currencies", "locks", "profs",
           "xp", "xpMax", "rested", "class",
           "dailyMax", "dailyResetAt", "questsTotal", "arenaTeams"}
IG_ORDER = ["level", "gs", "ilvl", "gold", "honor", "arena", "achPoints",
            "dailyDone", "questsDone", "arenaGames",
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
    "dailyDone": "Дейлики", "arenaGames": "Арена за неделю",
    "questsDone": "Квесты готовы",
    "currencies": "Валюта", "locks": "Рейд-локауты", "profs": "Профессии",
    "arenaTeams": "Команды арены",
}
CARD_ORDER = ["level", "gs", "ilvl", "gold", "honor", "arena", "achPoints",
              "dailyDone", "questsDone", "arenaGames",
              "spec", "talents", "guild", "zone", "subzone", "bagFree",
              "played", "race", "faction",
              "currencies", "locks", "profs", "arenaTeams"]
CARD_SECTIONS = {"currencies", "locks", "profs", "arenaTeams"}


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


def entry_summary(char):
    """Compact one-liner for a character — level, gear, gold — for places that
    only have a single line to spend, like the in-game alts list."""
    rec = INGAME.get(str(char.get("name", "")).lower())
    if not rec:
        return ""
    bits = []
    lvl = rec.get("level")
    if lvl:
        bits.append(str(lvl))
    gs = rec.get("gs")
    if gs:
        bits.append("%s %s" % (t("ГС"), gs))
    gold = rec.get("gold")
    if gold:
        bits.append(fmt_gold(gold))
    # Plain ASCII only: the game's font draws "·" and "—" as garbage.
    return " - ".join(bits)


def _ig_display(rec, key, long=False):
    """Human-readable form of one collected field. `long` is the hover-card
    variant, which has room for context a narrow column can't show."""
    v = rec.get(key)
    if v in (None, ""):
        return ""
    if key == "gold":
        return fmt_gold(v)
    if key == "played":
        return _fmt_played(v)
    if key == "dailyDone":
        out = "%s / %s" % (v, rec.get("dailyMax") or 25)
        left = int((rec.get("dailyResetAt") or 0) - time.time())
        if long and left > 0:
            out += "  (%s)" % t("сброс через {t}").format(t=_fmt_dhm(left))
        return out
    if key == "questsDone":
        return "%s / %s" % (v, rec.get("questsTotal") or 0)
    return v


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
        elif key == "arenaTeams":
            teams = rec.get("arenaTeams") or []
            if isinstance(teams, dict):
                teams = [v for _k, v in sorted(teams.items())]
            rows = []
            for tm in teams:
                if not isinstance(tm, dict):
                    continue
                size = tm.get("size") or "?"
                rows.append("  " + t("{size} — рейтинг {r}, игр {n}").format(
                    size="%sx%s" % (size, size), r=int(tm.get("rating") or 0),
                    n=int(tm.get("mine") or 0)))
            if rows:
                out.append(lbl(key) + ":")
                out.extend(rows)
        else:
            v = _ig_display(rec, key, long=True)
            if v in (None, ""):
                continue
            out.append("%s: %s" % (lbl(key), v))
    return out


def _ig_column_getter(key):
    def g(c, k=key):
        rec = INGAME.get(str(c.get("name", "")).lower())
        return _ig_display(rec, k) if rec else ""
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
    # Neutral graphite with a WoW-gold accent — the default look.
    "dark":  dict(BG="#0F1115", PANEL="#16191F", BORDER="#262A33",
                  TEXT="#E7E9EE", MUTED="#8A92A3", HEADER="#16191F",
                  ACCENT="#E3B341", LINK="#7AB8FF",
                  ENTRY_BG="#1C2028", BTN_BG="#222733", BTN_HOVER="#2D3342",
                  SEL_BG="#2A3552", SEL_FG="#FFFFFF",
                  PRIMARY_BG="#E3B341", PRIMARY_FG="#17130A",
                  PRIMARY_HOVER="#F0C45A", ACC_ROW="#1B1F27"),
    "light": dict(BG="#F5F6F8", PANEL="#FFFFFF", BORDER="#E3E6EC",
                  TEXT="#1B1F27", MUTED="#6B7280", HEADER="#FFFFFF",
                  ACCENT="#B7862A", LINK="#1F6FEB",
                  ENTRY_BG="#FFFFFF", BTN_BG="#ECEEF2", BTN_HOVER="#E0E3E9",
                  SEL_BG="#DDE6FB", SEL_FG="#0B1B3F",
                  PRIMARY_BG="#1B1F27", PRIMARY_FG="#FFFFFF",
                  PRIMARY_HOVER="#343A46", ACC_ROW="#F3F5F8"),
    # WotLK gold / parchment
    "wow":   dict(BG="#15110A", PANEL="#1F190F", BORDER="#4A3B22",
                  TEXT="#EAD9B0", MUTED="#A8946A", HEADER="#1F190F",
                  ACCENT="#E2C158", LINK="#D9B95E",
                  ENTRY_BG="#1A150C", BTN_BG="#3A2E1A", BTN_HOVER="#4A3B22",
                  SEL_BG="#5C4A22", SEL_FG="#FFF3D0",
                  PRIMARY_BG="#E2C158", PRIMARY_FG="#1A1206",
                  PRIMARY_HOVER="#F0D172", ACC_ROW="#241D12"),
}
DARK_THEMES = ("dark", "wow")

CURRENT_THEME = "dark"

# Module-level colour vars get rebound by apply_theme()
BG = PANEL = BORDER = TEXT = MUTED = HEADER = ACCENT = LINK = "#000"
ENTRY_BG = BTN_BG = BTN_HOVER = SEL_BG = SEL_FG = "#000"
PRIMARY_BG = PRIMARY_FG = PRIMARY_HOVER = ACC_ROW = "#000"


def apply_theme(name):
    global BG, PANEL, BORDER, TEXT, MUTED, HEADER, ACCENT, LINK
    global ENTRY_BG, BTN_BG, BTN_HOVER, SEL_BG, SEL_FG
    global PRIMARY_BG, PRIMARY_FG, PRIMARY_HOVER, ACC_ROW, CURRENT_THEME
    t = THEMES.get(name, THEMES["dark"])
    CURRENT_THEME = name if name in THEMES else "dark"
    BG, PANEL, BORDER = t["BG"], t["PANEL"], t["BORDER"]
    TEXT, MUTED, HEADER = t["TEXT"], t["MUTED"], t["HEADER"]
    ACCENT, LINK = t["ACCENT"], t["LINK"]
    ENTRY_BG, BTN_BG, BTN_HOVER = t["ENTRY_BG"], t["BTN_BG"], t["BTN_HOVER"]
    SEL_BG, SEL_FG = t["SEL_BG"], t["SEL_FG"]
    PRIMARY_BG, PRIMARY_FG = t["PRIMARY_BG"], t["PRIMARY_FG"]
    PRIMARY_HOVER, ACC_ROW = t["PRIMARY_HOVER"], t["ACC_ROW"]


apply_theme("dark")

WIN_W = 1040
WIN_H = 640


# ── modern look: fonts, icons, window chrome ────────────────────────────────
# Windows 11 ships "Segoe UI Variable" and the "Segoe Fluent Icons" glyph
# font; Windows 10 has "Segoe UI" and "Segoe MDL2 Assets" with the same code
# points. Whatever is installed is picked once at startup.

UI_FONT = "Segoe UI"
ICON_FONT = None
ICONS = {"play": "\uE768", "add": "\uE710", "edit": "\uE70F",
         "delete": "\uE74D", "settings": "\uE713", "search": "\uE721",
         "person": "\uE77B", "people": "\uE716", "link": "\uE71B",
         "more": "\uE712", "sync": "\uE895"}
ICON_FALLBACK = {"play": "\u25B6", "add": "+", "edit": "\u270E",
                 "delete": "\u2715", "settings": "\u2699", "search": "\u2315",
                 "person": "\u25CF", "people": "\u25CF", "link": "\u2197",
                 "more": "\u22EF", "sync": "\u21BB"}


def init_fonts(root):
    global UI_FONT, ICON_FONT
    try:
        fams = set(tkfont.families(root))
    except Exception:
        return
    for f in ("Segoe UI Variable Text", "Segoe UI"):
        if f in fams:
            UI_FONT = f
            break
    for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if f in fams:
            ICON_FONT = f
            break


def font(size=10, weight="normal"):
    return (UI_FONT, size, weight)


def icon_glyph(name):
    return ICONS.get(name, "") if ICON_FONT else ICON_FALLBACK.get(name, "")


def _hwnd_of(win):
    try:
        win.update_idletasks()
        return ctypes.windll.user32.GetParent(win.winfo_id())
    except Exception:
        return 0


def virtual_screen(win):
    """(left, top, width, height) of the whole desktop across monitors."""
    if sys.platform == "win32":
        try:
            gsm = ctypes.windll.user32.GetSystemMetrics
            w, h = gsm(78), gsm(79)           # SM_CXVIRTUALSCREEN / CY
            if w > 0 and h > 0:
                return gsm(76), gsm(77), w, h  # SM_XVIRTUALSCREEN / Y
        except Exception:
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


def style_window_chrome(win, rounded=False):
    """Dark title bar to match a dark theme, and rounded corners for popups
    (Windows 11). Silently does nothing where DWM doesn't support it."""
    if sys.platform != "win32":
        return
    hwnd = _hwnd_of(win)
    if not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if CURRENT_THEME in DARK_THEMES else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE; 19 on pre-20H1 builds
        for attr in (20, 19):
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark),
                                         ctypes.sizeof(dark)) == 0:
                break
        if rounded:
            pref = ctypes.c_int(2)    # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref),
                                      ctypes.sizeof(pref))
    except Exception:
        pass


def class_text_color(cls):
    """A class colour that stays readable as text on the current background:
    WoW's priest white and rogue yellow vanish on a light theme, so bright
    colours are darkened there and dark ones lifted on dark themes."""
    col = CLASS_COLORS.get(cls)
    if not col:
        return TEXT
    r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    if CURRENT_THEME in DARK_THEMES:
        if luma < 110:
            k = 110 / max(luma, 1)
            r, g, b = (min(255, int(v * k)) for v in (r, g, b))
    elif luma > 150:
        k = 0.55
        r, g, b = (int(v * k) for v in (r, g, b))
    return "#%02X%02X%02X" % (r, g, b)


class FlatButton(tk.Frame):
    """Flat button with an optional icon glyph and hover / disabled states —
    tk.Button can't mix an icon font with a text font or restyle its hover."""

    def __init__(self, parent, text="", icon=None, command=None,
                 kind="secondary", size=10, padx=14, pady=7):
        self.kind = kind
        self._set_palette()
        super().__init__(parent, bg=self._bg, cursor="hand2")
        self.command = command
        self.enabled = True
        self._labels = []
        inner = tk.Frame(self, bg=self._bg)
        inner.pack(padx=padx, pady=pady)
        self._inner = inner
        if icon:
            f = (ICON_FONT, size) if ICON_FONT else font(size)
            lab = tk.Label(inner, text=icon_glyph(icon), font=f,
                           bg=self._bg, fg=self._fg)
            lab.pack(side="left")
            self._labels.append(lab)
        if text:
            lab = tk.Label(inner, text=text, bg=self._bg, fg=self._fg,
                           font=font(size, "bold" if kind == "primary"
                                     else "normal"))
            lab.pack(side="left", padx=(8 if icon else 0, 0))
            self._labels.append(lab)
        for w in [self, inner] + self._labels:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<ButtonRelease-1>", self._on_click)

    def _set_palette(self):
        if self.kind == "primary":
            self._bg, self._fg, self._hover = PRIMARY_BG, PRIMARY_FG, PRIMARY_HOVER
        elif self.kind == "ghost":
            self._bg, self._fg, self._hover = BG, TEXT, BTN_BG
        else:
            self._bg, self._fg, self._hover = BTN_BG, TEXT, BTN_HOVER

    def _paint(self, bg, fg):
        for w in (self, self._inner):
            w.configure(bg=bg)
        for lab in self._labels:
            lab.configure(bg=bg, fg=fg)

    def _inside(self, x, y):
        w = self.winfo_containing(x, y)
        return w is not None and (w is self or str(w).startswith(str(self) + "."))

    def _on_enter(self, _e=None):
        if self.enabled:
            self._paint(self._hover, self._fg)

    def _rest(self):
        if self.enabled:
            return self._bg, self._fg
        return (BTN_BG if self.kind == "primary" else self._bg), MUTED

    def _on_leave(self, _e=None):
        # Leave also fires when moving between the button's own children.
        if self._inside(*self.winfo_pointerxy()):
            return
        self._paint(*self._rest())

    def _on_click(self, e):
        if self.enabled and self.command and self._inside(e.x_root, e.y_root):
            self.command()

    def set_enabled(self, on):
        self.enabled = bool(on)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self._paint(*self._rest())


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
        # "account|realm|name" of characters the user removed on purpose, so
        # the automatic import from the game doesn't bring them back.
        "hidden_chars":         [],
        # logins whose row is folded in the list
        "collapsed_accounts":   [],
        "theme":                "dark",    # "dark" | "light" | "wow"
        "lang":                 _detect_os_lang(),  # auto by OS on first run
        # Encrypt passwords / 2FA secrets at rest with Windows DPAPI (bound to
        # this PC + user). Turn off to store them as plaintext (portable).
        # "dpapi" | "master" | "plain" — see the secret-storage section
        "secret_mode":          "dpapi",
        "master_salt":          "",   # base64, master mode only
        "master_check":         "",   # base64 verifier, master mode only
        # Snapshot the game's WTF folder + Interface/AddOns before launch.
        "backup_wtf":           False,
        "backup_keep":          3,    # ring buffer size
        "backup_interval_min":  30,   # min minutes between snapshots
        "backup_dir":           "",   # empty = <wow_dir>/_WowManagerBackups
        # UI extras
        "hover_card":           True,    # info card on row hover (deploys addon)
        "graphics_presets":     {},      # id -> {"name":…, "cvars": {…}}
        "laa_patch":            True,    # 4GB flag on Wow.exe (never removed)
        "anti_afk":             False,   # keep the character from going AFK
        "auto_import_chars":    True,    # add an account's characters on login
        "sync_friends":         True,    # one friends / ignore list for all alts
        "lfg":                  True,    # in-game group finder from chat
        "overlay":              False,   # in-game minimap relog button
        # Columns: ordered keys + per-column label/width overrides + sort
        "columns":              ["class", "level", "gs", "gold", "realm"],
        "column_labels":        {},      # key -> custom heading text
        "column_widths":        {},      # key -> px width
        "sort":                 {},      # {"col": key, "reverse": bool}
        # Hover card: ordered field keys + per-field label overrides
        "card_fields":          ["level", "gs", "ilvl", "gold", "zone",
                                 "played", "currencies", "locks", "profs"],
        "card_labels":          {},      # key -> custom label
        # Window state
        "win_geometry":         "",      # last "WxH+X+Y"
        # Optional external loader used for ALL characters (enable with
        # `use_loader`). If off, characters launch WoW.exe directly.
        "use_loader":           False,
        "loader_path":          "",
        "loader_window_title":  "",
        "loader_launch_button": "",
    }


# Set when load_cfg had to fall back to the backup, so the window can say so.
RECOVERED_FROM_BACKUP = [False]


def _read_cfg_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("config is not an object")
    return cfg


def secret_mode(cfg):
    mode = cfg.get("secret_mode")
    if mode in SECRET_MODES:
        return mode
    # Pre-1.5 configs only had a boolean.
    return "dpapi" if cfg.get("encrypt_secrets", True) else "plain"


def load_cfg(decrypt=True):
    if not os.path.exists(CONFIG_FILE):
        cfg = _default_cfg()
        save_cfg(cfg)
        return cfg
    # A truncated or corrupt config must not take the whole program down with
    # it — every account and password lives in this file. Fall back to the
    # previous good copy that save_cfg keeps beside it.
    cfg = None
    for path in (CONFIG_FILE, CONFIG_FILE + ".bak"):
        if not os.path.isfile(path):
            continue
        try:
            cfg = _read_cfg_file(path)
            break
        except (OSError, ValueError):
            continue
    # save_cfg writes the backup just before replacing the real file, so the
    # real file is normally the newer of the two. If it isn't — something
    # outside put an older copy back — the backup holds the newer roster.
    bak = CONFIG_FILE + ".bak"
    if cfg is not None and os.path.isfile(bak):
        try:
            if os.path.getmtime(bak) > os.path.getmtime(CONFIG_FILE) + 1:
                newer = _read_cfg_file(bak)
                if len(newer.get("characters") or []) > len(
                        cfg.get("characters") or []):
                    cfg = newer
                    RECOVERED_FROM_BACKUP[0] = True
        except (OSError, ValueError):
            pass
    if cfg is None:
        # Keep the unreadable file instead of silently overwriting it.
        try:
            os.replace(CONFIG_FILE, CONFIG_FILE + ".corrupt")
        except OSError:
            pass
        cfg = _default_cfg()

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
    cfg["secret_mode"] = secret_mode(cfg)
    cfg.pop("encrypt_secrets", None)
    normalize_roster(cfg)
    # Decrypt secrets — in-memory cfg normally holds plaintext. Master mode
    # defers this until the password has been entered.
    if decrypt:
        decrypt_cfg_secrets(cfg)
    return cfg


def save_cfg(cfg):
    # Write a copy with secrets encrypted per the configured mode; never mutate
    # the caller's cfg.
    mode = secret_mode(cfg)
    if mode == "master" and not have_master_key():
        # Nothing was unlocked this session, so the values in hand are still
        # ciphertext; encrypt_secret leaves those as they are.
        pass
    out = {k: v for k, v in cfg.items() if k != "characters"}
    out["characters"] = []
    for c in cfg.get("characters", []):
        cc = dict(c)
        for k in _SECRET_FIELDS:
            if cc.get(k):
                cc[k] = encrypt_secret(cc[k], mode)
        out["characters"].append(cc)
    # Write-then-rename: a crash (or a pulled plug) part-way through must never
    # leave a half-written characters.json, and the previous copy stays as a
    # .bak that load_cfg falls back to.
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    if os.path.isfile(CONFIG_FILE):
        try:
            shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
        except OSError:
            pass
    os.replace(tmp, CONFIG_FILE)


# ── roster model ──────────────────────────────────────────────────────────────
# Stored flat — older configs, exports, desktop shortcuts and the tray all read
# that shape — but it behaves as account → characters. The account entry (an
# entry with no character name) owns the login, password, 2FA secret and
# realmlist; each of its characters carries a copy that normalize_roster keeps
# in sync, so the launch path can keep reading one flat entry.

ACCOUNT_OWNED = ("password", "totp_secret", "realmlist")
CLASS_BY_ID = {1: "Воин", 2: "Паладин", 3: "Охотник", 4: "Разбойник",
               5: "Жрец", 6: "Рыцарь смерти", 7: "Шаман", 8: "Маг",
               9: "Чернокнижник", 11: "Друид"}


def acc_key(login):
    return (login or "").strip().lower()


def is_account_entry(e):
    return not (e.get("name") or "").strip()


def char_key(account, realm, name):
    return "|".join((acc_key(account), (realm or "").strip().lower(),
                     (name or "").strip().lower()))


def _roster_snapshot(entries):
    return json.dumps(entries, ensure_ascii=False, sort_keys=True)


def normalize_roster(cfg):
    """Bring the flat list in line with the account → characters model:

    * exactly one account entry per login (duplicates are folded together);
    * a character whose login has no account entry gets one;
    * credentials live on the account entry and are copied down to its
      characters (a legacy per-character password is lifted up first);
    * entries are grouped: each account followed by its characters, in the
      order the accounts first appear. Characters with no login go last.

    Returns True if anything changed."""
    before = _roster_snapshot(cfg.get("characters", []))
    entries = [e for e in cfg.get("characters", [])
               if isinstance(e, dict)
               and ((e.get("name") or "").strip()
                    or (e.get("account") or "").strip())]

    accounts, order = {}, []
    for e in entries:
        k = acc_key(e.get("account"))
        if not k:
            continue
        if k not in accounts:
            order.append(k)
            accounts[k] = None
        if is_account_entry(e):
            if accounts[k] is None:
                accounts[k] = e
            else:                        # duplicate account row: fold it in
                keep = accounts[k]
                for f in ACCOUNT_OWNED + ("realm",):
                    if not keep.get(f) and e.get(f):
                        keep[f] = e[f]

    chars_of = {k: [] for k in order}
    orphans = []
    for e in entries:
        if is_account_entry(e):
            continue
        k = acc_key(e.get("account"))
        (chars_of[k] if k else orphans).append(e)

    result = []
    for k in order:
        acc = accounts[k]
        chars = chars_of[k]
        if acc is None:                  # characters only: invent the account
            first = chars[0]
            acc = {"name": "", "account": (first.get("account") or "").strip(),
                   "class": "", "realm": first.get("realm", "")}
            for f in ACCOUNT_OWNED:
                acc[f] = first.get(f, "")
        for c in chars:                  # lift legacy per-character values
            for f in ACCOUNT_OWNED:
                if not acc.get(f) and c.get(f):
                    acc[f] = c[f]
        acc["class"] = ""
        for c in chars:                  # then copy the account's down
            for f in ACCOUNT_OWNED:
                c[f] = acc.get(f, "")
            c["account"] = acc.get("account", "")
            if not (c.get("realm") or "").strip():
                c["realm"] = acc.get("realm", "")
        result.append(acc)
        result.extend(chars)
    result.extend(orphans)

    cfg["characters"] = result
    hidden = cfg.get("hidden_chars")
    cfg["hidden_chars"] = hidden if isinstance(hidden, list) else []
    return _roster_snapshot(result) != before


def roster_groups(cfg):
    """[(account_index | None, account_entry | None, [(index, char), ...])]
    in display order. The None group holds characters with no login."""
    groups, by_key, orphans = [], {}, []
    for i, e in enumerate(cfg.get("characters", [])):
        k = acc_key(e.get("account"))
        if is_account_entry(e):
            g = (i, e, [])
            groups.append(g)
            by_key[k] = g
        elif k in by_key:
            by_key[k][2].append((i, e))
        else:
            orphans.append((i, e))
    if orphans:
        groups.append((None, None, orphans))
    return groups


def account_entry_for(cfg, login):
    k = acc_key(login)
    for e in cfg.get("characters", []):
        if is_account_entry(e) and acc_key(e.get("account")) == k:
            return e
    return None


def insert_character(cfg, char):
    """Place a new character right after the last entry of its account."""
    entries = cfg.setdefault("characters", [])
    k = acc_key(char.get("account"))
    last = max((i for i, e in enumerate(entries)
                if acc_key(e.get("account")) == k), default=None)
    if last is None:
        entries.append(char)
    else:
        entries.insert(last + 1, char)
    unhide_character(cfg, char)


def hide_character(cfg, char):
    key = char_key(char.get("account"), char.get("realm"), char.get("name"))
    hidden = cfg.setdefault("hidden_chars", [])
    if key not in hidden:
        hidden.append(key)


def unhide_character(cfg, char):
    key = char_key(char.get("account"), char.get("realm"), char.get("name"))
    hidden = cfg.get("hidden_chars") or []
    if key in hidden:
        hidden.remove(key)


def remove_account(cfg, login):
    """Drop an account and every character on it. Returns how many entries
    went. Its hidden-character marks go too, so re-adding the account later
    brings its characters back."""
    k = acc_key(login)
    before = len(cfg.get("characters", []))
    cfg["characters"] = [e for e in cfg.get("characters", [])
                         if acc_key(e.get("account")) != k]
    cfg["hidden_chars"] = [h for h in cfg.get("hidden_chars") or []
                           if not h.startswith(k + "|")]
    return before - len(cfg["characters"])


# ── character lists written by the patch DLL ─────────────────────────────────
# Every time the client receives a character list, AwesomeWotlkLib.dll writes
# it to <game>/WowManagerData/<login>__<realmhash>.json. That lets an account
# entered with just a login and password fill itself in on first login.

CHARLIST_DIR = "WowManagerData"


def _charlist_dir(wow_dir):
    return os.path.join(wow_dir or "", CHARLIST_DIR)


def charlist_signature(wow_dir):
    """Cheap change detector: (name, mtime, size) of every list file."""
    d = _charlist_dir(wow_dir)
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    except OSError:
        return ()
    sig = []
    for n in names:
        try:
            st = os.stat(os.path.join(d, n))
            sig.append((n, st.st_mtime, st.st_size))
        except OSError:
            pass
    return tuple(sig)


def read_char_lists(wow_dir):
    out = []
    d = _charlist_dir(wow_dir)
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return out
    for n in sorted(names):
        try:
            with open(os.path.join(d, n), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue                      # half-written or foreign — skip
        if (isinstance(data, dict) and data.get("account")
                and isinstance(data.get("chars"), list)):
            out.append(data)
    return out


def import_char_lists(cfg, lists):
    """Add characters the game reported for accounts we know. Returns the
    names added. Existing characters only get a missing class filled in;
    characters the user deleted stay deleted (see hide_character)."""
    added = []
    hidden = set(cfg.get("hidden_chars") or [])
    for data in lists:
        acc = account_entry_for(cfg, data.get("account"))
        if acc is None:
            continue                      # not ours: no password to use
        realm = (data.get("realm") or "").strip() or acc.get("realm", "")
        k = acc_key(acc.get("account"))
        for ch in data.get("chars") or []:
            if not isinstance(ch, dict):
                continue
            name = (ch.get("name") or "").strip()
            if not name:
                continue
            try:
                cls = CLASS_BY_ID.get(int(ch.get("class") or 0), "")
            except (TypeError, ValueError):
                cls = ""
            existing = None
            for e in cfg.get("characters", []):
                if (not is_account_entry(e)
                        and acc_key(e.get("account")) == k
                        and (e.get("name") or "").strip().lower() == name.lower()
                        and (not (e.get("realm") or "").strip()
                             or (e.get("realm") or "").strip().lower()
                             == realm.lower())):
                    existing = e
                    break
            if existing is not None:
                if not existing.get("class") and cls:
                    existing["class"] = cls
                continue
            if char_key(acc.get("account"), realm, name) in hidden:
                continue
            insert_character(cfg, {"name": name, "account": acc["account"],
                                   "class": cls, "realm": realm,
                                   "auto": True})
            added.append(name)
    if added:
        normalize_roster(cfg)
    return added


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


IMAGE_FILE_LARGE_ADDRESS_AWARE = 0x0020


def _coff_characteristics_offset(f):
    f.seek(0x3C)
    e_lfanew = struct.unpack("<I", f.read(4))[0]
    f.seek(e_lfanew)
    if f.read(4) != b"PE\x00\x00":
        raise ValueError("not a PE file")
    return e_lfanew + 4 + 18        # COFF header: Characteristics field


def is_large_address_aware(wow_exe):
    try:
        with open(wow_exe, "rb") as f:
            f.seek(_coff_characteristics_offset(f))
            return bool(struct.unpack("<H", f.read(2))[0]
                        & IMAGE_FILE_LARGE_ADDRESS_AWARE)
    except (OSError, ValueError, struct.error):
        return False


def ensure_large_address_aware(wow_exe):
    """The "4GB patch": let the 32-bit client use up to 4 GB instead of 2 on
    64-bit Windows, which is what stops the out-of-memory crashes in Icecrown
    and big battlegrounds. Only ever sets the flag — many clients (WoWCircle
    included) already ship with it, and it is never taken away. Returns True
    if the flag is set afterwards."""
    if is_large_address_aware(wow_exe):
        return True
    try:
        with open(wow_exe, "r+b") as f:
            off = _coff_characteristics_offset(f)
            f.seek(off)
            flags = struct.unpack("<H", f.read(2))[0]
            f.seek(off)
            f.write(struct.pack("<H", flags | IMAGE_FILE_LARGE_ADDRESS_AWARE))
        return True
    except (OSError, ValueError, struct.error):
        return False        # the client is running and holds the file


def _file_hash(path):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def deploy_patch(wow_dir, on_error=None, large_address=True):
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
            # A running client holds the DLL open. Swallowing this silently is
            # how people end up stuck on an old DLL forever — say so once.
            if on_error:
                on_error(t("Не удалось обновить {dll} — файл занят запущенным "
                           "клиентом.\nЗакрой все окна WoW и запусти снова, "
                           "иначе останется старая версия патча."
                           ).format(dll=AWESOME_DLL))
    wow_exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(wow_exe):
        raise RuntimeError(t("Не найден Wow.exe в {dir}").format(dir=wow_dir))
    if not is_wow_patched(wow_exe):
        patch_wow_exe(wow_exe)
    if large_address:
        ensure_large_address_aware(wow_exe)


def update_realmlist(wow_dir, realmlist):
    # The client reads realmlist.wtf as plain bytes, so a host name has to be
    # plain ASCII. Say so instead of raising a UnicodeError out of the middle
    # of a launch (or, worse, writing a silently mangled host name).
    clean = (realmlist or "").strip()
    if not clean or any(ord(ch) > 126 or ord(ch) < 33 for ch in clean):
        raise RuntimeError(t("Realmlist пустой или содержит недопустимые "
                             "символы: {r}").format(r=realmlist))
    with open(os.path.join(wow_dir, "realmlist.wtf"), "w", encoding="ascii") as f:
        f.write("set realmlist %s\n" % clean)


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
                 hover_card=True, card_fields=None, card_labels=None,
                 current_account="", sync_friends=True, lfg=True,
                 harvest_chars=None, harvest_wait=12):
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
                 # Which account this client is logged into. Entries on the
                 # same account can be switched to without restarting the
                 # client; the rest need the manager to relaunch Wow.exe.
                 "    currentAccount = %s," % _lua_str(current_account or ""),
                 "    syncFriends = %s," % ("true" if sync_friends else "false"),
                 "    lfg = %s," % ("true" if lfg else "false"),
                 # harvest mode: the addon walks these characters by itself
                 "    harvest = %s," % ("true" if harvest_chars else "false"),
                 "    harvestWait = %d," % int(harvest_wait),
                 "    harvestChars = { %s }," % ", ".join(
                     _lua_str(n) for n in (harvest_chars or [])),
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
            summary = entry_summary(c) if nm else ""
            lines.append(
                "        { name = %s, account = %s, realm = %s, "
                "isAccount = %s, color = %s, summary = %s, info = %s },"
                % (_lua_str(label), _lua_str(acc),
                   _lua_str((c.get("realm") or "").strip()), is_account,
                   _lua_str(color), _lua_str(summary), info_lua))
        lines += ["    },", "}", ""]
        with open(os.path.join(dst, "Config.lua"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass


# ── roster export ─────────────────────────────────────────────────────────────
# Guild officers ask for "post your alts" and people assemble it by hand. We
# already know all of it.

ROSTER_FORMATS = ("text", "bbcode", "markdown")
_ROSTER_COLS = ("Персонаж", "Класс", "Ур.", "ГС", "Гильдия", "Реалм",
                "Профессии")


def roster_rows(cfg):
    """One row per character entry: the manager's own fields plus whatever the
    addon collected. Account-only entries have nothing to show, so they are
    left out."""
    rows = []
    for c in cfg.get("characters", []):
        name = (c.get("name") or "").strip()
        if not name:
            continue
        rec = INGAME.get(name.lower()) or {}
        profs = rec.get("profs") or []
        if isinstance(profs, dict):
            profs = [v for _k, v in sorted(profs.items())]
        rows.append([
            name,
            class_disp(c.get("class", "")) or "",
            str(rec.get("level") or ""),
            str(rec.get("gs") or ""),
            str(rec.get("guild") or ""),
            (c.get("realm") or "").strip(),
            ", ".join(str(x) for x in profs[:3]),
        ])
    return rows


def format_roster(cfg, fmt="text"):
    head = [t(h) for h in _ROSTER_COLS]
    rows = roster_rows(cfg)
    if not rows:
        return ""
    if fmt == "bbcode":
        out = ["[table]", "[tr]" + "".join("[td][b]%s[/b][/td]" % h
                                           for h in head) + "[/tr]"]
        for r in rows:
            out.append("[tr]" + "".join("[td]%s[/td]" % v for v in r) + "[/tr]")
        out.append("[/table]")
        return "\n".join(out)
    if fmt == "markdown":
        out = ["| " + " | ".join(head) + " |",
               "|" + "|".join("---" for _ in head) + "|"]
        for r in rows:
            out.append("| " + " | ".join(r) + " |")
        return "\n".join(out)
    # plain text, padded into columns
    widths = [max(len(head[i]), max(len(r[i]) for r in rows))
              for i in range(len(head))]
    def line(vals):
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(vals)).rstrip()
    out = [line(head), "-" * len(line(head))]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


# ── per-character settings transfer ───────────────────────────────────────────
# Setting up a fresh alt means redoing the UI, the keybinds and every addon.
# All of it lives in WTF/Account/<ACC>/<Realm>/<Character>/ — copying those
# files over is the whole feature.

# key -> (label, explicit file names; empty means "the SavedVariables folder")
WTF_GROUPS = (
    ("config", "Интерфейс и бинды",
     ("config-cache.wtf", "layout-local.txt", "bindings-cache.wtf")),
    ("addons", "Список включённых аддонов", ("AddOns.txt",)),
    ("macros", "Макросы персонажа", ("macros-cache.txt",)),
    ("savedvars", "Настройки аддонов (SavedVariables)", ()),
)


def list_wtf_characters(wow_dir):
    """Every character folder the client has ever written, as
    (account, realm, character, path). Sorted, so the UI order is stable."""
    base = os.path.join(wow_dir or "", "WTF", "Account")
    out = []
    try:
        accounts = sorted(os.listdir(base))
    except OSError:
        return out
    for acc in accounts:
        acc_dir = os.path.join(base, acc)
        if not os.path.isdir(acc_dir):
            continue
        try:
            realms = sorted(os.listdir(acc_dir))
        except OSError:
            continue
        for realm in realms:
            # Account-wide SavedVariables sit at this level, not a realm.
            if realm.lower() == "savedvariables":
                continue
            realm_dir = os.path.join(acc_dir, realm)
            if not os.path.isdir(realm_dir):
                continue
            try:
                chars = sorted(os.listdir(realm_dir))
            except OSError:
                continue
            for char in chars:
                char_dir = os.path.join(realm_dir, char)
                if os.path.isdir(char_dir):
                    out.append((acc, realm, char, char_dir))
    return out


def copy_wtf_settings(src_dir, dst_dirs, groups):
    """Copy the chosen groups from one character folder to others.
    Returns (files_copied, [error strings]). Never raises."""
    copied, errors = 0, []
    wanted = {g[0] for g in WTF_GROUPS if g[0] in groups}
    files = []
    for key, _label, names in WTF_GROUPS:
        if key in wanted:
            files.extend(names)

    for dst in dst_dirs:
        if os.path.abspath(dst) == os.path.abspath(src_dir):
            continue
        try:
            os.makedirs(dst, exist_ok=True)
        except OSError as e:
            errors.append("%s: %s" % (dst, e))
            continue
        for fn in files:
            sp = os.path.join(src_dir, fn)
            if not os.path.isfile(sp):
                continue        # the client only writes what it needs
            try:
                shutil.copy2(sp, os.path.join(dst, fn))
                copied += 1
            except OSError as e:
                errors.append("%s: %s" % (fn, e))
        if "savedvars" in wanted:
            sv_src = os.path.join(src_dir, "SavedVariables")
            sv_dst = os.path.join(dst, "SavedVariables")
            if os.path.isdir(sv_src):
                try:
                    os.makedirs(sv_dst, exist_ok=True)
                except OSError as e:
                    errors.append("%s: %s" % (sv_dst, e))
                    continue
                for fn in os.listdir(sv_src):
                    sp = os.path.join(sv_src, fn)
                    if not os.path.isfile(sp):
                        continue
                    try:
                        shutil.copy2(sp, os.path.join(sv_dst, fn))
                        copied += 1
                    except OSError as e:
                        errors.append("%s: %s" % (fn, e))
    return copied, errors


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


# The names a 3.3.5a client ships under — the same list the AwesomeWotlk
# patcher looks for. Getting this wrong would let the settings transfer write
# underneath a live client, which then overwrites everything on exit.
WOW_PROCESS_NAMES = (b"wow.exe", b"wowcircle.exe", b"run.exe")


def is_wow_running():
    """True if a game client process is currently running (Windows)."""
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
                if entry.szExeFile.lower() in WOW_PROCESS_NAMES:
                    found = True
                    break
                if not k.Process32Next(snap, ctypes.byref(entry)):
                    break
        k.CloseHandle(snap)
        return found
    except Exception:
        return False


def terminate_clients():
    """Close any running game client. Used only when a data-collection run
    has to give up on one — with an external loader the client isn't our
    child process, so there is nothing to terminate directly."""
    if sys.platform != "win32":
        return False
    ok = False
    for name in WOW_PROCESS_NAMES:
        try:
            r = subprocess.run(["taskkill", "/F", "/IM", name.decode()],
                               capture_output=True,
                               creationflags=0x08000000)
            ok = ok or r.returncode == 0
        except OSError:
            pass
    return ok


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
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _restore_snapshot(wow_dir, zip_path):
    """Extract a snapshot .zip back into the game folder: WTF/* → <wow>/WTF,
    AddOns/* → <wow>/Interface/AddOns. Merges over existing files."""
    game_root = os.path.abspath(wow_dir)
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
            # Never let ".." inside the archive escape the game folder.
            dest = os.path.abspath(dest)
            if os.path.commonpath([dest, game_root]) != game_root:
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


# Graphics / sound presets applied by the patch DLL for one launch. Values
# the client then writes to WTF/Config.wtf are put back by the manager once
# that client exits (see restore_config_cvars), so a light background window
# never leaves your main client with its settings.
GRAPHICS_PRESETS = {
    "light": {
        "farclip": "450", "groundEffectDensity": "32", "groundEffectDist": "70",
        "environmentDetail": "0.75", "particleDensity": "0.5",
        "weatherDensity": "1", "extShadowQuality": "1",
        "detailDoodadAlpha": "50", "maxFPS": "60", "maxFPSBk": "20",
    },
    "minimal": {
        "farclip": "177", "groundEffectDensity": "16", "groundEffectDist": "1",
        "environmentDetail": "0.5", "particleDensity": "0.1",
        "weatherDensity": "0", "extShadowQuality": "0",
        "detailDoodadAlpha": "0", "projectedTextures": "0",
        "spellEffectLevel": "0", "maxFPS": "30", "maxFPSBk": "8",
        "Sound_EnableAllSound": "0",
    },
}
GRAPHICS_LABELS = (("", "Как в настройках игры"), ("light", "Лёгкая"),
                   ("minimal", "Минимальная, без звука (фон / твинк)"))

# What the preset builder can change: (cvar, label, kind, lo, hi, step, default).
# Only client settings that take effect without restarting the graphics engine.
GRAPHICS_SETTINGS = (
    ("farclip", "Дальность обзора", "scale", 177, 1277, 10, 777),
    ("groundEffectDensity", "Густота травы", "scale", 16, 256, 8, 64),
    ("groundEffectDist", "Дальность травы", "scale", 1, 140, 5, 70),
    ("environmentDetail", "Детализация окружения", "scale", 0.5, 1.5, 0.05, 1.0),
    ("particleDensity", "Частицы", "scale", 0.1, 1.0, 0.1, 1.0),
    ("weatherDensity", "Погода", "scale", 0, 3, 1, 2),
    ("extShadowQuality", "Тени", "scale", 0, 5, 1, 2),
    ("spellEffectLevel", "Эффекты заклинаний", "scale", 0, 2, 1, 1),
    ("detailDoodadAlpha", "Мелкие объекты", "scale", 0, 100, 5, 100),
    ("projectedTextures", "Проецируемые текстуры", "toggle", 0, 1, 1, 1),
    ("maxFPS", "Ограничение FPS (0 — без него)", "scale", 0, 200, 5, 0),
    ("maxFPSBk", "FPS в фоне", "scale", 0, 60, 5, 30),
    ("Sound_EnableAllSound", "Звук", "toggle", 0, 1, 1, 1),
    ("Sound_EnableMusic", "Музыка", "toggle", 0, 1, 1, 1),
)
GRAPHICS_SETTING_LABELS = {c: lbl for c, lbl, _k, _lo, _hi, _st, _d
                           in GRAPHICS_SETTINGS}

# Screen mode and resolution are read by the client when it starts, so these
# go into WTF/Config.wtf before launch instead of being set from the DLL.
# (gxWindow 0 = fullscreen; gxWindow 1 + gxMaximize 1 = borderless window.)
GX_SETTINGS = ("gxWindow", "gxMaximize", "gxResolution")
GRAPHICS_SETTING_LABELS.update({"gxWindow": "Режим окна",
                                "gxMaximize": "Режим окна",
                                "gxResolution": "Разрешение"})
SCREEN_MODES = (("full", "Полный экран", "0", "0"),
                ("window", "Окно", "1", "0"),
                ("borderless", "Окно без рамки", "1", "1"))


def screen_mode_of(cvars):
    """Which of the three modes a preset's CVars describe, or "" for none."""
    if "gxWindow" not in cvars:
        return ""
    win = str(cvars.get("gxWindow", "")).strip()
    maxi = str(cvars.get("gxMaximize", "0")).strip()
    for key, _label, w, m in SCREEN_MODES:
        if win == w and maxi == m:
            return key
    return "window" if win == "1" else "full"


def screen_mode_cvars(key):
    for k, _label, w, m in SCREEN_MODES:
        if k == key:
            return {"gxWindow": w, "gxMaximize": m}
    return {}


def available_resolutions():
    """Screen modes Windows reports, widest first; falls back to a common
    list when it can't ask."""
    out = set()
    if sys.platform == "win32":
        try:
            class DEVMODE(ctypes.Structure):
                _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                            ("dmSpecVersion", ctypes.c_ushort),
                            ("dmDriverVersion", ctypes.c_ushort),
                            ("dmSize", ctypes.c_ushort),
                            ("dmDriverExtra", ctypes.c_ushort),
                            ("dmFields", ctypes.c_ulong),
                            ("dmPositionX", ctypes.c_long),
                            ("dmPositionY", ctypes.c_long),
                            ("dmDisplayOrientation", ctypes.c_ulong),
                            ("dmDisplayFixedOutput", ctypes.c_ulong),
                            ("dmColor", ctypes.c_short),
                            ("dmDuplex", ctypes.c_short),
                            ("dmYResolution", ctypes.c_short),
                            ("dmTTOption", ctypes.c_short),
                            ("dmCollate", ctypes.c_short),
                            ("dmFormName", ctypes.c_wchar * 32),
                            ("dmLogPixels", ctypes.c_ushort),
                            ("dmBitsPerPel", ctypes.c_ulong),
                            ("dmPelsWidth", ctypes.c_ulong),
                            ("dmPelsHeight", ctypes.c_ulong),
                            ("dmDisplayFlags", ctypes.c_ulong),
                            ("dmDisplayFrequency", ctypes.c_ulong),
                            ("dmICMMethod", ctypes.c_ulong),
                            ("dmICMIntent", ctypes.c_ulong),
                            ("dmMediaType", ctypes.c_ulong),
                            ("dmDitherType", ctypes.c_ulong),
                            ("dmReserved1", ctypes.c_ulong),
                            ("dmReserved2", ctypes.c_ulong),
                            ("dmPanningWidth", ctypes.c_ulong),
                            ("dmPanningHeight", ctypes.c_ulong)]

            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            i = 0
            while ctypes.windll.user32.EnumDisplaySettingsW(None, i,
                                                            ctypes.byref(dm)):
                if dm.dmPelsWidth >= 800 and dm.dmBitsPerPel >= 24:
                    out.add("%dx%d" % (dm.dmPelsWidth, dm.dmPelsHeight))
                i += 1
        except Exception:
            pass
    if not out:
        out = {"1024x768", "1280x720", "1280x1024", "1366x768", "1600x900",
               "1920x1080", "2560x1440"}
    return sorted(out, key=lambda r: [int(x) for x in r.split("x")],
                  reverse=True)


def gfx_value_str(value):
    """Store numbers the way the client writes them: 1 not 1.0, 0.75 not 0.7500."""
    text = ("%.2f" % float(value)).rstrip("0").rstrip(".")
    return text or "0"


def user_presets(cfg):
    presets = cfg.get("graphics_presets")
    return presets if isinstance(presets, dict) else {}


def preset_cvars(cfg, key):
    """The CVars a preset applies — built-in or one the user built."""
    if key in GRAPHICS_PRESETS:
        return dict(GRAPHICS_PRESETS[key])
    p = user_presets(cfg).get(key)
    if isinstance(p, dict) and isinstance(p.get("cvars"), dict):
        return {k: str(v) for k, v in p["cvars"].items()
                if k in GRAPHICS_SETTING_LABELS}
    return {}


def preset_exists(cfg, key):
    return key in GRAPHICS_PRESETS or key in user_presets(cfg)


def preset_label(cfg, key):
    for k, lbl in GRAPHICS_LABELS:
        if k == key and k:
            return t(lbl)
    p = user_presets(cfg).get(key)
    return (p.get("name") or key) if isinstance(p, dict) else key


def graphics_options(cfg, for_character=False):
    """(key, label) pairs for the preset pickers."""
    if for_character:
        opts = [("", t("Как у аккаунта")), ("none", t("Как в настройках игры"))]
    else:
        opts = [("", t("Как в настройках игры"))]
    opts += [(k, t(lbl)) for k, lbl in GRAPHICS_LABELS if k]
    opts += sorted(((k, preset_label(cfg, k)) for k in user_presets(cfg)),
                   key=lambda kv: kv[1].lower())
    return opts


def new_preset_key(cfg):
    n = 1
    while ("my%d" % n) in user_presets(cfg):
        n += 1
    return "my%d" % n


def drop_preset(cfg, key):
    """Delete a user preset and forget it wherever it was assigned."""
    cfg.setdefault("graphics_presets", {}).pop(key, None)
    for e in cfg.get("characters", []):
        if (e.get("graphics") or "") == key:
            e["graphics"] = ""


def effective_graphics(cfg, char):
    """A character's own preset, else its account's, else none."""
    own = (char.get("graphics") or "").strip()
    if own == "none":                # explicitly "as in the game" for this one
        return ""
    if preset_exists(cfg, own):
        return own
    acc = account_entry_for(cfg, char.get("account")) or {}
    inherited = (acc.get("graphics") or "").strip()
    return inherited if preset_exists(cfg, inherited) else ""


_CVAR_LINE = re.compile(r'^\s*SET\s+(\S+)\s+"(.*)"\s*$', re.I)


def read_config_cvars(wow_dir, names):
    """{name: value or None} for the given CVars as WTF/Config.wtf has them."""
    wanted = {n.lower(): n for n in names}
    out = {n: None for n in names}
    try:
        with open(os.path.join(wow_dir, "WTF", "Config.wtf"), "r",
                  encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _CVAR_LINE.match(line)
                if m and m.group(1).lower() in wanted:
                    out[wanted[m.group(1).lower()]] = m.group(2)
    except OSError:
        pass
    return out


def restore_config_cvars(wow_dir, snapshot):
    """Put the snapshot back into WTF/Config.wtf: known values are rewritten,
    CVars that weren't in the file before are removed again."""
    path = os.path.join(wow_dir, "WTF", "Config.wtf")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    lower = {k.lower(): k for k in snapshot}
    out, seen = [], set()
    for line in lines:
        m = _CVAR_LINE.match(line)
        key = lower.get(m.group(1).lower()) if m else None
        if key is None:
            out.append(line)
            continue
        seen.add(key)
        if snapshot[key] is not None:
            out.append('SET %s "%s"' % (m.group(1), snapshot[key]))
    for key, val in snapshot.items():
        if key not in seen and val is not None:
            out.append('SET %s "%s"' % (key, val))
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


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


def _write_autologin_json(wow_dir, char, realmlist, extra=None):
    """Write per-launch params next to Wow.exe — DLL reads it then deletes it.
    `extra` adds flat string keys (anti-AFK switch, cvar_<Name> presets)."""
    data = _build_autologin_json(char, realmlist)
    data.update(extra or {})
    path = os.path.join(wow_dir, "autologin.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def drop_stale_autologin_json(wow_dir):
    """Remove a leftover autologin.json. The DLL deletes the file as soon as it
    reads it, so one surviving with no client running means the launch died
    early — and it holds the account password in plain text."""
    if not wow_dir or is_wow_running():
        return
    try:
        os.remove(os.path.join(wow_dir, "autologin.json"))
    except OSError:
        pass


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
    return subprocess.Popen([path], cwd=loader_dir)


def launch_wow(cfg, char, on_error=None, harvest_chars=None):
    wow_dir = cfg.get("wow_path", "")
    exe = os.path.join(wow_dir, "Wow.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(t("Wow.exe не найден:\n{exe}").format(exe=exe))

    realmlist = (char.get("realmlist") or cfg.get("realmlist")
                 or REALMLISTS_DEFAULT[0])

    deploy_patch(wow_dir, on_error=on_error,
                 large_address=bool(cfg.get("laa_patch", True)))
    update_realmlist(wow_dir, realmlist)

    # Deploy (or remove) the data-collector / overlay addon based on settings
    addon_on = bool(cfg.get("hover_card", True) or cfg.get("overlay", False)
                    or cfg.get("sync_friends", True) or cfg.get("lfg", True))
    deploy_addon(wow_dir, addon_on,
                 show_minimap=bool(cfg.get("overlay", False)),
                 characters=cfg.get("characters", []),
                 hover_card=bool(cfg.get("hover_card", True)),
                 card_fields=cfg.get("card_fields"),
                 card_labels=cfg.get("card_labels"),
                 current_account=char.get("account", ""),
                 sync_friends=bool(cfg.get("sync_friends", True)),
                 lfg=bool(cfg.get("lfg", True)),
                 harvest_chars=harvest_chars)

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

    extra = {}
    if cfg.get("anti_afk"):
        extra["antiafk"] = "1"
    preset = effective_graphics(cfg, char)
    cvars = preset_cvars(cfg, preset) if preset else {}
    snapshot = read_config_cvars(wow_dir, cvars) if cvars else None
    screen = {k: v for k, v in cvars.items() if k in GX_SETTINGS}
    for name, value in cvars.items():
        if name not in GX_SETTINGS:
            extra["cvar_" + name] = value
    if screen:
        # The client reads these at startup, so they go in before it runs.
        restore_config_cvars(wow_dir, screen)

    # Always write autologin.json so the DLL has params no matter who launches Wow.
    _write_autologin_json(wow_dir, char, realmlist, extra)

    if cfg.get("use_loader") and (cfg.get("loader_path") or "").strip():
        # The loader starts the client itself, so the handle we get back is
        # the loader's. Anything that needs to know whether the game is up
        # asks is_wow_running() instead.
        return _launch_via_loader(cfg, wow_dir, on_error=on_error)

    # Single source of truth for credentials = autologin.json, read by the
    # DLL. Passing them ALSO via argv used to cause a race: the argv path
    # and the JSON path could both fire a login packet, the server saw two
    # auth attempts from the same account and kicked one of them mid-world-
    # load — that was the "1 in 3" disconnect on character enter.
    proc = subprocess.Popen([exe], cwd=wow_dir)
    if snapshot is not None:
        # The client saves whatever it ran with to Config.wtf on exit; put the
        # user's own values back afterwards.
        def _restore():
            proc.wait()
            time.sleep(1.0)
            restore_config_cvars(wow_dir, snapshot)
        threading.Thread(target=_restore, daemon=True).start()
    return proc


# ── helpers ───────────────────────────────────────────────────────────────────

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

# Secrets can be stored three ways, picked in Settings:
#   "dpapi"  — Windows DPAPI, tied to this PC and this Windows account
#              (the default, and what every existing config already uses)
#   "master" — a master password typed once per session. The config becomes
#              portable — a flash drive, another PC — and useless without it.
#   "plain"  — no encryption.
#
# Master mode derives a key with scrypt and then does encrypt-then-MAC with an
# HMAC-SHA256 keystream. That is not AES, and it is a deliberate trade: it keeps
# the program dependency-free (nothing to bundle, nothing for an antivirus to
# object to) while still being a sound construction.
_SECRET_PREFIX = "enc:v1:"      # DPAPI blob
_MASTER_PREFIX = "enc:m1:"      # master-password blob
_SECRET_PREFIXES = (_SECRET_PREFIX, _MASTER_PREFIX)
SECRET_MODES = ("dpapi", "master", "plain")

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 1 << 15, 8, 1
_MASTER_CHECK = b"WowManager master key check v1"

# 64 bytes (32 cipher + 32 mac) for this session only — never written to disk.
_MASTER_KEY = None
# True when the config holds secrets we could not decrypt (wrong / refused
# master password). Everything that needs a password must refuse to run.
SECRETS_LOCKED = False


def _is_encrypted(value):
    return isinstance(value, str) and value.startswith(_SECRET_PREFIXES)


def derive_master_key(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                          dklen=64, maxmem=192 * 1024 * 1024)


def _keystream(key, nonce, nbytes):
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        out += hmac.new(key, nonce + struct.pack(">I", counter),
                        hashlib.sha256).digest()
        counter += 1
    return bytes(out[:nbytes])


def _xor(data, stream):
    return bytes(a ^ b for a, b in zip(data, stream))


def master_verifier(key):
    return base64.b64encode(
        hmac.new(key[32:], _MASTER_CHECK, hashlib.sha256).digest()).decode("ascii")


def set_master_key(key):
    global _MASTER_KEY
    _MASTER_KEY = key


def have_master_key():
    return _MASTER_KEY is not None


def _master_encrypt(plaintext):
    if _MASTER_KEY is None:
        raise RuntimeError("master key is not unlocked")
    nonce = os.urandom(16)
    data = plaintext.encode("utf-8")
    ct = _xor(data, _keystream(_MASTER_KEY[:32], nonce, len(data)))
    tag = hmac.new(_MASTER_KEY[32:], nonce + ct, hashlib.sha256).digest()[:16]
    return _MASTER_PREFIX + base64.b64encode(nonce + tag + ct).decode("ascii")


def _master_decrypt(stored):
    if _MASTER_KEY is None:
        raise RuntimeError("master key is not unlocked")
    blob = base64.b64decode(stored[len(_MASTER_PREFIX):])
    nonce, tag, ct = blob[:16], blob[16:32], blob[32:]
    expect = hmac.new(_MASTER_KEY[32:], nonce + ct, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expect):
        raise ValueError("wrong master password or tampered value")
    return _xor(ct, _keystream(_MASTER_KEY[:32], nonce, len(ct))).decode("utf-8")


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


def encrypt_secret(plaintext, mode="dpapi"):
    # Already a blob (e.g. we never managed to unlock it) — leave it alone
    # rather than encrypting the ciphertext a second time.
    if not plaintext or _is_encrypted(plaintext):
        return plaintext
    if mode == "master":
        try:
            return _master_encrypt(plaintext)
        except Exception:
            return plaintext
    if mode != "dpapi" or sys.platform != "win32":
        return plaintext
    try:
        blob = _dpapi_call(ctypes.windll.crypt32.CryptProtectData,
                           plaintext.encode("utf-8"))
        return _SECRET_PREFIX + base64.b64encode(blob).decode("ascii")
    except Exception:
        return plaintext


def decrypt_secret(stored):
    """Undo whichever scheme produced this value. Dispatching on the prefix
    rather than on the configured mode means a config half-converted between
    modes still opens."""
    if not _is_encrypted(stored):
        return stored or ""
    try:
        if stored.startswith(_MASTER_PREFIX):
            return _master_decrypt(stored)
        blob = base64.b64decode(stored[len(_SECRET_PREFIX):])
        return _dpapi_call(ctypes.windll.crypt32.CryptUnprotectData,
                           blob).decode("utf-8")
    except Exception:
        return ""


_SECRET_FIELDS = ("password", "totp_secret")


def decrypt_cfg_secrets(cfg):
    for c in cfg.get("characters", []):
        for k in _SECRET_FIELDS:
            if c.get(k):
                c[k] = decrypt_secret(c[k])


def cfg_has_encrypted_secrets(cfg):
    return any(_is_encrypted(c.get(k))
               for c in cfg.get("characters", [])
               for k in _SECRET_FIELDS)


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
        # Read without decrypting: master mode needs a themed password prompt,
        # and the theme is only known once the config has been read.
        self.cfg = load_cfg(decrypt=False)
        init_fonts(root)
        apply_theme(self.cfg.get("theme", "dark"))
        set_lang(self.cfg.get("lang", "ru"))
        self.search_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self._tray_icon = None
        self._banners = {}   # kind -> dict(text, action_label, action, accent)
        self._card = None
        self._card_row = None
        self._last_launch = {}   # entry key -> time.monotonic() of last launch
        self._harvesting = False
        self._harvest_stop = False
        root.title(APP_TITLE)
        self._restore_geometry()
        root.bind_class("Toplevel", "<Map>", self._on_toplevel_map, add="+")
        root.minsize(780, 480)
        root.configure(bg=BG)
        # Hide-to-tray on close, real exit via tray menu
        root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        try:
            root.iconbitmap(_bundled("wow.ico"))
        except Exception:
            pass
        self._unlock_secrets()
        self.build()
        if RECOVERED_FROM_BACKUP[0]:
            RECOVERED_FROM_BACKUP[0] = False
            save_cfg(self.cfg)
            self._add_banner("recovered",
                             t("Список персонажей восстановлен из резервной "
                               "копии."), accent=ACCENT)
        self._setup_tray()
        self._start_background_checks()

    # ── secrets ─────────────────────────────────────────────────────────────

    def _ask_password(self, title, prompt, confirm_prompt=None):
        """Modal password box in the app's own theme. Returns the string, or
        None if the user backed out."""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        result = {"value": None}

        tk.Label(dlg, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")
                 ).pack(padx=20, pady=(16, 6), anchor="w")
        tk.Label(dlg, text=prompt, bg=BG, fg=MUTED, font=("Segoe UI", 9),
                 justify="left", wraplength=340
                 ).pack(padx=20, anchor="w")

        v1 = tk.StringVar()
        e1 = _make_entry(dlg, v1, show="●")
        e1.pack(fill="x", padx=20, pady=(8, 0), ipady=5)
        v2 = None
        if confirm_prompt:
            tk.Label(dlg, text=confirm_prompt, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9)).pack(fill="x", padx=20, pady=(8, 0))
            v2 = tk.StringVar()
            _make_entry(dlg, v2, show="●").pack(fill="x", padx=20, ipady=5)

        err_var = tk.StringVar()
        tk.Label(dlg, textvariable=err_var, bg=BG, fg="#D9534F",
                 font=("Segoe UI", 9), wraplength=340, justify="left"
                 ).pack(fill="x", padx=20, pady=(4, 0))

        def ok(_e=None):
            pw = v1.get()
            if v2 is not None:
                if pw != v2.get():
                    err_var.set(t("Пароли не совпадают."))
                    return
                if len(pw) < MASTER_MIN_LEN:
                    err_var.set(t("Пароль слишком короткий — минимум {n} "
                                  "символов.").format(n=MASTER_MIN_LEN))
                    return
            result["value"] = pw
            dlg.destroy()

        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=20, pady=(12, 16))
        tk.Button(row, text=t("ОК"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", padx=18, pady=6, command=ok
                  ).pack(side="right")
        tk.Button(row, text=t("Отмена"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=6, command=dlg.destroy
                  ).pack(side="right", padx=(0, 8))

        e1.bind("<Return>", ok)
        e1.focus_set()
        self._fit_dialog(dlg, 400)
        dlg.grab_set()
        self.root.wait_window(dlg)
        return result["value"]

    def _unlock_secrets(self):
        """Master mode: ask for the password until it opens the config, or the
        user gives up. Everything that needs a password stays blocked until it
        does."""
        global SECRETS_LOCKED
        if secret_mode(self.cfg) != "master":
            decrypt_cfg_secrets(self.cfg)
            SECRETS_LOCKED = False
            return True
        try:
            salt = base64.b64decode(self.cfg.get("master_salt") or "")
        except Exception:
            salt = b""
        expect = self.cfg.get("master_check") or ""
        if not (salt and expect):
            # Mode says master but the key material is gone — treat what's in
            # the file as whatever it is and let the user fix it in Settings.
            decrypt_cfg_secrets(self.cfg)
            SECRETS_LOCKED = cfg_has_encrypted_secrets(self.cfg)
            return not SECRETS_LOCKED

        prompt = t("Пароли и 2FA-секреты зашифрованы мастер-паролем.")
        while True:
            pw = self._ask_password(t("Введи мастер-пароль"), prompt)
            if pw is None:
                SECRETS_LOCKED = True
                self._add_banner(
                    "locked",
                    t("Пароли заблокированы — мастер-пароль не введён."),
                    t("Ввести пароль"), self._relock_prompt, accent="#D9534F")
                return False
            key = derive_master_key(pw, salt)
            if hmac.compare_digest(master_verifier(key), expect):
                set_master_key(key)
                decrypt_cfg_secrets(self.cfg)
                SECRETS_LOCKED = False
                self._dismiss_banner("locked")
                return True
            prompt = t("Неверный пароль.")

    def _relock_prompt(self):
        if self._unlock_secrets():
            self.render_rows()

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

        threading.Thread(
            target=lambda: drop_stale_autologin_json(self.cfg.get("wow_path", "")),
            daemon=True).start()
        threading.Thread(target=_clock, daemon=True).start()
        threading.Thread(target=_update, daemon=True).start()
        threading.Thread(target=self._refresh_ingame, daemon=True).start()
        # Re-read in-game data when the window regains focus (after playing)
        self.root.bind("<FocusIn>", self._on_focus_in)
        # Overlay relog watcher
        self._relog_seen = int(time.time())
        threading.Thread(target=self._relog_watcher, daemon=True).start()
        threading.Thread(target=self._check_char_lists, daemon=True).start()

    def _relog_watcher(self):
        """Poll the addon for an overlay relog request; once Wow.exe has closed,
        relaunch the chosen character through the manager."""
        while True:
            time.sleep(3)
            try:
                self._check_char_lists()
            except Exception:
                pass
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

    # ── styling ───────────────────────────────────────────────────────────────

    def _apply_ttk_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Roster.Treeview",
                     background=PANEL, foreground=TEXT, fieldbackground=PANEL,
                     borderwidth=0, rowheight=32, font=font(10))
        st.layout("Roster.Treeview",
                  [("Roster.Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Roster.Treeview.Heading",
                     background=PANEL, foreground=MUTED, borderwidth=0,
                     relief="flat", font=font(9, "bold"), padding=(10, 8))
        st.map("Roster.Treeview.Heading",
               background=[("active", PANEL)], foreground=[("active", TEXT)])
        st.map("Roster.Treeview",
               background=[("selected", SEL_BG)],
               foreground=[("selected", SEL_FG)])
        # Legacy tables in dialogs keep a plain look in the same palette
        st.configure("Treeview", background=PANEL, foreground=TEXT,
                     fieldbackground=PANEL, borderwidth=0, rowheight=24)
        st.configure("Treeview.Heading", background=BTN_BG, foreground=TEXT,
                     borderwidth=0, relief="flat", font=font(9, "bold"))
        st.map("Treeview", background=[("selected", SEL_BG)],
               foreground=[("selected", SEL_FG)])
        # Thin, arrow-less scrollbars
        for orient in ("Vertical", "Horizontal"):
            name = "Slim.%s.TScrollbar" % orient
            st.layout(name, [("%s.Scrollbar.trough" % orient, {
                "sticky": "ns" if orient == "Vertical" else "we",
                "children": [("%s.Scrollbar.thumb" % orient,
                              {"expand": "1", "sticky": "nswe"})]})])
            st.configure(name, troughcolor=PANEL, background=BTN_BG,
                         bordercolor=PANEL, lightcolor=BTN_BG,
                         darkcolor=BTN_BG, relief="flat", gripcount=0,
                         width=10, arrowsize=10)
            st.map(name, background=[("active", BTN_HOVER)])
        st.configure("TCombobox", fieldbackground=ENTRY_BG, background=BTN_BG,
                     foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                     lightcolor=ENTRY_BG, darkcolor=ENTRY_BG,
                     selectbackground=ENTRY_BG, selectforeground=TEXT)
        st.map("TCombobox", fieldbackground=[("readonly", ENTRY_BG)],
               foreground=[("readonly", TEXT)],
               selectbackground=[("readonly", ENTRY_BG)],
               selectforeground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", ENTRY_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", SEL_BG)
        self.root.option_add("*TCombobox*Listbox.selectForeground", SEL_FG)
        self.root.option_add("*TCombobox*Listbox.font", font(10))

    def _save_window_state(self):
        try:
            self.cfg["win_geometry"] = self.root.geometry()
            save_cfg(self.cfg)
        except Exception:
            pass

    # ── main window ──────────────────────────────────────────────────────────

    def build(self):
        self._apply_ttk_styles()
        self.root.title("%s  ·  v%s" % (t(APP_TITLE), __version__))
        style_window_chrome(self.root)

        self._banner_area = tk.Frame(self.root, bg=BG)
        self._banner_area.pack(fill="x", side="top")
        self._render_banners()

        # ── header: search + actions ─────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 10))

        search_box = tk.Frame(header, bg=ENTRY_BG, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=ACCENT)
        search_box.pack(side="left", fill="x", expand=True, padx=(0, 12))
        tk.Label(search_box, text=icon_glyph("search"), bg=ENTRY_BG, fg=MUTED,
                 font=(ICON_FONT, 11) if ICON_FONT else font(11)
                 ).pack(side="left", padx=(12, 6))
        self._search_entry = tk.Entry(
            search_box, textvariable=self.search_var, bg=ENTRY_BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=font(10), bd=0)
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=8)
        placeholder = tk.Label(search_box, text=t("Поиск персонажа или аккаунта"),
                               bg=ENTRY_BG, fg=MUTED, font=font(10))

        def _placeholder(*_):
            if self.search_var.get():
                placeholder.place_forget()
            else:
                placeholder.place(in_=self._search_entry, x=2, rely=0.5,
                                  anchor="w")
        placeholder.bind("<Button-1>", lambda _e: self._search_entry.focus_set())
        self.search_var.trace_add("write", _placeholder)
        self.search_var.trace_add("write", lambda *_: self.render_rows())
        _placeholder()

        FlatButton(header, t("Аккаунт"), icon="add", kind="primary",
                   command=lambda: self.account_dialog(None)
                   ).pack(side="left", padx=(0, 8))
        self._btn_edit = FlatButton(header, icon="edit", padx=11,
                                    command=self.edit_selected)
        self._btn_edit.pack(side="left", padx=(0, 8))
        self._btn_delete = FlatButton(header, icon="delete", padx=11,
                                      command=self.delete_selected)
        self._btn_delete.pack(side="left", padx=(0, 8))
        FlatButton(header, icon="settings", padx=11,
                   command=self.settings).pack(side="left")

        # ── summary chips ────────────────────────────────────────────────────
        self._chips = tk.Frame(self.root, bg=BG)
        self._chips.pack(fill="x", padx=20, pady=(0, 10))

        # ── the roster: one tree, accounts with their characters ─────────────
        card = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self._tree_card = card

        self._cols = [c for c in self.cfg.get("columns", DEFAULT_COLUMNS)
                      if c and c != "name"]
        labels = self.cfg.get("column_labels", {})
        widths = self.cfg.get("column_widths", {})

        tree = ttk.Treeview(card, columns=tuple(self._cols), show="tree headings",
                            selectmode="browse", style="Roster.Treeview")
        tree.heading("#0", text=labels.get("name") or t("Аккаунт / персонаж"),
                     anchor="w")
        tree.column("#0", width=int(widths.get("name", 240)), minwidth=160,
                    stretch=False, anchor="w")
        for col in self._cols:
            default_label, w, anchor, _getter = col_meta(col)
            tree.heading(col, text=(labels.get(col) or t(default_label)),
                         anchor=anchor)
            tree.column(col, width=int(widths.get(col, w)), anchor=anchor,
                        stretch=False)
        sb = ttk.Scrollbar(card, orient="vertical", command=tree.yview,
                           style="Slim.Vertical.TScrollbar")
        sb.pack(side="right", fill="y", padx=(0, 2), pady=2)
        tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(2, 6))
        tree.configure(yscrollcommand=sb.set)
        self.tree = tree

        tree.tag_configure("account", font=font(10, "bold"), background=ACC_ROW,
                           foreground=TEXT)
        tree.tag_configure("orphans", font=font(10, "bold"), foreground=MUTED)
        for cls in CLASS_COLORS:
            tree.tag_configure("cls_" + cls, foreground=class_text_color(cls))

        tree.bind("<Configure>", self._fit_columns)
        tree.bind("<Double-1>", self._on_double)
        tree.bind("<Return>", lambda _e: self.launch_selected())
        tree.bind("<Delete>", lambda _e: self.delete_selected())
        tree.bind("<F2>", lambda _e: self.edit_selected())
        tree.bind("<Button-3>", self._on_context)
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_actions())
        tree.bind("<<TreeviewOpen>>", lambda e: self._on_fold(True, e))
        tree.bind("<<TreeviewClose>>", lambda e: self._on_fold(False, e))
        self._drag = None
        tree.bind("<ButtonPress-1>", self._on_drag_start)
        tree.bind("<B1-Motion>", self._on_drag_motion)
        tree.bind("<ButtonRelease-1>", self._on_drag_drop)
        tree.bind("<ButtonRelease-1>", self._save_col_widths, add="+")
        tree.bind("<Motion>", self._on_tree_motion)
        tree.bind("<Leave>", lambda _e: self._hide_card())
        tree.bind("<ButtonPress-1>", lambda _e: self._hide_card(), add="+")
        tree.bind("<Enter>", lambda _e: tree.focus_set())

        # Empty state, shown over the table when there is nothing yet
        self._empty = tk.Frame(card, bg=PANEL)
        tk.Label(self._empty, text=icon_glyph("people"), bg=PANEL, fg=MUTED,
                 font=(ICON_FONT, 34) if ICON_FONT else font(30)).pack()
        tk.Label(self._empty, text=t("Добавь первый аккаунт"), bg=PANEL,
                 fg=TEXT, font=font(14, "bold")).pack(pady=(10, 4))
        tk.Label(self._empty,
                 text=t("Логин и пароль — персонажи подтянутся сами при "
                        "первом входе в игру."),
                 bg=PANEL, fg=MUTED, font=font(10)).pack()
        FlatButton(self._empty, t("Добавить аккаунт"), icon="add",
                   kind="primary", command=lambda: self.account_dialog(None)
                   ).pack(pady=(16, 0))

        # ── footer ───────────────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(footer, text=t("Сортировка"), bg=BG, fg=MUTED,
                 font=font(9)).pack(side="left")
        self._sort_var = tk.StringVar()
        self._sort_box = ttk.Combobox(footer, textvariable=self._sort_var,
                                      state="readonly", width=20,
                                      font=font(9))
        self._sort_box.pack(side="left", padx=(8, 4))
        self._sort_box.bind("<<ComboboxSelected>>", self._on_sort_pick)
        self._sort_dir = FlatButton(footer, "", padx=8, pady=3,
                                    command=self._toggle_sort_dir)
        self._sort_dir.pack(side="left")
        self._refresh_sort_picker()

        tk.Label(footer,
                 text=t("Двойной клик или Enter — играть  ·  ПКМ — все "
                        "действия"),
                 bg=BG, fg=MUTED, font=font(9)).pack(side="left", padx=(16, 0))
        _hyperlink(footer, TELEGRAM_HANDLE, TELEGRAM_URL, bg=BG
                   ).pack(side="right", padx=(12, 0))
        tk.Label(footer, text="v" + __version__, bg=BG, fg=MUTED,
                 font=font(9)).pack(side="right", padx=(12, 0))

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

        lang_cb = ttk.Combobox(footer, textvariable=lang_var,
                               values=("ru", "en"), state="readonly",
                               width=4, font=font(9))
        lang_cb.pack(side="right", padx=(6, 0))
        lang_cb.bind("<<ComboboxSelected>>", _on_lang)
        theme_cb = ttk.Combobox(footer, textvariable=theme_var,
                                values=("dark", "light", "wow"),
                                state="readonly", width=6, font=font(9))
        theme_cb.pack(side="right", padx=(6, 0))
        theme_cb.bind("<<ComboboxSelected>>", _on_theme)

        self.root.bind("<Control-f>", lambda _e: self._search_entry.focus_set())
        self.root.bind("<Control-n>", lambda _e: self.account_dialog(None))

        self.render_rows()

    # ── sorting ──────────────────────────────────────────────────────────────

    def sort_options(self):
        """(column key, label) pairs for the footer picker. "" is the manual
        order you get by dragging rows around."""
        opts = [("", t("Вручную")),
                ("name", t("Персонаж"))]
        for col in self._cols:
            label, _w, _a, _g = col_meta(col)
            opts.append((col, t(label)))
        return opts

    def _refresh_sort_picker(self):
        box = getattr(self, "_sort_box", None)
        if box is None or not box.winfo_exists():
            return
        opts = self.sort_options()
        box.configure(values=[lbl for _k, lbl in opts])
        current = (self.cfg.get("sort") or {}).get("col") or ""
        if current and current not in [k for k, _l in opts]:
            current = ""
        self._sort_var.set(dict(opts).get(current, opts[0][1]))
        reverse = bool((self.cfg.get("sort") or {}).get("reverse"))
        self._sort_dir.set_enabled(bool(current))
        for lab in self._sort_dir._labels:
            lab.configure(text="\u25BC" if reverse else "\u25B2")

    def _on_sort_pick(self, _e=None):
        opts = self.sort_options()
        key = next((k for k, lbl in opts if lbl == self._sort_var.get()), "")
        srt = dict(self.cfg.get("sort") or {})
        if key:
            srt["col"] = key
            srt.setdefault("reverse", False)
        else:
            srt = {}
        self.cfg["sort"] = srt
        save_cfg(self.cfg)
        self._refresh_sort_picker()
        self.render_rows()

    def _toggle_sort_dir(self):
        srt = dict(self.cfg.get("sort") or {})
        if not srt.get("col"):
            return
        srt["reverse"] = not srt.get("reverse")
        self.cfg["sort"] = srt
        save_cfg(self.cfg)
        self._refresh_sort_picker()
        self.render_rows()

    def _clear_sort(self):
        """Dragging a row means "I'll order these myself"."""
        if (self.cfg.get("sort") or {}).get("col"):
            self.cfg["sort"] = {}
            self._refresh_sort_picker()

    def _fit_columns(self, _e=None):
        """Give spare width to the name column; shrink proportionally when the
        configured widths don't fit. Display only — saved widths are kept."""
        try:
            avail = self.tree.winfo_width() - 4
            if avail <= 1:
                return
            wcfg = self.cfg.get("column_widths", {})
            keys = ["name"] + list(self._cols)
            ids = ["#0"] + list(self._cols)
            desired = [int(wcfg.get(k, 240 if k == "name" else col_meta(k)[1]))
                       for k in keys]
            total = sum(desired)
            if total <= avail:
                desired[0] += avail - total
                for cid, w in zip(ids, desired):
                    self.tree.column(cid, width=w)
            else:
                scale = avail / total
                for cid, w in zip(ids, desired):
                    self.tree.column(cid, width=max(40, int(w * scale)))
        except Exception:
            pass

    def _save_col_widths(self, _e=None):
        """Persist column widths only when the user dragged a heading edge."""
        if not getattr(self, "_resizing", False):
            return
        self._resizing = False
        try:
            widths = dict(self.cfg.get("column_widths", {}))
            for key, cid in [("name", "#0")] + [(c, c) for c in self._cols]:
                widths[key] = self.tree.column(cid, "width")
            if widths != self.cfg.get("column_widths"):
                self.cfg["column_widths"] = widths
                save_cfg(self.cfg)
        except Exception:
            pass

    # ── rows ─────────────────────────────────────────────────────────────────

    def _sorted_items(self, items):
        """Apply the configured sort to (index, character) pairs. Sorting works
        inside each account — accounts themselves keep their own order."""
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
                rec = INGAME.get(str(c.get("name", "")).lower()) or {}
                v = rec.get(col, "") if numeric else col_meta(col)[3](c)
            if numeric:
                digits = "".join(ch for ch in str(v) if ch.isdigit())
                return int(digits) if digits else -1
            return str(v).lower()
        return sorted(items, key=_key, reverse=bool(srt.get("reverse")))

    @staticmethod
    def _matches(entry, q):
        if not q:
            return True
        hay = " ".join(str(entry.get(k, "")) for k in
                       ("name", "account", "realm", "realmlist")).lower()
        hay += " " + class_disp(entry.get("class", "")).lower()
        return q in hay

    def _account_values(self, acc, chars):
        """What an account row shows in the data columns: its own realm and
        server, and totals over its characters where adding up makes sense."""
        vals = []
        for col in self._cols:
            if col in ("realm", "realmlist", "account"):
                vals.append(acc.get(col, ""))
            elif col in ("gold", "played"):
                total = 0
                for _i, c in chars:
                    rec = INGAME.get(str(c.get("name", "")).lower()) or {}
                    try:
                        total += int(rec.get(col) or 0)
                    except (TypeError, ValueError):
                        pass
                vals.append((fmt_gold(total) if col == "gold"
                             else _fmt_played(total)) if total else "")
            else:
                vals.append("")
        return tuple(vals)

    def render_rows(self):
        tree = getattr(self, "tree", None)
        if tree is None or not tree.winfo_exists():
            return
        q = self.search_var.get().strip().lower()
        opened = {iid: bool(tree.item(iid, "open"))
                  for iid in tree.get_children("")}
        selected = tree.selection()
        tree.delete(*tree.get_children(""))

        groups = roster_groups(self.cfg)
        n_acc = n_chars = 0
        for acc_idx, acc, chars in groups:
            n_chars += len(chars)
            shown = [(i, c) for i, c in chars if self._matches(c, q)]
            acc_hit = acc is not None and self._matches(acc, q)
            if q and not shown and not acc_hit:
                continue
            if q and acc_hit and not shown:
                shown = chars
            shown = self._sorted_items(shown)
            if acc is None:
                parent = tree.insert("", "end", iid="orphans",
                                     text="  " + t("Без аккаунта"),
                                     values=("",) * len(self._cols),
                                     open=True, tags=("orphans",))
            else:
                n_acc += 1
                parent = str(acc_idx)
                label = "  %s   ·   %s" % (
                    acc.get("account", ""),
                    len(chars) if chars else t("ждёт первого входа"))
                collapsed = acc_key(acc.get("account")) in (
                    self.cfg.get("collapsed_accounts") or [])
                tree.insert("", "end", iid=parent, text=label,
                            values=self._account_values(acc, chars),
                            open=True if q else opened.get(parent,
                                                           not collapsed),
                            tags=("account",))
            for idx, c in shown:
                tree.insert(parent, "end", iid=str(idx),
                            text=c.get("name", ""),
                            values=tuple(col_meta(col)[3](c)
                                         for col in self._cols),
                            tags=("cls_" + c.get("class", ""),))

        for iid in selected:
            if tree.exists(iid):
                tree.selection_set(iid)
                tree.see(iid)
                break

        if self.cfg.get("characters"):
            self._empty.place_forget()
        else:
            self._empty.place(relx=0.5, rely=0.45, anchor="center")

        self._render_chips(n_acc, n_chars)
        self._refresh_sort_picker()
        self._update_actions()
        self._refresh_tray()

    def _render_chips(self, n_acc, n_chars):
        for w in self._chips.winfo_children():
            w.destroy()
        self.summary_var.set(self._account_summary())
        chips = [(t("Аккаунтов"), str(n_acc)), (t("Персонажей"), str(n_chars))]
        summary = self.summary_var.get()
        for part in summary.split("     •     "):
            if ": " in part:
                k, v = part.split(": ", 1)
                chips.append((k, v))
        for k, v in chips:
            chip = tk.Frame(self._chips, bg=BTN_BG)
            chip.pack(side="left", padx=(0, 8))
            tk.Label(chip, text=k, bg=BTN_BG, fg=MUTED, font=font(9)
                     ).pack(side="left", padx=(10, 4), pady=4)
            tk.Label(chip, text=v, bg=BTN_BG, fg=TEXT, font=font(9, "bold")
                     ).pack(side="left", padx=(0, 10), pady=4)

    # ── selection & actions ──────────────────────────────────────────────────

    def selected_entry(self):
        """(index, entry) of the selected row, or (None, None)."""
        sel = self.tree.selection() if getattr(self, "tree", None) else ()
        if not sel or sel[0] == "orphans":
            return None, None
        try:
            idx = int(sel[0])
            return idx, self.cfg["characters"][idx]
        except (ValueError, IndexError):
            return None, None

    def _update_actions(self):
        has = self.selected_entry()[0] is not None
        for b in (getattr(self, "_btn_edit", None),
                  getattr(self, "_btn_delete", None)):
            if b is not None:
                b.set_enabled(has)

    def _on_double(self, e):
        """Double-click launches — including account rows. Folding is what the
        arrow on the left is for, so ttk's own double-click toggle is
        suppressed here."""
        iid = self.tree.identify_row(e.y)
        if not iid or iid == "orphans":
            return "break"
        if self.tree.identify_element(e.x, e.y) == "Treeitem.indicator":
            return              # let the arrow fold the account
        self._launch_char(self.cfg["characters"][int(iid)])
        return "break"

    def _on_fold(self, opened, e=None):
        """Remember which accounts are collapsed."""
        iid = self.tree.focus() or (self.tree.selection() or ("",))[0]
        if not iid or iid == "orphans":
            return
        try:
            entry = self.cfg["characters"][int(iid)]
        except (ValueError, IndexError):
            return
        key = acc_key(entry.get("account"))
        try:                       # keep the row itself in step with the state
            self.tree.item(iid, open=bool(opened))
        except tk.TclError:
            pass
        collapsed = [k for k in (self.cfg.get("collapsed_accounts") or [])
                     if k != key]
        if not opened:
            collapsed.append(key)
        if collapsed != (self.cfg.get("collapsed_accounts") or []):
            self.cfg["collapsed_accounts"] = collapsed
            save_cfg(self.cfg)

    def _on_context(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid or iid == "orphans":
            return
        self.tree.selection_set(iid)
        idx = int(iid)
        entry = self.cfg["characters"][idx]
        m = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=TEXT, bd=0,
                    activebackground=SEL_BG, activeforeground=SEL_FG,
                    font=font(10), relief="flat")
        if is_account_entry(entry):
            m.add_command(label=t("Войти в аккаунт"),
                          command=lambda: self._launch_char(entry))
            m.add_separator()
            m.add_command(label=t("Изменить аккаунт"),
                          command=lambda: self.account_dialog(idx))
        else:
            m.add_command(label=t("Играть"),
                          command=lambda: self._launch_char(entry))
            m.add_separator()
            m.add_command(label=t("Изменить"),
                          command=lambda: self.char_dialog(idx))
        m.add_command(label=t("Ярлык на рабочий стол"),
                      command=lambda: self._make_shortcut(entry))
        m.add_separator()
        m.add_command(label=t("Удалить"), command=self.delete_selected)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _make_shortcut(self, entry):
        value = (entry.get("name") or "").strip() or entry.get("account", "")
        try:
            path = create_desktop_shortcut(value, value)
            self._add_banner("shortcut",
                             t("Ярлык создан на рабочем столе:\n{path}")
                             .format(path=path).replace("\n", " "),
                             accent=ACCENT)
        except Exception as e:
            messagebox.showerror(APP_TITLE,
                                 t("Не удалось создать ярлык:\n{e}").format(e=e))

    # ── drag to reorder ──────────────────────────────────────────────────────

    def _on_drag_start(self, e):
        self._resizing = (self.tree.identify_region(e.x, e.y) == "separator")
        iid = self.tree.identify_row(e.y)
        # Reordering needs the full list in front of us; a search hides rows.
        if not iid or iid == "orphans" or self.search_var.get().strip():
            self._drag = None
            return
        self._drag = {"iid": iid, "moved": False}

    def _on_drag_motion(self, e):
        d = self._drag
        if not d:
            return
        src = d["iid"]
        tgt = self.tree.identify_row(e.y)
        if not tgt or tgt == src or tgt == "orphans":
            return
        parent = self.tree.parent(src)
        if parent == "":                     # an account moves among accounts
            while self.tree.parent(tgt):
                tgt = self.tree.parent(tgt)
            if tgt == src or tgt == "orphans":
                return
        elif self.tree.parent(tgt) != parent:  # a character stays in its account
            return
        self.tree.move(src, parent, self.tree.index(tgt))
        d["moved"] = True

    def _on_drag_drop(self, _e):
        d, self._drag = self._drag, None
        if not d or not d["moved"]:
            return
        self._clear_sort()          # a manual order replaces any sorting
        entries = self.cfg["characters"]
        order = []
        for top in self.tree.get_children(""):
            if top != "orphans":
                order.append(int(top))
            order.extend(int(c) for c in self.tree.get_children(top))
        if sorted(order) != list(range(len(entries))):
            self.render_rows()                # something is filtered: bail out
            return
        self.cfg["characters"] = [entries[i] for i in order]
        save_cfg(self.cfg)
        self.render_rows()

    # ── hover card ───────────────────────────────────────────────────────────

    def _on_tree_motion(self, e):
        if not self.cfg.get("hover_card", True) or self._drag:
            return
        iid = self.tree.identify_row(e.y)
        if not iid or iid == "orphans":
            self._hide_card()
            return
        if iid == self._card_row:
            return
        self._hide_card()
        try:
            c = self.cfg["characters"][int(iid)]
        except (ValueError, IndexError):
            return
        if is_account_entry(c):
            return
        self._card_row = iid
        self._show_card(c, e.x_root + 18, e.y_root + 12)

    # ── tray ─────────────────────────────────────────────────────────────────

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

        def launcher(entry):
            # Hop to the UI thread and go through _launch_char, which checks
            # the master-password lock and the double-launch guard.
            def _launch(_i=None, _it=None):
                self.root.after(0, lambda: (
                    entry in self.cfg.get("characters", [])
                    and self._launch_char(entry)))
            return _launch

        def build_menu():
            items = [pystray.MenuItem(t("Показать"), show, default=True),
                     pystray.Menu.SEPARATOR]
            for _ai, acc, chars in roster_groups(self.cfg)[:12]:
                if acc is None:
                    continue
                sub = [pystray.MenuItem(t("Войти в аккаунт"), launcher(acc))]
                if chars:
                    sub.append(pystray.Menu.SEPARATOR)
                sub += [pystray.MenuItem(c.get("name", "?"), launcher(c))
                        for _i, c in chars[:20]]
                items.append(pystray.MenuItem(acc.get("account", "?"),
                                              pystray.Menu(*sub)))
            items += [pystray.Menu.SEPARATOR,
                      pystray.MenuItem(t("Выход"), quit_)]
            return pystray.Menu(*items)

        self._tray_icon = pystray.Icon("wow_manager", icon_img,
                                       APP_TITLE, build_menu())
        self._build_tray_menu = build_menu
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    # ── launching & editing ──────────────────────────────────────────────────

    def launch_selected(self):
        _idx, entry = self.selected_entry()
        if entry is not None:
            self._launch_char(entry)

    def edit_selected(self):
        idx, entry = self.selected_entry()
        if entry is None:
            return
        if is_account_entry(entry):
            self.account_dialog(idx)
        else:
            self.char_dialog(idx)

    def delete_selected(self):
        idx, entry = self.selected_entry()
        if entry is None:
            return
        if is_account_entry(entry):
            login = entry.get("account", "")
            n = sum(1 for e in self.cfg["characters"]
                    if not is_account_entry(e)
                    and acc_key(e.get("account")) == acc_key(login))
            text = (t("Удалить аккаунт «{name}» и его персонажей ({n})?")
                    .format(name=login, n=n) if n else
                    t("Удалить «{name}»?").format(name=login))
            if not messagebox.askyesno(APP_TITLE, text):
                return
            remove_account(self.cfg, login)
        else:
            if not messagebox.askyesno(
                    APP_TITLE, t("Удалить «{name}»?").format(
                        name=entry.get("name", ""))):
                return
            self.cfg["characters"].pop(idx)
            # Otherwise the next login would quietly import it again.
            hide_character(self.cfg, entry)
        save_cfg(self.cfg)
        self.render_rows()

    def _select_entry(self, entry):
        try:
            idx = self.cfg["characters"].index(entry)
        except ValueError:
            return
        iid = str(idx)
        if self.tree.exists(iid):
            parent = self.tree.parent(iid)
            if parent:
                self.tree.item(parent, open=True)
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _dialog(self, title):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        tk.Label(dlg, text=title, bg=BG, fg=TEXT, font=font(14, "bold")
                 ).pack(padx=22, pady=(18, 4), anchor="w")
        return dlg

    def _field(self, dlg, label, widget_factory):
        tk.Label(dlg, text=label, bg=BG, fg=MUTED, font=font(9), anchor="w"
                 ).pack(fill="x", padx=22, pady=(10, 2))
        w = widget_factory(dlg)
        w.pack(fill="x", padx=22, ipady=5)
        return w

    def _graphics_field(self, dlg, current, for_character=False):
        """Preset picker plus a button to the builder. Returns (var, getter)."""
        tk.Label(dlg, text=t("Графика при запуске"), bg=BG, fg=MUTED,
                 font=font(9), anchor="w").pack(fill="x", padx=22, pady=(10, 2))
        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=22)
        opts = {"list": graphics_options(self.cfg, for_character)}
        var = tk.StringVar()
        box = ttk.Combobox(row, textvariable=var, state="readonly",
                           font=font(10))
        box.pack(side="left", fill="x", expand=True, ipady=3)

        def refresh(select=None):
            opts["list"] = graphics_options(self.cfg, for_character)
            box.configure(values=[lbl for _k, lbl in opts["list"]])
            want = select if select is not None else current
            var.set(dict(opts["list"]).get(want, opts["list"][0][1]))

        def getter():
            return next((k for k, lbl in opts["list"] if lbl == var.get()), "")

        def open_builder():
            chosen = getter()
            self.graphics_constructor(dlg, on_close=lambda: refresh(chosen))

        tk.Button(row, text=t("Настроить…"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=10, command=open_builder).pack(side="left", padx=(8, 0))
        refresh()
        return var, getter

    def account_dialog(self, idx):
        editing = idx is not None
        acc = self.cfg["characters"][idx] if editing else {}
        last_acc = next((e for e in reversed(self.cfg.get("characters", []))
                         if is_account_entry(e)), {})
        dlg = self._dialog(t("Аккаунт"))

        login_var = tk.StringVar(value=acc.get("account", ""))
        pass_var = tk.StringVar(value=acc.get("password", ""))
        totp_var = tk.StringVar(value=acc.get("totp_secret", ""))
        realm_var = tk.StringVar(value=acc.get("realm")
                                 or last_acc.get("realm")
                                 or (self.cfg.get("realms") or [""])[0])
        rl_var = tk.StringVar(value=acc.get("realmlist")
                              or last_acc.get("realmlist")
                              or (self.cfg.get("realmlists") or [""])[0])

        first = self._field(dlg, t("Логин аккаунта"),
                            lambda p: _make_entry(p, login_var))
        pw = self._field(dlg, t("Пароль"),
                         lambda p: _make_entry(p, pass_var, show="●"))
        show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(dlg, text=t("Показать пароль"), variable=show_var,
                       bg=BG, fg=MUTED, activebackground=BG,
                       activeforeground=TEXT, selectcolor=ENTRY_BG,
                       font=font(9), anchor="w",
                       command=lambda: pw.configure(
                           show="" if show_var.get() else "●")
                       ).pack(fill="x", padx=20)

        self._field(dlg, t("Реалм"), lambda p: ttk.Combobox(
            p, textvariable=realm_var, values=self.cfg.get("realms", []),
            font=font(10)))
        self._field(dlg, t("Realmlist"), lambda p: ttk.Combobox(
            p, textvariable=rl_var, values=self.cfg.get("realmlists", []),
            font=font(10)))
        gfx_var, gfx_get = self._graphics_field(dlg, acc.get("graphics", ""))

        tk.Label(dlg, text=t("Секрет 2FA (Google / 2FAS Auth / Yandex "
                             "Authenticator)"),
                 bg=BG, fg=MUTED, font=font(9), anchor="w"
                 ).pack(fill="x", padx=22, pady=(10, 2))
        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=22)
        _make_entry(row, totp_var).pack(side="left", fill="x", expand=True,
                                        ipady=5)
        code_var = tk.StringVar()
        tk.Label(row, textvariable=code_var, bg=BG, fg=ACCENT, width=8,
                 font=font(10, "bold")).pack(side="left", padx=(8, 0))

        def refresh_code(*_):
            sec = totp_var.get().strip()
            code_var.set("" if not sec else (compute_totp(sec)
                                             or t("невалидно")))
        totp_var.trace_add("write", refresh_code)
        refresh_code()
        tk.Label(dlg, text=t("Если 2FA не подключена — оставь пусто."),
                 bg=BG, fg=MUTED, font=font(8), anchor="w"
                 ).pack(fill="x", padx=22)

        if not editing:
            tk.Label(dlg,
                     text=t("Персонажей вводить не нужно: при первом входе в "
                            "аккаунт они добавятся сами."),
                     bg=BG, fg=ACCENT, font=font(9), wraplength=380,
                     justify="left", anchor="w"
                     ).pack(fill="x", padx=22, pady=(12, 0))

        def save():
            login = login_var.get().strip()
            if not login:
                messagebox.showwarning(APP_TITLE, t("Введи логин аккаунта."),
                                       parent=dlg)
                return
            other = account_entry_for(self.cfg, login)
            if other is not None and other is not acc:
                messagebox.showwarning(
                    APP_TITLE, t("Аккаунт «{name}» уже есть.").format(
                        name=login), parent=dlg)
                return
            fields = {"account": login, "password": pass_var.get(),
                      "totp_secret": normalize_totp_secret(totp_var.get()),
                      "realm": realm_var.get().strip(),
                      "realmlist": rl_var.get().strip(),
                      "graphics": gfx_get()}
            if editing:
                old = acc.get("account", "")
                for e in self.cfg["characters"]:
                    if (not is_account_entry(e)
                            and acc_key(e.get("account")) == acc_key(old)):
                        e["account"] = login
                acc.update(fields)
                target = acc
            else:
                target = dict(fields, name="", **{"class": ""})
                self.cfg.setdefault("characters", []).append(target)
            normalize_roster(self.cfg)
            save_cfg(self.cfg)
            dlg.destroy()
            self.render_rows()
            self._select_entry(target)
            if not editing:
                self._add_banner(
                    "new_account",
                    t("Аккаунт «{name}» добавлен. Войди в него — персонажи "
                      "подтянутся сами.").format(name=login),
                    t("Войти"), lambda e=target: (
                        self._dismiss_banner("new_account"),
                        self._launch_char(e)),
                    accent=ACCENT)

        FlatButton(dlg, t("Сохранить") if editing else t("Добавить"),
                   kind="primary", command=save
                   ).pack(fill="x", padx=22, pady=(18, 20))
        dlg.bind("<Return>", lambda _e: save())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        first.focus_set()
        self._fit_dialog(dlg, 440)
        dlg.grab_set()

    def char_dialog(self, idx):
        """Edit a character. Characters themselves come from the game — the
        patch reports the account's roster on the first login."""
        ch = self.cfg["characters"][idx]
        logins = [e.get("account", "") for e in self.cfg.get("characters", [])
                  if is_account_entry(e)]
        start_acc = ch.get("account") or (logins[0] if logins else "")
        start_acc = next((l for l in logins if acc_key(l) == acc_key(start_acc)),
                         start_acc)
        acc_entry = account_entry_for(self.cfg, start_acc) or {}

        dlg = self._dialog(t("Персонаж"))
        editing = True
        name_var = tk.StringVar(value=ch.get("name", ""))
        acc_var = tk.StringVar(value=start_acc)
        stored = ch.get("class", "")
        class_var = tk.StringVar(value=class_disp(stored) if stored
                                 else t(NO_CLASS))
        realm_var = tk.StringVar(value=ch.get("realm")
                                 or acc_entry.get("realm", ""))

        first = self._field(dlg, t("Ник персонажа"),
                            lambda p: _make_entry(p, name_var))
        self._field(dlg, t("Аккаунт"), lambda p: ttk.Combobox(
            p, textvariable=acc_var, values=logins, state="readonly",
            font=font(10)))
        self._field(dlg, t("Класс"), lambda p: ttk.Combobox(
            p, textvariable=class_var, state="readonly", font=font(10),
            values=[t(NO_CLASS)] + [class_disp(c) for c in WOW_CLASSES]))
        self._field(dlg, t("Реалм"), lambda p: ttk.Combobox(
            p, textvariable=realm_var, values=self.cfg.get("realms", []),
            font=font(10)))
        _cgfx_var, cgfx_get = self._graphics_field(
            dlg, ch.get("graphics", ""), for_character=True)
        tk.Label(dlg, text=t("Пароль и 2FA берутся из аккаунта."),
                 bg=BG, fg=MUTED, font=font(8), anchor="w"
                 ).pack(fill="x", padx=22, pady=(6, 0))

        def save():
            name = name_var.get().strip()
            login = acc_var.get().strip()
            if not name:
                messagebox.showwarning(APP_TITLE, t("Введи ник персонажа."),
                                       parent=dlg)
                return
            realm = realm_var.get().strip()
            for e in self.cfg["characters"]:
                if (e is not ch and not is_account_entry(e)
                        and acc_key(e.get("account")) == acc_key(login)
                        and (e.get("name") or "").strip().lower() == name.lower()
                        and (e.get("realm") or "").strip().lower()
                        == realm.lower()):
                    messagebox.showwarning(
                        APP_TITLE, t("«{name}» уже есть на этом аккаунте.")
                        .format(name=name), parent=dlg)
                    return
            cls_disp = class_var.get().strip()
            cls = "" if cls_disp == t(NO_CLASS) else class_canon(cls_disp)
            fields = {"name": name, "account": login, "class": cls,
                      "realm": realm,
                      "graphics": cgfx_get()}
            if editing:
                moved = acc_key(ch.get("account")) != acc_key(login)
                ch.update(fields)
                if moved:                 # re-slot it under the new account
                    self.cfg["characters"].remove(ch)
                    insert_character(self.cfg, ch)
                target = ch
            else:
                target = fields
                insert_character(self.cfg, target)
            normalize_roster(self.cfg)
            save_cfg(self.cfg)
            dlg.destroy()
            self.render_rows()
            self._select_entry(target)

        FlatButton(dlg, t("Сохранить") if editing else t("Добавить"),
                   kind="primary", command=save
                   ).pack(fill="x", padx=22, pady=(18, 20))
        dlg.bind("<Return>", lambda _e: save())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        first.focus_set()
        self._fit_dialog(dlg, 420)
        dlg.grab_set()

    # ── characters reported by the game ──────────────────────────────────────

    def _check_char_lists(self):
        """Called from the watcher thread: notice new list files cheaply and
        hand the actual import to the UI thread."""
        if not self.cfg.get("auto_import_chars", True):
            return
        wow = self.cfg.get("wow_path", "")
        sig = charlist_signature(wow)
        if sig and sig != getattr(self, "_charlist_sig", None):
            self._charlist_sig = sig
            lists = read_char_lists(wow)
            self.root.after(0, lambda: self._import_char_lists(lists))

    def _import_char_lists(self, lists):
        if not self.cfg.get("auto_import_chars", True):
            return []
        added = import_char_lists(self.cfg, lists)
        if not added:
            return added
        save_cfg(self.cfg)
        self.render_rows()
        shown = ", ".join(added[:6]) + ("…" if len(added) > 6 else "")
        self._add_banner("imported",
                         t("Добавлены персонажи ({n}): {names}").format(
                             n=len(added), names=shown),
                         accent=ACCENT)
        return added

    # ── kept from the previous window ─────────────────────────────────────

    def rebuild(self):
        self._save_window_state()
        self._hide_card()
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self.build()

    def _account_summary(self):
        """One line over the whole roster: total gold, best geared character,
        total time played. Built from what the addon already collects, so it
        costs nothing extra."""
        def as_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        gold = played = seen = 0
        best = None
        for c in self.cfg.get("characters", []):
            rec = INGAME.get(str(c.get("name", "")).lower())
            if not rec:
                continue
            seen += 1
            gold += as_int(rec.get("gold"))
            played += as_int(rec.get("played"))
            gs = as_int(rec.get("gs"))
            if gs and (best is None or gs > best[1]):
                best = (rec.get("name") or c.get("name", ""), gs)
        if not seen:
            return t("Данных пока нет — зайди в игру с аддоном.")
        parts = [t("Всего золота: {g}").format(g=fmt_gold(gold))]
        if best:
            parts.append(t("Лучший ГС: {n} ({gs})").format(n=best[0],
                                                           gs=best[1]))
        if played:
            parts.append(t("Наиграно: {t}").format(t=_fmt_played(played)))
        return "     •     ".join(parts)

    def _hide_card(self):
        if self._card is not None:
            try:
                self._card.destroy()
            except Exception:
                pass
            self._card = None
        self._card_row = None

    def _show_card(self, char, x, y):
        cls = char.get("class", "")
        color = CLASS_COLORS.get(cls, ACCENT)
        win = tk.Toplevel(self.root)
        win.withdraw()          # keep it off-screen until it has a position
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
                elif key == "arenaTeams":
                    teams = rec.get("arenaTeams") or []
                    if isinstance(teams, dict):
                        teams = [v for _k, v in sorted(teams.items())]
                    printed = False
                    for tm in teams:
                        if not isinstance(tm, dict):
                            continue
                        if not printed:
                            tk.Label(body, text=field_label(key) + ":",
                                     bg=PANEL, fg=MUTED, font=F).pack(
                                         anchor="w", padx=PX, pady=(4, 0))
                            printed = True
                        size = tm.get("size") or "?"
                        tk.Label(body, bg=PANEL, fg=TEXT, font=F,
                                 text="  " + t("{size} — рейтинг {r}, игр {n}")
                                 .format(size="%sx%s" % (size, size),
                                         r=int(tm.get("rating") or 0),
                                         n=int(tm.get("mine") or 0))
                                 ).pack(anchor="w", padx=PX, pady=0)
                else:
                    row(field_label(key) + ":", _ig_display(rec, key, long=True))

        tk.Frame(body, bg=PANEL, height=5).pack()

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = min(x, sw - w - 8)
        y = min(y, sh - h - 8)
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        style_window_chrome(win, rounded=True)
        self._card = win

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

    def _async_err(self, msg):
        # Worker-thread callback for async errors (loader button not found etc).
        # tkinter is single-threaded — hop back to the UI thread via after().
        self.root.after(0, lambda m=msg: messagebox.showerror(APP_TITLE, m))

    def _launch_char(self, char):
        if getattr(self, "_harvesting", False):
            messagebox.showinfo(APP_TITLE, t("Идёт сбор данных — дождись "
                                             "окончания."))
            return
        if SECRETS_LOCKED:
            messagebox.showwarning(
                APP_TITLE,
                t("Пароли заблокированы. Введи мастер-пароль, чтобы запускать "
                  "игру."))
            self._relock_prompt()
            return
        # An impatient second double-click used to start a second client on the
        # same account; the server then drops one of the two sessions and the
        # player lands back on character select.
        key = "%s|%s" % (char.get("name", ""), char.get("account", ""))
        now = time.monotonic()
        if now - self._last_launch.get(key, float("-inf")) < LAUNCH_COOLDOWN_SEC:
            return
        self._last_launch[key] = now
        try:
            launch_wow(self.cfg, char, on_error=self._async_err)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

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

    def _center_window(self, win, width, height):
        """Put a dialog in the middle of the main window (or of the screen
        while the main window is hidden in the tray). Without an explicit
        position Windows drops new windows into the top-left corner."""
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        root = self.root
        try:
            over_root = (root.winfo_viewable()
                         and root.state() not in ("withdrawn", "iconic"))
        except tk.TclError:
            over_root = False
        if over_root:
            cx = root.winfo_rootx() + root.winfo_width() // 2
            cy = root.winfo_rooty() + root.winfo_height() // 2
            vx, vy, vw, vh = virtual_screen(win)
        else:
            cx, cy = sw // 2, sh // 2
            vx, vy, vw, vh = 0, 0, sw, sh
        x = max(vx, min(cx - width // 2, vx + vw - width))
        y = max(vy, min(cy - height // 2, vy + vh - height - 40))
        win.geometry("%dx%d+%d+%d" % (width, height, x, y))
        win._placed = True

    def _on_toplevel_map(self, e):
        """Safety net for any dialog that doesn't size itself through
        _fit_dialog / _fit_scroll: if it lands in the corner, centre it."""
        w = e.widget
        if not isinstance(w, tk.Toplevel) or getattr(w, "_placed", False):
            return
        try:
            if w.overrideredirect():
                return                         # the hover card places itself
        except tk.TclError:
            return
        w._placed = True
        if w.winfo_rootx() < 60 and w.winfo_rooty() < 90:
            self._center_window(w, max(w.winfo_width(), w.winfo_reqwidth()),
                                max(w.winfo_height(), w.winfo_reqheight()))

    def _restore_geometry(self):
        """Saved size and position, unless that position is off every monitor
        (a screen was unplugged) — then centre on the main screen."""
        geo = self.cfg.get("win_geometry") or ""
        m = re.match(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$", geo)
        w, h = WIN_W, WIN_H
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            x, y = int(m.group(3)), int(m.group(4))
            vx, vy, vw, vh = virtual_screen(self.root)
            if (vx - 50 <= x <= vx + vw - 200 and vy - 10 <= y <= vy + vh - 120):
                self.root.geometry(geo)
                return
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 80)
        self.root.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2,
                                            max(0, (sh - h) // 2 - 20)))

    def _fit_dialog(self, dlg, width):
        """Size a (non-scrolling) dialog to its content height, capped."""
        dlg.update_idletasks()
        sh = dlg.winfo_screenheight()
        h = min(int(sh * 0.92), max(200, dlg.winfo_reqheight()))
        self._center_window(dlg, int(width), h)
        style_window_chrome(dlg)

    def _fit_scroll(self, dlg, body, width, extra=80):
        """Size a scrollable dialog to its content, capped to the screen."""
        dlg.update_idletasks()
        sh = dlg.winfo_screenheight()
        h = min(int(sh * 0.92), max(260, body.winfo_reqheight() + extra))
        self._center_window(dlg, int(width), h)
        style_window_chrome(dlg)

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

    def roster_dialog(self, parent):
        """The whole roster as text an officer can paste into a forum post."""
        if not roster_rows(self.cfg):
            messagebox.showinfo(
                APP_TITLE,
                t("Нет персонажей с данными. Зайди в игру с аддоном хотя бы "
                  "раз."), parent=parent)
            return

        dlg = tk.Toplevel(parent)
        dlg.title(t("Ростер"))
        dlg.configure(bg=BG)
        dlg.grab_set()

        top = tk.Frame(dlg, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text=t("Формат:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        fmt_var = tk.StringVar(value=ROSTER_FORMATS[0])
        fmt_cb = ttk.Combobox(top, textvariable=fmt_var,
                              values=list(ROSTER_FORMATS), state="readonly",
                              width=12, font=("Segoe UI", 9))
        fmt_cb.pack(side="left", padx=(8, 0))

        text = tk.Text(dlg, height=18, width=90, bg=ENTRY_BG, fg=TEXT,
                       relief="flat", highlightthickness=1,
                       highlightbackground=BORDER, wrap="none",
                       font=("Consolas", 9))
        text.pack(fill="both", expand=True, padx=16)

        def render(_e=None):
            text.delete("1.0", "end")
            text.insert("1.0", format_roster(self.cfg, fmt_var.get()))
        fmt_cb.bind("<<ComboboxSelected>>", render)
        render()

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(text.get("1.0", "end-1c"))
            messagebox.showinfo(APP_TITLE,
                                t("Скопировано в буфер обмена."), parent=dlg)

        def save():
            path = filedialog.asksaveasfilename(
                parent=dlg, title=t("Сохранить ростер"), defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("All files", "*.*")])
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text.get("1.0", "end-1c"))
                messagebox.showinfo(APP_TITLE,
                                    t("Сохранено:\n{p}").format(p=path),
                                    parent=dlg)
            except OSError as e:
                messagebox.showerror(APP_TITLE, str(e), parent=dlg)

        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=16, pady=(8, 14))
        tk.Button(row, text=t("Копировать"), bg=PRIMARY_BG, fg=PRIMARY_FG,
                  relief="flat", padx=16, pady=6, command=copy
                  ).pack(side="left")
        tk.Button(row, text=t("Сохранить в файл…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=14, pady=6, command=save
                  ).pack(side="left", padx=(8, 0))
        tk.Button(row, text=t("Закрыть"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=14, pady=6, command=dlg.destroy).pack(side="right")
        self._fit_dialog(dlg, 760)

    def wtf_transfer_dialog(self, parent):
        """Copy one character's UI / keybinds / addon settings onto others."""
        wow = self.cfg.get("wow_path", "")
        chars = list_wtf_characters(wow)
        if not chars:
            messagebox.showinfo(APP_TITLE,
                                t("В папке WTF нет ни одного персонажа."),
                                parent=parent)
            return

        labels = ["%s / %s / %s" % (a, r, c) for a, r, c, _p in chars]
        paths = [p for _a, _r, _c, p in chars]

        dlg = tk.Toplevel(parent)
        dlg.title(t("Перенос настроек персонажа"))
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text=t("Откуда:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=18, pady=(14, 0))
        src_var = tk.StringVar(value=labels[0])
        ttk.Combobox(dlg, textvariable=src_var, values=labels,
                     state="readonly", font=("Segoe UI", 9)
                     ).pack(fill="x", padx=18, ipady=3)

        tk.Label(dlg, text=t("Куда (можно выбрать несколько):"), bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)
                 ).pack(fill="x", padx=18, pady=(10, 0))
        list_wrap = tk.Frame(dlg, bg=BG)
        list_wrap.pack(fill="both", expand=True, padx=18)
        targets = tk.Listbox(list_wrap, selectmode="extended", height=9,
                             bg=ENTRY_BG, fg=TEXT, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER,
                             font=("Segoe UI", 9), exportselection=False)
        targets.pack(side="left", fill="both", expand=True)
        tsb = ttk.Scrollbar(list_wrap, orient="vertical",
                            command=targets.yview)
        tsb.pack(side="right", fill="y")
        targets.configure(yscrollcommand=tsb.set)
        for lb in labels:
            targets.insert("end", lb)

        tk.Label(dlg, text=t("Что переносить:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=18, pady=(10, 0))
        group_vars = {}
        for key, label, _names in WTF_GROUPS:
            var = tk.BooleanVar(value=(key in ("config", "addons")))
            group_vars[key] = var
            tk.Checkbutton(dlg, text=t(label), variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=TEXT,
                           selectcolor=ENTRY_BG, font=("Segoe UI", 9),
                           anchor="w"
                           ).pack(fill="x", padx=22)

        tk.Label(dlg,
                 text=t("Перед переносом делается бэкап WTF — его можно "
                        "откатить в «Настройки → Авто-бэкап → Восстановить»."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left",
                 wraplength=440, anchor="w"
                 ).pack(fill="x", padx=18, pady=(8, 0))

        status_var = tk.StringVar()
        tk.Label(dlg, textvariable=status_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(fill="x", padx=18)

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(fill="x", padx=18, pady=(10, 16))
        apply_btn = tk.Button(btn_row, text=t("Применить"), bg=PRIMARY_BG,
                              fg=PRIMARY_FG, relief="flat", padx=16, pady=6)
        apply_btn.pack(side="left")
        tk.Button(btn_row, text=t("Закрыть"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=14, pady=6, command=dlg.destroy
                  ).pack(side="right")

        def finish(copied, errors):
            apply_btn.configure(state="normal")
            status_var.set("")
            if errors:
                messagebox.showwarning(
                    APP_TITLE,
                    t("Готово, но с ошибками ({e}). Скопировано файлов: {n}"
                      ).format(e=len(errors), n=copied), parent=dlg)
            else:
                messagebox.showinfo(
                    APP_TITLE,
                    t("Готово. Скопировано файлов: {n}").format(n=copied),
                    parent=dlg)

        def apply():
            # The client rewrites the whole WTF tree when it exits, so copying
            # underneath a running one just gets silently undone.
            if is_wow_running():
                messagebox.showwarning(
                    APP_TITLE,
                    t("Сначала закрой все окна WoW — клиент перезапишет WTF "
                      "при выходе."), parent=dlg)
                return
            sel = targets.curselection()
            try:
                src_idx = labels.index(src_var.get())
            except ValueError:
                src_idx = -1
            dst = [paths[i] for i in sel if i != src_idx]
            if src_idx < 0 or not dst:
                messagebox.showwarning(
                    APP_TITLE, t("Выбери источник и хотя бы одного получателя."),
                    parent=dlg)
                return
            groups = [k for k, v in group_vars.items() if v.get()]
            if not groups:
                messagebox.showwarning(APP_TITLE,
                                       t("Выбери, что переносить."), parent=dlg)
                return
            if not messagebox.askyesno(
                    APP_TITLE,
                    t("Перенести настройки «{src}» на выбранных персонажей "
                      "({n})?\nИх текущие настройки будут перезаписаны."
                      ).format(src=src_var.get(), n=len(dst)), parent=dlg):
                return

            apply_btn.configure(state="disabled")
            status_var.set(t("Переношу…"))
            src_path = paths[src_idx]

            def work():
                # interval 0 forces a snapshot even if one was just taken
                _backup_game_data(wow, _backup_dest_root(self.cfg, wow),
                                  max(1, int(self.cfg.get("backup_keep", 3) or 3)),
                                  0)
                copied, errors = copy_wtf_settings(src_path, dst, groups)
                self.root.after(0, lambda: finish(copied, errors))

            threading.Thread(target=work, daemon=True).start()

        apply_btn.configure(command=apply)
        self._fit_dialog(dlg, 480)

    def graphics_constructor(self, parent, on_close=None):
        """Build your own graphics presets: pick which client settings the
        preset changes and what it sets them to. Built-in presets are shown
        read-only — "Копия" makes an editable one out of any of them."""
        dlg = tk.Toplevel(parent)
        dlg.title(t("Конструктор графики"))
        dlg.configure(bg=BG)
        dlg.transient(parent)
        tk.Label(dlg, text=t("Конструктор графики"), bg=BG, fg=TEXT,
                 font=font(14, "bold")).pack(padx=20, pady=(16, 2), anchor="w")
        tk.Label(dlg, text=t("Пресет меняет только отмеченные настройки, "
                             "остальные останутся как в игре."),
                 bg=BG, fg=MUTED, font=font(9), anchor="w"
                 ).pack(fill="x", padx=20)

        wrap = tk.Frame(dlg, bg=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(10, 0))

        left = tk.Frame(wrap, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 14))
        listbox = tk.Listbox(left, width=30, height=16, bg=ENTRY_BG, fg=TEXT,
                             relief="flat", highlightthickness=1,
                             highlightbackground=BORDER, font=font(10),
                             selectbackground=SEL_BG, selectforeground=SEL_FG,
                             exportselection=False, activestyle="none")
        listbox.pack(fill="y", expand=True)
        lbtns = tk.Frame(left, bg=BG)
        lbtns.pack(fill="x", pady=(8, 0))

        right = tk.Frame(wrap, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        name_row = tk.Frame(right, bg=BG)
        name_row.pack(fill="x")
        tk.Label(name_row, text=t("Название"), bg=BG, fg=MUTED, font=font(9)
                 ).pack(side="left")
        name_var = tk.StringVar()
        name_entry = _make_entry(name_row, name_var)
        name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)

        rows_area = tk.Frame(right, bg=BG)
        rows_area.pack(fill="both", expand=True, pady=(10, 0))

        keys = []                      # listbox index -> preset key
        state = {"key": None, "rows": {}, "loading": False}

        def selected_key():
            sel = listbox.curselection()
            return keys[sel[0]] if sel else None

        def editable(key):
            return key is not None and key not in GRAPHICS_PRESETS

        def store():
            """Write the editor back into the preset (user presets only)."""
            key = state["key"]
            if state["loading"] or not editable(key):
                return
            presets = self.cfg.setdefault("graphics_presets", {})
            entry = presets.setdefault(key, {})
            entry["name"] = name_var.get().strip() or key
            cvars = {}
            mode_use, mode_var, res_use, res_var = state["screen"]
            if mode_use.get():
                chosen = next((k for k, lbl, _w, _m in SCREEN_MODES
                               if t(lbl) == mode_var.get()), "")
                cvars.update(screen_mode_cvars(chosen))
            if res_use.get() and res_var.get():
                cvars["gxResolution"] = res_var.get()
            for cvar, (use_var, val_var) in state["rows"].items():
                if use_var.get():
                    cvars[cvar] = gfx_value_str(val_var.get())
            entry["cvars"] = cvars

        def load(key):
            state["loading"] = True
            state["key"] = key
            values = preset_cvars(self.cfg, key) if key else {}
            mode_use, mode_var, res_use, res_var = state["screen"]
            mode_key = screen_mode_of(values)
            mode_use.set(bool(mode_key))
            mode_var.set(next((t(lbl) for k, lbl, _w, _m in SCREEN_MODES
                               if k == (mode_key or "full")), ""))
            res_use.set("gxResolution" in values)
            res_var.set(values.get("gxResolution", "")
                        or (available_resolutions() or [""])[0])
            name_var.set(preset_label(self.cfg, key) if key else "")
            can_edit = editable(key)
            name_entry.configure(state="normal" if can_edit else "disabled")
            for cvar, (use_var, val_var) in state["rows"].items():
                present = cvar in values
                use_var.set(present)
                default = next(d for c, _l, _k, _lo, _hi, _st, d
                               in GRAPHICS_SETTINGS if c == cvar)
                try:
                    val_var.set(float(values.get(cvar, default)))
                except (TypeError, ValueError):
                    val_var.set(float(default))
            for widgets in (state.get("widgets", [])
                            + state.get("screen_widgets", [])):
                for w in widgets:
                    try:
                        w.configure(state="normal" if can_edit else "disabled")
                    except tk.TclError:
                        pass
            state["loading"] = False
            refresh_values()

        def refresh_values():
            for cvar, label in state.get("value_labels", {}).items():
                _use, val_var = state["rows"][cvar]
                kind = next(k for c, _l, k, _lo, _hi, _st, _d
                            in GRAPHICS_SETTINGS if c == cvar)
                if kind == "toggle":
                    label.configure(text=t("вкл") if val_var.get() >= 0.5
                                    else t("выкл"))
                else:
                    label.configure(text=gfx_value_str(val_var.get()))

        # screen mode and resolution first — they matter most
        mode_use = tk.BooleanVar(value=False)
        mode_var = tk.StringVar()
        res_use = tk.BooleanVar(value=False)
        res_var = tk.StringVar()
        state["screen"] = (mode_use, mode_var, res_use, res_var)

        def screen_changed(*_a):
            store()
        for _v in (mode_use, mode_var, res_use, res_var):
            _v.trace_add("write", screen_changed)
        mode_labels = [t(lbl) for _k, lbl, _w, _m in SCREEN_MODES]
        screen_widgets = []
        for label, use_var, var, values in (
                (t("Режим окна"), mode_use, mode_var, mode_labels),
                (t("Разрешение"), res_use, res_var, available_resolutions())):
            row = tk.Frame(rows_area, bg=BG)
            row.pack(fill="x", pady=1)
            cb = tk.Checkbutton(row, variable=use_var, bg=BG, fg=TEXT,
                                activebackground=BG, selectcolor=ENTRY_BG,
                                highlightthickness=0, bd=0)
            cb.pack(side="left")
            tk.Label(row, text=label, bg=BG, fg=TEXT, font=font(9), width=28,
                     anchor="w").pack(side="left")
            box = ttk.Combobox(row, textvariable=var, values=values,
                               state="readonly", font=font(9), width=22)
            box.pack(side="right", padx=(0, 10))
            screen_widgets.append((cb, box))
        state["screen_widgets"] = screen_widgets

        # one row per setting
        state["widgets"], state["value_labels"] = [], {}
        for cvar, label, kind, lo, hi, step, default in GRAPHICS_SETTINGS:
            row = tk.Frame(rows_area, bg=BG)
            row.pack(fill="x", pady=1)
            use_var = tk.BooleanVar(value=False)
            val_var = tk.DoubleVar(value=float(default))
            state["rows"][cvar] = (use_var, val_var)

            def changed(*_a):
                store()
                refresh_values()

            use_var.trace_add("write", changed)
            val_var.trace_add("write", changed)
            cb = tk.Checkbutton(row, variable=use_var, bg=BG, fg=TEXT,
                                activebackground=BG, selectcolor=ENTRY_BG,
                                highlightthickness=0, bd=0)
            cb.pack(side="left")
            tk.Label(row, text=t(label), bg=BG, fg=TEXT, font=font(9),
                     width=28, anchor="w").pack(side="left")
            value_lbl = tk.Label(row, text="", bg=BG, fg=ACCENT, font=font(9),
                                 width=6, anchor="e")
            value_lbl.pack(side="right")
            state["value_labels"][cvar] = value_lbl
            if kind == "toggle":
                ctl = tk.Checkbutton(row, variable=val_var, onvalue=1.0,
                                     offvalue=0.0, bg=BG, activebackground=BG,
                                     selectcolor=ENTRY_BG, highlightthickness=0,
                                     bd=0)
                ctl.pack(side="right", padx=(0, 10))
            else:
                ctl = tk.Scale(row, from_=lo, to=hi, resolution=step,
                               orient="horizontal", variable=val_var,
                               showvalue=0, bg=BTN_HOVER, fg=TEXT,
                               troughcolor=ENTRY_BG, activebackground=ACCENT,
                               highlightthickness=0, bd=0, width=10,
                               sliderlength=16, sliderrelief="flat", length=200)
                ctl.pack(side="right", padx=(0, 10))
            state["widgets"].append((cb, ctl))

        def fill_list(select_key=None):
            store()
            listbox.delete(0, "end")
            del keys[:]
            for key, lbl in graphics_options(self.cfg):
                if not key:
                    continue
                keys.append(key)
                listbox.insert("end", lbl + ("" if editable(key)
                                             else "  " + t("(встроенный)")))
            if not keys:
                load(None)
                return
            idx = keys.index(select_key) if select_key in keys else 0
            listbox.selection_clear(0, "end")
            listbox.selection_set(idx)
            load(keys[idx])

        def on_select(_e=None):
            store()
            key = selected_key()
            if key and key != state["key"]:
                load(key)

        listbox.bind("<<ListboxSelect>>", on_select)

        def add_preset(copy_from=None):
            store()
            key = new_preset_key(self.cfg)
            base = preset_cvars(self.cfg, copy_from) if copy_from else {}
            name = (t("{name} — копия").format(
                name=preset_label(self.cfg, copy_from)) if copy_from
                else t("Мой пресет"))
            self.cfg.setdefault("graphics_presets", {})[key] = {
                "name": name, "cvars": base}
            fill_list(key)
            name_entry.focus_set()

        def delete_preset():
            key = selected_key()
            if not editable(key):
                messagebox.showinfo(
                    APP_TITLE, t("Встроенный пресет нельзя удалить — сделай "
                                 "копию."), parent=dlg)
                return
            if not messagebox.askyesno(
                    APP_TITLE, t("Удалить пресет «{name}»?").format(
                        name=preset_label(self.cfg, key)), parent=dlg):
                return
            state["key"] = None
            drop_preset(self.cfg, key)
            fill_list()

        tk.Button(lbtns, text=t("Новый"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=8, pady=3, command=lambda: add_preset()
                  ).pack(side="left")
        tk.Button(lbtns, text=t("Копия"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=8, pady=3,
                  command=lambda: add_preset(selected_key())
                  ).pack(side="left", padx=4)
        tk.Button(lbtns, text=t("Удалить"), bg=BTN_BG, fg=TEXT, relief="flat",
                  padx=8, pady=3, command=delete_preset).pack(side="left")

        def close():
            store()
            save_cfg(self.cfg)
            dlg.destroy()
            if on_close:
                on_close()

        FlatButton(dlg, t("Готово"), kind="primary", command=close
                   ).pack(fill="x", padx=20, pady=(12, 16))
        dlg.protocol("WM_DELETE_WINDOW", close)
        dlg.bind("<Escape>", lambda _e: close())
        fill_list()
        self._fit_dialog(dlg, 700)
        dlg.grab_set()

    # ── collecting data for the whole roster ────────────────────────────────

    def harvest_plan(self):
        """[(account entry, [character entries])] — what a run would visit."""
        return [(acc, [c for _i, c in chars])
                for _ai, acc, chars in roster_groups(self.cfg)
                if acc is not None]

    def harvest_dialog(self, parent):
        """Walk every account and character once, so gold / GS / lockouts are
        filled in for the whole roster. One client launch per account: the
        addon switches characters inside the client and closes the game when
        the account is done."""
        plan = self.harvest_plan()
        chars_total = sum(len(c) for _a, c in plan)
        dlg = tk.Toplevel(parent)
        dlg.title(t("Сбор данных"))
        dlg.configure(bg=BG)
        dlg.transient(parent)

        tk.Label(dlg, text=t("Сбор данных со всех персонажей"), bg=BG, fg=TEXT,
                 font=font(14, "bold")).pack(padx=20, pady=(16, 4), anchor="w")
        tk.Label(dlg, text=t("Менеджер сам зайдёт в каждый аккаунт и за "
                             "каждого персонажа, соберёт данные и закроет "
                             "игру. Клиент запускается один раз на аккаунт — "
                             "персонажи переключаются внутри него.\n"
                             "Пока идёт сбор, не трогай игру."),
                 bg=BG, fg=MUTED, font=font(9), justify="left", anchor="w",
                 wraplength=520).pack(fill="x", padx=20)

        if self.cfg.get("use_loader"):
            tk.Label(dlg, text=t("Запуск идёт через внешний лоадер: не трогай "
                                 "его окно, пока идёт сбор."),
                     bg=BG, fg=ACCENT, font=font(9), anchor="w",
                     wraplength=520, justify="left"
                     ).pack(fill="x", padx=20, pady=(8, 0))

        minutes = max(1, int((len(plan) * 60 + chars_total * 40) / 60))
        tk.Label(dlg, text=t("Аккаунтов: {a} · персонажей: {c} · примерно "
                             "{m} мин").format(a=len(plan), c=chars_total,
                                               m=minutes),
                 bg=BG, fg=ACCENT, font=font(10, "bold"), anchor="w"
                 ).pack(fill="x", padx=20, pady=(10, 0))

        status_var = tk.StringVar(value=t("Готов к запуску"))
        tk.Label(dlg, textvariable=status_var, bg=BG, fg=TEXT, font=font(10),
                 anchor="w").pack(fill="x", padx=20, pady=(10, 2))
        log = tk.Text(dlg, height=12, bg=ENTRY_BG, fg=TEXT, relief="flat",
                      highlightthickness=1, highlightbackground=BORDER,
                      font=font(9), wrap="word")
        log.pack(fill="both", expand=True, padx=20)

        row = tk.Frame(dlg, bg=BG)
        row.pack(fill="x", padx=20, pady=(12, 16))
        start_btn = FlatButton(row, t("Начать"), kind="primary")
        start_btn.pack(side="left")
        stop_btn = FlatButton(row, t("Остановить"))
        stop_btn.pack(side="left", padx=(8, 0))
        stop_btn.set_enabled(False)
        close_btn = FlatButton(row, t("Закрыть"), command=dlg.destroy)
        close_btn.pack(side="right")

        def say(line):
            log.insert("end", line + "\n")
            log.see("end")

        def finish():
            self._harvesting = False
            start_btn.set_enabled(True)
            stop_btn.set_enabled(False)
            close_btn.set_enabled(True)
            status_var.set(t("Готово"))
            self._refresh_ingame()

        def start():
            if is_wow_running():
                messagebox.showwarning(
                    APP_TITLE, t("Сначала закрой запущенный WoW."), parent=dlg)
                return
            if not plan:
                messagebox.showinfo(APP_TITLE, t("Нет аккаунтов для сбора."),
                                    parent=dlg)
                return
            if SECRETS_LOCKED:
                self._relock_prompt()
                return
            self._harvest_stop = False
            self._harvesting = True
            start_btn.set_enabled(False)
            stop_btn.set_enabled(True)
            close_btn.set_enabled(False)
            log.delete("1.0", "end")
            threading.Thread(
                target=self._harvest_worker,
                args=(plan, lambda *a: self.root.after(0, say, *a),
                      lambda *a: self.root.after(0, status_var.set, *a),
                      lambda: self.root.after(0, finish)),
                daemon=True).start()

        def stop():
            self._harvest_stop = True
            status_var.set(t("Останавливаю…"))

        start_btn.command = start
        stop_btn.command = stop
        dlg.protocol("WM_DELETE_WINDOW",
                     lambda: None if self._harvesting else dlg.destroy())
        self._fit_dialog(dlg, 580)
        dlg.grab_set()

    def _harvest_log(self, line):
        """A run leaves a trace next to the config — when something goes wrong
        in the game there is otherwise nothing to look at."""
        try:
            with open(os.path.join(_config_dir(), "harvest.log"), "a",
                      encoding="utf-8") as fh:
                fh.write("%s  %s\n" % (time.strftime("%H:%M:%S"), line))
        except OSError:
            pass

    def _client_running(self):
        return is_wow_running()

    def _wait_for_client_start(self, deadline):
        """Wait until a client process shows up. With an external loader that
        can take a while — the loader has its own window to get through."""
        while time.time() < deadline and not self._harvest_stop:
            if self._client_running():
                return True
            time.sleep(1)
        return False

    def _wait_for_client_exit(self, deadline):
        """Wait until no game client is running any more. Watching only the
        process we started isn't enough: with a loader the client isn't our
        child at all, and a client can also hand over to another process."""
        gone_for = 0
        while time.time() < deadline and not self._harvest_stop:
            if not self._client_running():
                gone_for += 1
                if gone_for >= 3:
                    return True
            else:
                gone_for = 0
            time.sleep(1)
        return False

    def _harvest_worker(self, plan, say, status, done):
        """Runs off the UI thread: one client launch per account."""
        wow = self.cfg.get("wow_path", "")
        collected = 0
        self._harvest_log("=== run start: %d accounts" % len(plan))
        try:
            for n, (acc, chars) in enumerate(plan, 1):
                if self._harvest_stop:
                    say(t("Остановлено."))
                    break
                names = [c.get("name", "") for c in chars if c.get("name")]
                login = acc.get("account", "")
                status(t("Аккаунт {n} из {total}: {login}").format(
                    n=n, total=len(plan), login=login))
                say(t("{login}: персонажей {c}").format(login=login,
                                                        c=len(names)))
                target = dict(chars[0]) if chars else acc
                before = charlist_signature(wow)
                self._harvest_log("%s: %d characters -> %s"
                                  % (login, len(names), names))
                try:
                    proc = launch_wow(self.cfg, target, harvest_chars=names)
                except Exception as e:                  # noqa: BLE001
                    say("  " + str(e))
                    self._harvest_log("  launch failed: %s" % e)
                    continue
                deadline = time.time() + (120 + 90 * len(names) if names
                                          else 120)
                if not self._wait_for_client_start(min(deadline,
                                                       time.time() + 120)):
                    say(t("  Клиент не запустился."))
                    self._harvest_log("  client never appeared")
                    if not self._harvest_stop:
                        continue
                    break
                if names:
                    finished = self._wait_for_client_exit(deadline)
                else:
                    # An account with no characters only needs the roster file.
                    finished = False
                    while time.time() < deadline and not self._harvest_stop:
                        if charlist_signature(wow) != before:
                            say(t("  Список персонажей получен."))
                            finished = True
                            break
                        if not self._client_running():
                            break
                        time.sleep(1)
                if not finished or self._harvest_stop:
                    if not self._harvest_stop and names:
                        say(t("  Не уложился во время — закрываю клиент."))
                    self._harvest_log("  timeout/stop, closing the client")
                    terminate_clients()
                    try:
                        if proc is not None:
                            proc.terminate()
                    except OSError:
                        pass
                    for _ in range(30):
                        if not self._client_running():
                            break
                        time.sleep(0.5)
                time.sleep(2)               # let the client flush its files
                self._harvest_log("  account done")
                self.root.after(0, self._refresh_ingame)
                if self.cfg.get("auto_import_chars", True):
                    lists = read_char_lists(wow)
                    self.root.after(0, lambda l=lists: self._import_char_lists(l))
                collected += len(names)
                say(t("  Готово: {c}").format(c=len(names) or "-"))
        finally:
            # Only clear harvest mode once no client is left that could still
            # be reading the addon config.
            for _ in range(30):
                if not self._client_running():
                    break
                time.sleep(1)
            try:
                deploy_addon(wow, bool(self.cfg.get("hover_card", True)
                                       or self.cfg.get("overlay", False)),
                             show_minimap=bool(self.cfg.get("overlay", False)),
                             characters=self.cfg.get("characters", []),
                             hover_card=bool(self.cfg.get("hover_card", True)),
                             card_fields=self.cfg.get("card_fields"),
                             card_labels=self.cfg.get("card_labels"))
            except Exception:
                pass
            say(t("Собрано персонажей: {c}").format(c=collected))
            self._harvest_log("=== run end: %d characters" % collected)
            done()

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
                 font=("Segoe UI", 9), anchor="w"
                 ).pack(fill="x", padx=20, pady=(16, 0))
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
                 fg=MUTED, font=("Segoe UI", 9), anchor="w"
                 ).pack(fill="x", padx=20)
        realms_text = tk.Text(body, height=6, bg=ENTRY_BG, fg=TEXT,
                              relief="flat", highlightthickness=1,
                              font=("Segoe UI", 10), wrap="none")
        realms_text.configure(highlightbackground=BORDER,
                              highlightcolor=ACCENT, insertbackground=TEXT)
        realms_text.insert("1.0", "\n".join(self.cfg.get("realms", [])))
        realms_text.pack(fill="x", padx=20, pady=(2, 12))

        # ── Realmlists ───────────────────────────────────────────────────────
        tk.Label(body, text=t("Список realmlist-серверов (по строке)"), bg=BG,
                 fg=MUTED, font=("Segoe UI", 9), anchor="w"
                 ).pack(fill="x", padx=20)
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

        # ── How secrets are stored ───────────────────────────────────────────
        mode_labels = {"dpapi":  t("Ключ Windows (этот ПК)"),
                       "master": t("Мастер-пароль"),
                       "plain":  t("Без шифрования")}
        mode_rev = {v: k for k, v in mode_labels.items()}
        secret_row = tk.Frame(body, bg=BG)
        secret_row.pack(fill="x", padx=18, pady=(10, 0))
        tk.Label(secret_row, text=t("Хранение паролей:"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        secret_var = tk.StringVar(
            value=mode_labels[secret_mode(self.cfg)])
        secret_cb = ttk.Combobox(secret_row, textvariable=secret_var,
                                 values=list(mode_labels.values()),
                                 state="readonly", width=24,
                                 font=("Segoe UI", 9))
        secret_cb.pack(side="left", padx=(8, 8))
        master_btn = tk.Button(secret_row, bg=BTN_BG, fg=TEXT, relief="flat",
                               padx=10, pady=2)
        master_btn.pack(side="left")

        # Pending master key, applied only if the user actually saves.
        new_master = {"key": None, "salt": None}

        def set_master():
            pw = self._ask_password(
                t("Новый мастер-пароль"),
                t("Мастер-пароль делает конфиг переносимым: его можно взять "
                  "на другой ПК, но без пароля он бесполезен."),
                confirm_prompt=t("Повтори пароль"))
            if not pw:
                return
            salt = os.urandom(16)
            new_master["salt"] = salt
            new_master["key"] = derive_master_key(pw, salt)
            messagebox.showinfo(
                APP_TITLE,
                t("Мастер-пароль задан. Не потеряй его — восстановить нечем."),
                parent=dlg)
            refresh_master_btn()

        def refresh_master_btn(_e=None):
            is_master = mode_rev.get(secret_var.get()) == "master"
            has_key = bool(self.cfg.get("master_check")) or new_master["key"]
            master_btn.configure(
                text=(t("Сменить мастер-пароль…") if has_key
                      else t("Задать мастер-пароль…")),
                command=set_master,
                state=("normal" if is_master else "disabled"))

        secret_cb.bind("<<ComboboxSelected>>", refresh_master_btn)
        refresh_master_btn()
        tk.Label(body,
                 text=t("Мастер-пароль делает конфиг переносимым: его можно "
                        "взять на другой ПК, но без пароля он бесполезен."),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left",
                 wraplength=520, anchor="w"
                 ).pack(fill="x", padx=18, pady=(2, 0))

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

        tools_row = tk.Frame(body, bg=BG)
        tools_row.pack(fill="x", padx=18, pady=(8, 0))
        tk.Button(tools_row, text=t("Ростер для форума…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.roster_dialog(dlg)
                  ).pack(side="left")
        tk.Button(tools_row, text=t("Перенос настроек…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.wtf_transfer_dialog(dlg)
                  ).pack(side="left", padx=(8, 0))

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

        gbtns = tk.Frame(body, bg=BG)
        gbtns.pack(anchor="w", padx=22, pady=(6, 0))
        tk.Button(gbtns, text=t("Конструктор графики…"), bg=BTN_BG, fg=TEXT,
                  relief="flat", padx=10, pady=2,
                  command=lambda: self.graphics_constructor(dlg)
                  ).pack(side="left")
        tk.Button(gbtns, text=t("Собрать данные со всех персонажей…"),
                  bg=BTN_BG, fg=TEXT, relief="flat", padx=10, pady=2,
                  command=lambda: self.harvest_dialog(dlg)
                  ).pack(side="left", padx=(8, 0))

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

        # ── In the game ─────────────────────────────────────────────────────
        tk.Label(body, text=t("В игре"), bg=BG, fg=MUTED, font=("Segoe UI", 9),
                 anchor="w").pack(fill="x", padx=20, pady=(10, 0))
        game_vars = {}
        for key, label, default in (
                ("auto_import_chars",
                 "Собирать персонажей при входе в аккаунт", True),
                ("laa_patch", "Патч «4 ГБ памяти» для Wow.exe — меньше вылетов "
                              "в ЦЛК и на БГ", True),
                ("anti_afk", "Анти-АФК: персонаж не уходит в «Отошёл» и не "
                             "выходит из игры через 30 минут", False),
                ("sync_friends", "Общий список друзей и игнора для всех "
                                 "персонажей", True),
                ("lfg", "Поиск группы из чата (/wm lfg)", True)):
            var = tk.BooleanVar(value=bool(self.cfg.get(key, default)))
            game_vars[key] = var
            tk.Checkbutton(body, text=t(label), variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=TEXT,
                           selectcolor=ENTRY_BG, font=("Segoe UI", 9),
                           anchor="w", justify="left", wraplength=520
                           ).pack(fill="x", padx=18, pady=(2, 0))

        # ── Config management (moved to the bottom) ──────────────────────────
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(12, 6))
        tk.Label(body, text=t("Конфиг"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=20)
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

            # Secret storage. Switching modes re-encrypts on the next save,
            # because the in-memory config already holds plaintext.
            chosen = mode_rev.get(secret_var.get(), "dpapi")
            if chosen != secret_mode(self.cfg) and SECRETS_LOCKED:
                # Re-encrypting needs the plaintext, and we never got it.
                messagebox.showwarning(
                    APP_TITLE,
                    t("Сейчас пароли заблокированы — сначала введи "
                      "мастер-пароль, иначе их нечем перешифровать."),
                    parent=dlg)
                return
            if chosen == "master":
                if new_master["key"] is not None:
                    set_master_key(new_master["key"])
                    self.cfg["master_salt"] = base64.b64encode(
                        new_master["salt"]).decode("ascii")
                    self.cfg["master_check"] = master_verifier(
                        new_master["key"])
                elif not (have_master_key() and self.cfg.get("master_check")):
                    messagebox.showwarning(
                        APP_TITLE,
                        t("Сначала задай мастер-пароль кнопкой справа от "
                          "списка."), parent=dlg)
                    return
            else:
                self.cfg["master_salt"] = ""
                self.cfg["master_check"] = ""
                set_master_key(None)
            self.cfg["secret_mode"]     = chosen
            self.cfg["backup_wtf"]      = bool(backup_var.get())
            self.cfg["hover_card"]      = bool(hover_var.get())
            for key, var in game_vars.items():
                self.cfg[key] = bool(var.get())
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
_TOKEN_FILE = "ipc.token"


def _ipc_token():
    """Shared secret every IPC message must carry. Anything on this machine can
    connect to a localhost port, and a LAUNCH message starts the game with the
    user's stored credentials — so a caller has to prove it can read our config
    directory before we act on it."""
    path = os.path.join(_config_dir(), _TOKEN_FILE)
    try:
        with open(path, "rb") as fh:
            tok = fh.read().strip()
        if len(tok) >= 16:
            return tok
    except OSError:
        pass
    tok = base64.urlsafe_b64encode(os.urandom(24)).strip()
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(tok)
        return tok
    except OSError:
        # Can't persist one — both copies still need to agree on something, so
        # derive it from what they do share. Weaker, but it keeps the "second
        # copy brings the first one forward" behaviour working.
        seed = (os.path.abspath(_config_dir()) + "|"
                + os.environ.get("USERNAME", "")).encode("utf-8", "replace")
        return base64.urlsafe_b64encode(hashlib.sha256(seed).digest()[:24])


IPC_NONE, IPC_OK, IPC_STALE = 0, 1, 2
_MSG_ACK = b"OK"


def _send_to_existing(msg):
    """Hand `msg` to a running instance.

    IPC_NONE  — nobody is listening; this copy should start normally.
    IPC_OK    — a current instance took the request.
    IPC_STALE — something holds the port but never confirmed: in practice a
                pre-1.5 manager still sitting in the tray, which neither knows
                the token nor answers. Starting silently would look like the
                program doesn't open at all."""
    msg = _ipc_token() + b"|" + msg
    try:
        c = socket.create_connection(("127.0.0.1", _SINGLE_INSTANCE_PORT),
                                     timeout=0.5)
    except OSError:
        return IPC_NONE
    try:
        c.settimeout(1.5)
        c.sendall(msg)
        c.shutdown(socket.SHUT_WR)          # EOF for the reader, keep our end
        reply = c.recv(16)
        return IPC_OK if reply.startswith(_MSG_ACK) else IPC_STALE
    except OSError:
        return IPC_STALE
    finally:
        c.close()


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

    token = _ipc_token()

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    conn.settimeout(1.0)
                    chunks = []
                    while len(b"".join(chunks)) < 4096:
                        part = conn.recv(1024)
                        if not part:
                            break
                        chunks.append(part)
                    data = b"".join(chunks)
                    prefix = token + b"|"
                    if not data.startswith(prefix):
                        continue
                    try:
                        conn.sendall(_MSG_ACK)
                    except OSError:
                        pass
                data = data[len(prefix):]
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
    state = _send_to_existing(msg)
    if state == IPC_OK:
        sys.exit(0)
    if state == IPC_STALE:
        _cfg_lang = "ru"
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as _fh:
                _cfg_lang = json.load(_fh).get("lang", "ru")
        except Exception:
            pass
        set_lang(_cfg_lang)
        _r = tk.Tk()
        _r.withdraw()
        messagebox.showwarning(
            APP_TITLE,
            t("Уже запущена старая версия менеджера (значок в трее).\n"
              "Закрой её через меню трея и запусти программу снова."))
        _r.destroy()
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
