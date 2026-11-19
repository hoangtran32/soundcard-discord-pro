import base64
import json
import os
import re
import subprocess
import time

import requests


TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
REPO_NAME = re.compile(r"[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+")
LIVE_BRANCH = "soundcard-live"


def github_session(repo):
    owner = repo.split("/", 1)[0]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    for user in (f"username={owner}\n", ""):
        result = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost=github.com\n{user}\n",
            capture_output=True, text=True, timeout=8, env=env,
        )
        credential = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if result.returncode == 0 and (password := credential.get("password")):
            break
    else:
        raise RuntimeError("GitHub login not available in Git Credential Manager.")
    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer " + password,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return session


def publish_when_ready(repo, url, cancelled):
    if not REPO_NAME.fullmatch(repo) or not TUNNEL_URL.fullmatch(url):
        raise ValueError("Invalid GitHub repository or tunnel URL.")
    if cancelled.is_set():
        return False

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            probe = requests.get(url + "/healthz", timeout=4, allow_redirects=False)
            if probe.status_code == 204 and probe.headers.get("Access-Control-Allow-Origin") == "*":
                break
        except requests.RequestException:
            pass
        if cancelled.wait(2):
            return False
    else:
        raise RuntimeError("The public SoundCard tunnel did not become ready.")

    with github_session(repo) as session:
        endpoint = f"https://api.github.com/repos/{repo}/contents/live.json"
        previous = session.get(endpoint, params={"ref": LIVE_BRANCH}, timeout=10)
        payload = {
            "message": "Update SoundCard live address",
            "branch": LIVE_BRANCH,
            "content": base64.b64encode(json.dumps({"url": url}).encode()).decode(),
        }
        if previous.status_code != 404:
            previous.raise_for_status()
            payload["sha"] = previous.json()["sha"]
        if cancelled.is_set():
            return False
        response = session.put(endpoint, json=payload, timeout=10)
        response.raise_for_status()
    return True
