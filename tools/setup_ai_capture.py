#!/usr/bin/env python3
"""One-time local PC setup for private AI chat capture."""

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

from ai_capture import ROOT, REPOSITORY, EXTENSION_ID, GitHubArchive, atomic, encoded, require, safe


def create_config(directory, token, transcript_roots):
    directory = safe(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        account = subprocess.run(["whoami"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", account + ":(OI)(CI)F"], check=True, capture_output=True)
    path = directory / "config.json"
    require(not path.exists(), "Capture configuration already exists; edit its authorized roots privately if needed")
    config = {"repository": REPOSITORY, "github_token": token, "workspace": str(ROOT),
              "spool": str(directory / "spool"), "transcript_roots": [str(safe(root)) for root in transcript_roots]}
    return path, config


def setup_windows(directory, config_path):
    # Register only this user's native host and background worker, without admin access.
    python = str(Path(sys.executable).resolve())
    script = str(ROOT / "tools/ai_capture.py")
    require(not any(character in value for value in [python, script, str(config_path)] for character in ('"', '%', '\r', '\n')), "Unsupported command path")
    launcher = directory / "native-host.cmd"
    atomic(launcher, ('@echo off\r\n"%s" "%s" native --config "%s" %%*\r\n' % (python, script, config_path)).encode())
    manifest_path = directory / "native-host.json"
    atomic(manifest_path, encoded({"name": "com.mirroriedled.ai_capture", "description": "Mirroried LED private AI capture",
                                  "path": str(launcher), "type": "stdio", "allowed_origins": ["chrome-extension://" + EXTENSION_ID + "/"]}))
    def quoted(value):
        return "'" + str(value).replace("'", "''") + "'"
    arguments = '"%s" watch --config "%s"' % (script, config_path)
    powershell = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$key = 'HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.mirroriedled.ai_capture'",
        "$manifest = " + quoted(manifest_path),
        "if (Test-Path $key) { $prior = (Get-Item $key).GetValue(''); if ($prior -ne $manifest) { throw 'An existing native capture host uses another path; review it before replacing it.' } }",
        "New-Item -Path $key -Force | Out-Null",
        "Set-Item -Path $key -Value $manifest",
        "$name = 'MirroriedLED-AICapture'",
        "$description = 'Mirroried LED private chat checkpoint retry worker'",
        "$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue",
        "if ($existing -and $existing.Description -ne $description) { throw 'The scheduled task name is already used by another task.' }",
        "$action = New-ScheduledTaskAction -Execute " + quoted(python) + " -Argument " + quoted(arguments),
        "$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name",
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user",
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)",
        "Register-ScheduledTask -TaskName $name -Description $description -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null",
        "Start-ScheduledTask -TaskName $name",
    ])
    setup_file = directory / "register-capture.ps1"
    atomic(setup_file, powershell.encode())
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(setup_file)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-private-repository", action="store_true")
    parser.add_argument("--directory", default=str(ROOT / "mirroriedled-private/ai-capture"))
    parser.add_argument("--transcript-root", action="append")
    parser.add_argument("--skip-windows-registration", action="store_true")
    args = parser.parse_args()
    directory = safe(args.directory)
    path = directory / "config.json"
    try:
        if path.exists():
            config = json.loads(path.read_text())
            GitHubArchive(config).verify()
        else:
            roots = args.transcript_root or [str(Path.home() / ".codex/sessions"), str(Path.home() / ".copilot/session-state")]
            if os.environ.get("APPDATA"):
                roots.append(str(Path(os.environ["APPDATA"]) / "Code/User/workspaceStorage"))
            token = getpass.getpass("Private GitHub AI-history token (hidden input): ").strip()
            require(len(token) >= 30 and "\n" not in token and "\r" not in token, "Enter a valid GitHub token")
            path, config = create_config(directory, token, roots)
            archive = GitHubArchive(config)
            account = archive.request("GET", "/user")
            require(account.get("login") == "Crosby121", "Use the authorized Crosby121 GitHub account")
            repo = archive.request("GET", "/repos/" + REPOSITORY, missing_ok=True)
            if repo is None and args.create_private_repository:
                archive.request("POST", "/user/repos", {"name": "MirroriedLED-AI-History", "private": True, "auto_init": True,
                                                        "description": "Private Mirroried LED AI chat checkpoints and session archives"})
            archive.verify()
            atomic(path, encoded(config))
        if os.name == "nt" and not args.skip_windows_registration:
            setup_windows(directory, path)
            print("Private capture configured. The Windows retry worker is running.")
        else:
            print("Private capture configured. Run tools/ai_capture.py watch with this config on a persistent local computer.")
        print("Load tools/browser-ai-capture in Chrome, then enable tracking on the Mirroried LED chat tabs.")
        return 0
    except Exception:
        print("Capture setup did not complete. Verify the PRIVATE MirroriedLED-AI-History repository, token access and local registration. No credential values were printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
