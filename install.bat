@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Не найден Python 3.10+. Установите его с python.org и повторите запуск.
    pause
    exit /b 1
)

echo Устанавливаю зависимости в папку vendor...
python -m pip install --disable-pip-version-check --target vendor --upgrade -r requirements.txt
if errorlevel 1 (
    echo.
    echo Не удалось установить зависимости.
    pause
    exit /b 1
)

echo Готово. Теперь можно запускать run.bat
pause
