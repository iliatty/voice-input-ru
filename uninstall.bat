@echo off
chcp 65001 >nul
setlocal
echo.
echo Удаление «Голосового ввода»
echo ============================
echo.
echo Будут удалены:
echo   - автозапуск программы;
echo   - настройки, журнал и словарь самообучения;
echo   - скачанные модели в LocalAppData.
echo.
echo Папку самой программы нужно удалить вручную после этого.
echo Если программа сейчас открыта, сначала выберите «Выход» в её трее.
echo.
pause

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v VoiceInputRU /f >nul 2>&1
rmdir /s /q "%APPDATA%\VoiceInputRU" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\VoiceInputRU" >nul 2>&1

echo.
echo Готово: настройки, журнал, словарь и автозапуск удалены.
echo Удалите папку:
echo   %~dp0
echo.
pause
