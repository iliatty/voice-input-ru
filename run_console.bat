@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=%~dp0vendor
set PYTHONIOENCODING=utf-8
python "%~dp0run.pyw"
pause
