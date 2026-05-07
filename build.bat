@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo   Менеджер персонажей WOW (by Zaifat)
echo   v1.0 — сборка через Nuitka
echo =========================================
echo.

echo [1/2] Проверяю зависимости...
python -m pip install --quiet nuitka zstandard ordered-set pefile
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка: pip не найден. Установи Python 3.10+ с python.org
    pause & exit /b 1
)

echo [2/2] Компилирую launcher.py в нативный exe...
echo (первый запуск может качать MinGW/clang — займет 5-10 минут)
python -m nuitka ^
    --onefile ^
    --standalone ^
    --enable-plugin=tk-inter ^
    --windows-disable-console ^
    --windows-icon-from-ico=wow.ico ^
    --include-data-file=AwesomeWotlkLib.dll=AwesomeWotlkLib.dll ^
    --product-name="Менеджер персонажей WOW" ^
    --product-version=1.0.0.0 ^
    --file-version=1.0.0.0 ^
    --company-name=Zaifat ^
    --output-filename=АвтологинWOW.exe ^
    --output-dir=dist ^
    --lto=yes ^
    --remove-output ^
    --assume-yes-for-downloads ^
    launcher.py

echo.
if exist "dist\АвтологинWOW.exe" (
    echo =========================================
    echo  ГОТОВО!
    echo  Файл: dist\АвтологинWOW.exe
    echo =========================================
) else (
    echo Что-то пошло не так — проверь ошибки выше.
)
pause
