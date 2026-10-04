#!/usr/bin/env python3
"""Install only the shared-workflow endpoint and its private service files."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


FILES = {"mcp.php": ("public", 0o644), ".htaccess": ("public", 0o644),
         "server.php": ("private", 0o600), "config.json": ("private", 0o600),
         "managed.json": ("private", 0o600)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require(not any(parent.is_symlink() for parent in (path, *path.parents)), "Refusing a symlink in an installation path")
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def locations(webroot):
    root = safe(webroot)
    require(root.is_dir() and root.name == "public_html" and root.parent.name == "mirroriedled.com",
            "Use the main mirroriedled.com public_html directory")
    public = safe(root / "ai-workflow")
    private = safe(root.parent / "mirroriedled-private/ai-workflow")
    return root, public, private


def atomic(path, data, mode):
    path = safe(path)
    require(not path.exists() or path.is_file(), "The destination is not a regular file")
    descriptor, temporary = tempfile.mkstemp(prefix=".workflow-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def config_valid(data):
    value = json.loads(data)
    require(value.get("repository") == "Crosby121/MirroriedLED-Public" and value.get("branch") == "main"
            and value.get("expected_github_account") == "Crosby121", "Invalid connector repository or service account")
    require(isinstance(value.get("github_token"), str) and len(value["github_token"]) >= 30
            and "\n" not in value["github_token"] and "\r" not in value["github_token"], "Missing private service GitHub token")
    require(isinstance(value.get("clients"), dict) and value["clients"], "Missing app credentials")
    require(isinstance(value.get("allowed_origins"), list), "Missing allowed origins")
    for client_id, client in value["clients"].items():
        require(isinstance(client_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", client_id)
                and isinstance(client, dict) and isinstance(client.get("application"), str)
                and re.fullmatch(r"[a-f0-9]{64}", client.get("token_sha256", "")), "Invalid app credential metadata")


def retain_ownership(private, recorded):
    # A first-install rollback retains backups. Keep their directory owned so a
    # corrected deployment can retry without accepting arbitrary existing files.
    if not recorded["files"]["managed.json"]["existed"]:
        marker = {"service": "mirroried-led-ai-workflow", "release": None, "state": "rolled_back"}
        atomic(private / "managed.json", (json.dumps(marker) + "\n").encode(), 0o600)


def install(webroot, source, configuration, receipt, release, expected_homepage_sha):
    root, public, private = locations(webroot)
    source, configuration, receipt = safe(source), safe(configuration), safe(receipt)
    require(re.fullmatch(r"[a-f0-9]{40}", release), "Use an exact source commit")
    require(re.fullmatch(r"[a-f0-9]{64}", expected_homepage_sha), "Supply the live-domain homepage checksum")
    homepage = safe(root / "index.html")
    require(homepage.is_file() and sha(homepage.read_bytes()) == expected_homepage_sha,
            "This destination does not match the checked live-domain homepage")
    require(root not in receipt.parents and root not in configuration.parents,
            "Configuration and receipts must stay outside public_html")
    require(not receipt.exists() and receipt.parent.is_dir(), "Use a new private receipt path")
    contents = {}
    for name in ("mcp.php", ".htaccess", "server.php"):
        path = safe(source / name)
        require(path.is_file(), "Missing connector source file")
        contents[name] = path.read_bytes()
        require(len(contents[name]) <= 1048576, "Oversized connector file")
    contents["config.json"] = configuration.read_bytes()
    config_valid(contents["config.json"])
    contents["managed.json"] = (json.dumps({"service": "mirroried-led-ai-workflow", "release": release}) + "\n").encode()
    marker = private / "managed.json"
    if marker.exists():
        require(json.loads(safe(marker).read_text()).get("service") == "mirroried-led-ai-workflow", "Existing connector ownership is unknown")
    else:
        require(not public.exists() or not any(public.iterdir()), "An unowned public connector directory already exists")
        require(not private.exists() or not any(private.iterdir()), "An unowned private connector directory already exists")
    public.mkdir(mode=0o755, parents=True, exist_ok=True)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    backup = Path(tempfile.mkdtemp(prefix="backup-", dir=private))
    recorded = {"schema_version": 1, "service": "mirroried-led-ai-workflow", "release": release,
                "webroot": str(root), "backup": str(backup), "files": {}}
    for name, (area, mode) in FILES.items():
        target = safe((public if area == "public" else private) / name)
        require(not target.exists() or target.is_file(), "Unsafe connector target")
        prior = target.read_bytes() if target.exists() else None
        entry = {"existed": prior is not None, "previous_mode": target.stat().st_mode & 0o777 if prior is not None else mode,
                 "installed_sha256": sha(contents[name]), "backup_sha256": sha(prior) if prior is not None else None}
        if prior is not None:
            atomic(backup / name, prior, 0o600)
        recorded["files"][name] = entry
    atomic(receipt, (json.dumps(recorded, indent=2) + "\n").encode(), 0o600)
    changed = []
    try:
        # Access rules first, then private implementation/config, then public entry point.
        for name in (".htaccess", "server.php", "config.json", "managed.json", "mcp.php"):
            area, mode = FILES[name]
            atomic((public if area == "public" else private) / name, contents[name], mode)
            changed.append(name)
    except Exception:
        for name in reversed(changed):
            area, mode = FILES[name]
            target = (public if area == "public" else private) / name
            entry = recorded["files"][name]
            if entry["existed"]:
                atomic(target, (backup / name).read_bytes(), entry["previous_mode"])
            else:
                target.unlink()
        retain_ownership(private, recorded)
        raise
    return recorded


def rollback(webroot, receipt):
    root, public, private = locations(webroot)
    recorded = json.loads(safe(receipt).read_text())
    require(recorded.get("service") == "mirroried-led-ai-workflow" and recorded.get("webroot") == str(root)
            and set(recorded.get("files", {})) == set(FILES), "Invalid connector rollback receipt")
    backup = safe(recorded["backup"])
    require(backup.parent == private and backup.name.startswith("backup-"), "Backup must belong to this connector")
    validated = {}
    for name, (area, _) in FILES.items():
        target = safe((public if area == "public" else private) / name)
        entry = recorded["files"][name]
        require(target.is_file() and sha(target.read_bytes()) == entry["installed_sha256"],
                "Connector files changed since this release; rollback would overwrite later work")
        previous = None
        if entry["existed"]:
            previous = safe(backup / name).read_bytes()
            require(sha(previous) == entry["backup_sha256"], "Connector backup integrity check failed")
        require(isinstance(entry["previous_mode"], int) and 0 <= entry["previous_mode"] <= 0o777, "Invalid previous file mode")
        validated[name] = (target, entry, previous)
    for name in ("mcp.php", "config.json", "server.php", "managed.json", ".htaccess"):
        target, entry, previous = validated[name]
        if previous is None:
            target.unlink()
        else:
            atomic(target, previous, entry["previous_mode"])
    retain_ownership(private, recorded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "rollback"))
    parser.add_argument("--webroot", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--source")
    parser.add_argument("--config")
    parser.add_argument("--release")
    parser.add_argument("--expected-homepage-sha")
    args = parser.parse_args()
    try:
        if args.command == "install":
            require(all((args.source, args.config, args.release, args.expected_homepage_sha)), "Installation requires source, private config, release and live-homepage checksum")
            install(args.webroot, args.source, args.config, args.receipt, args.release, args.expected_homepage_sha)
            print("WORKFLOW_CONNECTOR_INSTALLED")
        else:
            rollback(args.webroot, args.receipt)
            print("WORKFLOW_CONNECTOR_ROLLED_BACK")
    except (ValueError, OSError, TypeError, KeyError) as error:
        print("Connector installation/rollback failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
