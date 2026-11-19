@echo off
setlocal EnableExtensions
title SoundCard Discord Pro - Launcher
color 0b

echo ================================================================
echo          SOUNDCARD DISCORD PRO - LAUNCHER
echo ================================================================
echo.

set PYTHONIOENCODING=utf-8
set PY_EXE=

:: 1. Check py launcher
py -3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PY_EXE=py -3
    goto FOUND_PYTHON
)

:: 2. Check direct Python 3.12 path
if exist "C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe" (
    set PY_EXE="C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe"
    goto FOUND_PYTHON
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PY_EXE="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto FOUND_PYTHON
)

:: 3. Check any python in AppData
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set PY_EXE="%%D\python.exe"
        goto FOUND_PYTHON
    )
)

:: 4. Check Program Files
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set PY_EXE="%%D\python.exe"
        goto FOUND_PYTHON
    )
)

echo [ERROR] Khong tim thay Python! Vui long cai dat Python tu https://python.org
echo.
pause
exit /b 1

:FOUND_PYTHON
echo [*] Python phat hien: %PY_EXE%
echo [*] Dang khoi chay SoundCard Discord...
echo.

cd /d "%~dp0"
%PY_EXE% main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [*] Dang kiem tra va cai dat thu vien...
    %PY_EXE% -m pip install -r requirements.txt
    echo [*] Thu khoi dong lai...
    %PY_EXE% main.py
)

pause
