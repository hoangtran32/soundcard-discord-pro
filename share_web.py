"""Run SoundCard and a temporary HTTPS link from the same machine."""

import argparse
import asyncio
from contextlib import suppress
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import threading

import uvicorn

from core.pages_publisher import REPO_NAME, TUNNEL_URL, publish_when_ready


ROOT = Path(__file__).resolve().parent
ADDRESS = ("127.0.0.1", 8765)
PASSWORD_FILE = ROOT / "data" / "share-password.txt"
GUEST_KEY_FILE = ROOT / "data" / "guest-link-key.txt"
GUEST_LINK_FILE = ROOT / "data" / "link-moi.txt"
STOP_FILE = ROOT / "data" / "share.stop"
PAGES_FILE = ROOT / "data" / "pages-repo.txt"

def read_or_create_secret(path):
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(secrets.token_urlsafe(24) + "\n")
    except FileExistsError:
        pass
    return path.read_text(encoding="utf-8").strip()


def write_guest_link(url, guest_key):
    GUEST_LINK_FILE.write_text(f"{url}#invite={guest_key}\n", encoding="utf-8")
    print(f"Guest link file: {GUEST_LINK_FILE}", flush=True)


def cloudflared_path():
    installed = shutil.which("cloudflared")
    if installed:
        return installed
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        local = Path(local_app_data) / "SoundCardDiscord" / "cloudflared.exe"
        if local.is_file():
            return str(local)
    raise SystemExit("Install cloudflared and add it to PATH.")


async def wait_for_stop():
    while not STOP_FILE.exists():
        await asyncio.sleep(0.5)


async def watch_tunnel(stderr, repo, guest_key, cancelled):
    publication = None
    found_tunnel = False
    try:
        while line := await stderr.readline():
            message = line.decode("utf-8", errors="replace")
            print(message, file=sys.stderr, end="", flush=True)
            if found_tunnel:
                continue
            match = TUNNEL_URL.search(message)
            if match:
                found_tunnel = True
                if repo:
                    publication = asyncio.create_task(update_pages(repo, match[0], cancelled))
                else:
                    write_guest_link(f"{match[0]}/join", guest_key)
    finally:
        if publication is not None:
            await publication


async def update_pages(repo, live_url, cancelled):
    try:
        published = await asyncio.to_thread(publish_when_ready, repo, live_url, cancelled)
        if published:
            owner, name = repo.split("/", 1)
            print(f"GitHub Pages: https://{owner.lower()}.github.io/{name}/", flush=True)
    except Exception as error:
        print(f"Could not update GitHub Pages ({type(error).__name__}). Use the tunnel URL shown above.", flush=True)


async def serve(listener, cloudflared, repo, guest_key):
    server = uvicorn.Server(
        uvicorn.Config("server:app", access_log=False, timeout_graceful_shutdown=5)
    )
    web = asyncio.create_task(server.serve(sockets=[listener]))
    stop = asyncio.create_task(wait_for_stop())
    tunnel = None
    tunnel_exit = None
    tunnel_log = None
    cancelled = threading.Event()
    exit_code = 0
    try:
        while not server.started:
            if web.done():
                await web
                raise SystemExit("SoundCard failed to start.")
            await asyncio.sleep(0.1)
        tunnel = await asyncio.create_subprocess_exec(
            cloudflared, "tunnel", "--no-autoupdate", "--url",
            f"http://{ADDRESS[0]}:{ADDRESS[1]}",
            stderr=asyncio.subprocess.PIPE,
        )
        tunnel_log = asyncio.create_task(watch_tunnel(tunnel.stderr, repo, guest_key, cancelled))
        tunnel_exit = asyncio.create_task(tunnel.wait())
        finished, _ = await asyncio.wait([web, tunnel_exit, stop], return_when=asyncio.FIRST_COMPLETED)
        if tunnel_exit in finished:
            exit_code = tunnel_exit.result()
    finally:
        cancelled.set()
        stop.cancel()
        if tunnel and tunnel.returncode is None:
            with suppress(ProcessLookupError):
                tunnel.terminate()
        if tunnel_exit:
            await tunnel_exit
        if tunnel_log:
            await tunnel_log
        server.should_exit = True
        await web
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true", help="Stop the current sharing session.")
    args = parser.parse_args()
    os.chdir(ROOT)
    PASSWORD_FILE.parent.mkdir(exist_ok=True)
    if args.stop:
        STOP_FILE.touch()
        return 0
    cloudflared = cloudflared_path()
    with socket.socket() as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(ADDRESS)
        except OSError as error:
            raise SystemExit("Close the running SoundCard instance before sharing the web app.") from error
        STOP_FILE.unlink(missing_ok=True)
        os.environ["SOUNDCARD_SHARE_PASSWORD"] = read_or_create_secret(PASSWORD_FILE)
        guest_key = read_or_create_secret(GUEST_KEY_FILE)
        os.environ["SOUNDCARD_GUEST_KEY"] = guest_key
        print(f"Username: music | Password file: {PASSWORD_FILE}", flush=True)
        repo = PAGES_FILE.read_text(encoding="utf-8").strip() if PAGES_FILE.is_file() else ""
        if repo and not REPO_NAME.fullmatch(repo):
            raise SystemExit("Invalid GitHub repository in data/pages-repo.txt.")
        if repo:
            owner, name = repo.split("/", 1)
            write_guest_link(f"https://{owner.lower()}.github.io/{name}/", guest_key)
        return asyncio.run(serve(listener, cloudflared, repo, guest_key))


if __name__ == "__main__":
    raise SystemExit(main())
