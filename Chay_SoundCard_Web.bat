@echo off
setlocal
cd /d "%~dp0"
py -u share_web.py
if errorlevel 1 pause
