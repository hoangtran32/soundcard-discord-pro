import os
import sys

# Force UTF-8 stdout to avoid cp1252 UnicodeEncodeError on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import time
import socket
import threading
import subprocess
import webbrowser
import uvicorn

def is_port_in_use(port: int = 8765) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

def find_browser_app_executable():
    """Look for Edge or Chrome for dedicated native app window mode."""
    candidates = [
        # Microsoft Edge (standard on all Windows 10/11)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        # Google Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        # Brave
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def start_server():
    from server import app
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

def main():
    print("=" * 60)
    print("      >>> SOUNDCARD DISCORD PRO - DANG KHOI DONG <<<      ")
    print("=" * 60)

    url = "http://127.0.0.1:8765"

    if is_port_in_use(8765):
        print("[1/2] May chu am thanh da san sang tren cong 8765.")
    else:
        print("[1/2] Dang khoi chay may chu am thanh (Port 8765)...")
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        time.sleep(1.2)

    print(f"[2/2] Dang mo giao dien SoundCard Discord tai: {url}")

    browser_exe = find_browser_app_executable()
    if browser_exe:
        try:
            # Launch in standalone App Mode with fixed window dimensions
            app_args = [
                browser_exe,
                f"--app={url}",
                "--window-size=1280,820",
                "--app-id=SoundCardDiscord",
                f"--user-data-dir={os.path.abspath('data/browser_profile')}"
            ]
            process = subprocess.Popen(app_args)
            process.wait()
            return
        except Exception as e:
            print(f"App mode notice: {e}, dang mo bang trinh duyet mac dinh...")

    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDang tat SoundCard Discord...")

if __name__ == "__main__":
    main()
