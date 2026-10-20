@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%CD%\vendor"
set "PYTHONIOENCODING=utf-8"
python -m unittest discover -s tests -v
pause
