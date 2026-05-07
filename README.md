# Менеджер персонажей WOW 3.3.5a

<img width="883" height="593" alt="image" src="https://github.com/user-attachments/assets/6537801f-3c4f-4e01-a2de-9345f5ed5794" />

Лаунчер для World of Warcraft 3.3.5a (WotLK) с автологином.
Один клик по карточке персонажа — клиент сам вводит логин, пароль, выбирает реалм, заходит за нужного персонажа и (если подключено) подтверждает 2FA-код.

## Возможности

- **Один exe** — все зависимости и патч `AwesomeWotlkLib.dll` зашиты внутрь
- **2FA TOTP** — Google Authenticator / 2FAS Auth / Yandex.Ключ (RFC 6238). Код генерируется на лету и автоматически отправляется в окно подтверждения
- **Несколько аккаунтов** — каждый персонаж со своим логином/паролем/реалмом/realmlist
- **Подсветка по классам** в таблице, поиск, поле **ГС**
- **Бэкап/перенос конфига** — кнопки «Загрузить» / «Скачать» / «Очистить» в настройках
- Имя персонажа поддерживает **кириллицу** (исправлен баг с шагом массива в оригинальном AwesomeWotlk — `CharVectorEntry = 0x198` байт)

## Использование

1. Скачать `Manager_WOW.exe` из [Releases](../../releases) — это всё что нужно
2. Запустить → «Настройки» → указать путь к папке с `Wow.exe`
3. «Добавить» → заполнить ник, логин, пароль, класс, реалм, realmlist, при необходимости — секрет 2FA
4. Двойной клик по карточке персонажа → автозаход

Конфиг хранится в `%LOCALAPPDATA%\АвтологинWOW\characters.json`.

<img width="951" height="792" alt="image" src="https://github.com/user-attachments/assets/e05c0c7f-ae36-47af-9896-9584551c1c76" />

## Поддерживаемые серверы

Из коробки настроен на WoWCircle (`logon.wowcircle.com`). Список реалмов и realmlist-серверов редактируется в Настройках.

Технически работает с любым 3.3.5a-сервером, где клиент тот же `Wow.exe build 12340` и серверная сторона принимает стандартные команды:
- `-login` / `-password` — логин
- `-realmlist` / `-realmname` — выбор реалма
- `-character` — выбор персонажа

2FA должна реализовывать `TokenEnterDialog` GlueXML или вызов Lua `AcceptToken_AccountLogin`.

## Сборка из исходников

Нужен Python 3.10+ и Visual Studio 2022 с Desktop development with C++ (для clang-cl).

```bat
build.bat
```

Это поставит зависимости (Nuitka, zstandard, pefile) и скомпилирует `launcher.py` в нативный exe в папку `dist\АвтологинWOW.exe`. Первая сборка может занять 5-10 минут (Nuitka подкачает MinGW/clang при необходимости).

DLL `AwesomeWotlkLib.dll` уже собран и лежит в репозитории. Если хочешь пересобрать его сам — открой `awesome_wotlk_src/build_x86/Project.sln` в Visual Studio 2022.

## Благодарности

- [FrostAtom/awesome_wotlk](https://github.com/FrostAtom/awesome_wotlk) — оригинальный AwesomeWotlk-патч, на котором основан DLL

## Связь

Telegram: [@Zaifat](https://t.me/Zaifat)

## Лицензия

MIT
