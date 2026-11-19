@echo off
setlocal EnableExtensions
title Tao Shortcut Desktop - SoundCard Discord

echo [*] Dang tao bieu tuong Shortcut tren Desktop...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SoundCard Discord.lnk'); $sc.TargetPath = '%~dp0Chay_SoundCard_Discord.bat'; $sc.WorkingDirectory = '%~dp0'; $sc.IconLocation = '%~dp0static\icons\default_cover.png'; $sc.Description = 'SoundCard Discord Pro'; $sc.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [OK] Da tao thanh cong Shortcut "SoundCard Discord" tren Desktop!
) else (
    echo [!] Khong the tao shortcut, vui long chay truc tiep file Chay_SoundCard_Discord.bat
)

echo.
pause
