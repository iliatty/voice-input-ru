@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\vendor"

where python >nul 2>nul
if errorlevel 1 (
    echo Не найден Python 3.10+.
    pause
    exit /b 1
)

if not exist ".buildtools\PyInstaller" (
    echo Устанавливаю PyInstaller...
    python -m pip install --disable-pip-version-check --target .buildtools --upgrade pyinstaller
    if errorlevel 1 (
        echo Не удалось установить PyInstaller.
        pause
        exit /b 1
    )
)

if not exist "models\vosk-model-small-ru-0.22\am" (
    echo Модель не найдена, скачиваю...
    python tools\download_model.py
    if errorlevel 1 (
        echo Не удалось скачать модель.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\vendor;%CD%\.buildtools"
python -m PyInstaller --noconfirm --clean --windowed --name VoiceInputRU ^
    --icon assets\app.ico ^
    --add-data "assets;assets" ^
    --add-data "vendor\vosk;vosk" ^
    --paths vendor ^
    --hidden-import vosk ^
    --hidden-import vosk.vosk_cffi ^
    --hidden-import win32gui ^
    --hidden-import win32con ^
    --hidden-import win32api ^
    --hidden-import win32process ^
    --hidden-import win32clipboard ^
    --hidden-import pywintypes ^
    --hidden-import pythoncom ^
    --hidden-import pystray._win32 ^
    --hidden-import PIL.PngImagePlugin ^
    --exclude-module pandas ^
    --exclude-module matplotlib ^
    --exclude-module scipy ^
    --exclude-module IPython ^
    --exclude-module pytest ^
    --exclude-module notebook ^
    run.pyw
if errorlevel 1 (
    echo.
    echo Сборка не удалась.
    pause
    exit /b 1
)

if not exist "dist\VoiceInputRU\models" mkdir "dist\VoiceInputRU\models"
robocopy "models\vosk-model-small-ru-0.22" "dist\VoiceInputRU\models\vosk-model-small-ru-0.22" /E /NFL /NDL /NJH /NJS /NP >nul
robocopy "docs" "dist\VoiceInputRU\docs" /E /NFL /NDL /NJH /NJS /NP >nul
copy /Y "README.md" "dist\VoiceInputRU\README.md" >nul
copy /Y "uninstall.bat" "dist\VoiceInputRU\uninstall.bat" >nul

echo.
echo Готово: dist\VoiceInputRU\VoiceInputRU.exe
pause
