@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "vendor\vosk" goto :no_vendor

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0run.pyw"
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0run.pyw"
    exit /b 0
)

echo Не найден Python. Установите Python 3.10+ или запустите готовый VoiceInputRU.exe.
pause
exit /b 1

:no_vendor
echo Не найдены зависимости в папке vendor.
echo Запустите install.bat (нужен Python 3.10+) или используйте VoiceInputRU.exe.
pause
exit /b 1
