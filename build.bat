@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo   Менеджер персонажей WOW
echo   Сборка установщика
echo =========================================
echo.

REM ── 1. Зависимости ────────────────────────────────────────────────────
echo [1/3] Проверяю Python-зависимости...
python -m pip install --quiet nuitka zstandard ordered-set pefile pystray pillow
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка: pip не найден. Установи Python 3.10+ с python.org
    pause & exit /b 1
)

REM ── 2. Папочная сборка Nuitka (без onefile — меньше детектов AV) ─────
echo [2/3] Компилирую launcher.py (standalone)...
echo (первый запуск может качать MinGW/clang — займёт 5-10 минут)
python -m nuitka ^
    --standalone ^
    --enable-plugin=tk-inter ^
    --windows-disable-console ^
    --windows-icon-from-ico=wow.ico ^
    --include-data-file=AwesomeWotlkLib.dll=AwesomeWotlkLib.dll ^
    --include-data-file=wow.ico=wow.ico ^
    --include-package=pystray ^
    --include-package=PIL ^
    --product-name="Менеджер персонажей WOW" ^
    --product-version=1.4.0.0 ^
    --file-version=1.4.0.0 ^
    --company-name=Zaifat ^
    --output-filename=Manager_WOW.exe ^
    --output-dir=dist ^
    --lto=yes ^
    --assume-yes-for-downloads ^
    launcher.py

if not exist "dist\launcher.dist\Manager_WOW.exe" (
    echo Сборка не удалась. Проверь ошибки выше.
    pause & exit /b 1
)

REM ── 3. Inno Setup → установщик ────────────────────────────────────────
echo.
echo [3/3] Упаковываю в установщик через Inno Setup...

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"  set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"        set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo.
    echo ВНИМАНИЕ: Inno Setup не найден.
    echo Установи его: winget install JRSoftware.InnoSetup
    echo Или скачай: https://jrsoftware.org/isdl.php
    pause & exit /b 1
)

"%ISCC%" /Q installer.iss
if %ERRORLEVEL% NEQ 0 (
    echo Inno Setup завершился с ошибкой.
    pause & exit /b 1
)

echo.
echo =========================================
echo  ГОТОВО!
echo  Установщик: dist\installer\Manager_WOW.exe
echo =========================================
pause
