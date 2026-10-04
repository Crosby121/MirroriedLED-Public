#!/usr/bin/env python3
"""Create private connector configuration; never print credentials."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


APPLICATIONS = {
    "chatgpt-codex": "ChatGPT Work / Codex",
    "copilot": "GitHub Copilot",
    "hostinger-agent": "Hostinger Agent",
}


def create_config(directory, github_token):
    directory = Path(directory).absolute()
    if len(github_token) < 30 or "\n" in github_token or "\r" in github_token:
        raise ValueError("Enter a valid repository-scoped GitHub token.")
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise ValueError("Use a private directory without symlinks.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        account = subprocess.run(["whoami"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", account + ":(OI)(CI)F"], check=True, capture_output=True)
    if any((directory / name).exists() for name in ("config.json", "client-credentials.json")):
        raise ValueError("Private configuration already exists; keep client IDs when rotating credentials.")
    credentials = {key: "mlwf_" + secrets.token_urlsafe(48) for key in APPLICATIONS}
    config = {
        "repository": "Crosby121/MirroriedLED-Public", "branch": "main",
        "expected_github_account": "Crosby121", "github_token": github_token,
        "allowed_origins": ["https://mirroriedled.com", "https://chatgpt.com", "https://agent.hostinger.com"],
        "clients": {key: {"application": app, "token_sha256": hashlib.sha256(credentials[key].encode()).hexdigest()}
                    for key, app in APPLICATIONS.items()},
    }
    # O_EXCL prevents accidental replacement, and 0600 applies at creation.
    written = []
    try:
        for name, data in (("config.json", config), ("client-credentials.json", credentials)):
            path = directory / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            written.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="mirroriedled-private/ai-workflow")
    args = parser.parse_args()
    token = getpass.getpass("GitHub token (MirroriedLED-Public Contents read/write only): ").strip()
    try:
        create_config(args.directory, token)
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Private configuration could not be created. Check the directory, token format and access permissions.", file=sys.stderr)
        return 1
    print("Private configuration created. Store each app credential in that app's secure connection settings.")
    print("Do not upload client-credentials.json to GitHub or public_html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
