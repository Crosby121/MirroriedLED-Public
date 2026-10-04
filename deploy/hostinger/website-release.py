#!/usr/bin/env python3
"""Install or roll back the complete public website without changing private records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import zipfile

PUBLIC_FILES = (
    "index.html", "styles.css", "app.js", "repair.js",
    "infinity-mirror.webp", "stadium-model.webp", "led-display.webp", "address-sign.webp",
    "customer-portal/index.html", "customer-portal/portal.css", "customer-portal/portal.js",
    "customer-portal/business.css", "customer-portal/business.js", "customer-portal/operations.html",
    "customer-portal/backend/api.php", "customer-portal/backend/portal.php",
    "customer-portal/backend/business.php", "customer-portal/backend/.htaccess",
    "customer-portal/backend/.user.ini",
    "customer-portal/backend/builder.php",
    "infinity-builder/index.html", "infinity-builder/builder.css", "infinity-builder/builder.js",
    "infinity-builder/engine.js", "infinity-builder/draft-store.js", "infinity-builder/catalog.json",
    "infinity-builder/artwork/orbit.svg", "infinity-builder/artwork/tree.svg", "infinity-builder/artwork/wave.svg",
)
MANIFEST = "CUSTOMER_PORTAL_SHA256SUMS.txt"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def within(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


def no_symlinks(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("A release destination or its parent is a symlink")


def webroot_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("An absolute website hosting path is required")
    if not re.fullmatch(r"/home/u[0-9]+/domains/mirroriedled\.com/public_html", str(path)):
        raise ValueError("Use the main website hosting webroot, not the sponsor VPS")
    no_symlinks(path)
    if not path.is_dir():
        raise ValueError("The main website webroot does not exist on this host")
    check_destinations(path)
    return path


def check_destinations(path: Path) -> None:
    no_symlinks(path)
    for name in PUBLIC_FILES:
        target = path / name
        no_symlinks(target)
        if target.exists() and not target.is_file():
            raise ValueError("A public release file conflicts with an existing directory")
        for parent in target.parents:
            if parent == path:
                break
            if parent.exists() and not parent.is_dir():
                raise ValueError("A public release directory conflicts with an existing file")


def unpack(archive: Path, directory: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        allowed = set(PUBLIC_FILES) | {MANIFEST}
        if len(entries) != len(allowed) or {item.filename for item in entries} != allowed:
            raise ValueError("Release ZIP must contain exactly the public website allowlist")
        for item in entries:
            mode = item.external_attr >> 16
            if item.is_dir() or mode & 0o170000 not in (0, 0o100000):
                raise ValueError("Release ZIP contains an unsafe file type")
            if not 0 < item.file_size <= 50 * 1024 * 1024:
                raise ValueError("Release ZIP contains an empty or oversized file")
        for item in entries:
            target = directory / item.filename
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)
    lines = (directory / MANIFEST).read_text().splitlines()
    expected = {}
    for line in lines:
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if not match or match[2] not in PUBLIC_FILES or match[2] in expected:
            raise ValueError("Release checksum manifest is invalid")
        expected[match[2]] = match[1]
    if set(expected) != set(PUBLIC_FILES):
        raise ValueError("Release checksums do not cover the complete website")
    for name in PUBLIC_FILES:
        if digest(directory / name) != expected[name]:
            raise ValueError("A release file failed its checksum")


def atomic_copy(source: Path, destination: Path, mode: int = 0o644) -> None:
    no_symlinks(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    # Keep temporary PHP/source files private until their final filename is ready.
    fd, temporary = tempfile.mkstemp(prefix=".mled-install-", dir=source.parent)
    temporary_path = Path(temporary)
    try:
        with source.open("rb") as input_stream, os.fdopen(fd, "wb") as output:
            shutil.copyfileobj(input_stream, output)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def make_backup(root: Path, release_id: str) -> Path:
    backup_root = root.parent / "mirroriedled-backups"
    no_symlinks(backup_root)
    backup_root.mkdir(exist_ok=True, mode=0o700)
    backup_root.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path(tempfile.mkdtemp(prefix=f"website-{stamp}-{release_id[:12]}-", dir=backup_root))
    archive = backup / "public_html.tar.gz"
    with tarfile.open(archive, "w:gz", dereference=False) as bundle:
        bundle.add(root, arcname="public_html", recursive=True)
    archive.chmod(0o600)
    # Read every archived file to detect truncation before changing any live file.
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if member.isfile():
                stream = bundle.extractfile(member)
                if stream is None:
                    raise ValueError("The full-site backup could not be verified")
                with stream:
                    while stream.read(1024 * 1024):
                        pass
    records = {}
    created_directories = set()
    for name in PUBLIC_FILES:
        target = root / name
        for parent in target.parents:
            if parent == root:
                break
            if not parent.exists():
                created_directories.add(str(parent.relative_to(root)))
        if target.exists():
            saved = backup / "files" / name
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(target, saved)
            saved.chmod(0o600)
            records[name] = {"sha256": digest(saved), "mode": target.stat().st_mode & 0o777}
        else:
            records[name] = None
    metadata = {"webroot": str(root), "release_id": release_id, "files": records,
                "created_directories": sorted(created_directories), "archive_sha256": digest(archive)}
    (backup / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (backup / "metadata.json").chmod(0o600)
    return backup


def restore(root: Path, backup: Path) -> None:
    check_destinations(root)
    no_symlinks(backup)
    if not backup.is_dir() or backup.parent != root.parent / "mirroriedled-backups":
        raise ValueError("Rollback requires this website's private backup directory")
    no_symlinks(backup / "metadata.json")
    no_symlinks(backup / "public_html.tar.gz")
    metadata = json.loads((backup / "metadata.json").read_text())
    if metadata.get("webroot") != str(root) or set(metadata.get("files", {})) != set(PUBLIC_FILES):
        raise ValueError("Rollback metadata does not match this website")
    if digest(backup / "public_html.tar.gz") != metadata.get("archive_sha256"):
        raise ValueError("Full-site backup checksum failed")
    # Validate the entire rollback before replacing or removing a file.
    for name, record in metadata["files"].items():
        if record is not None:
            saved = backup / "files" / name
            no_symlinks(saved)
            if not saved.is_file() or digest(saved) != record.get("sha256"):
                raise ValueError("Rollback file checksum failed")
            if not isinstance(record.get("mode"), int) or not 0 <= record["mode"] <= 0o777:
                raise ValueError("Rollback permissions are invalid")
    directories = metadata.get("created_directories", [])
    allowed_directories = {str(Path(name).parent) for name in PUBLIC_FILES} | {"customer-portal"}
    if not isinstance(directories, list) or any(name not in allowed_directories - {"."} for name in directories):
        raise ValueError("Rollback directory metadata is invalid")
    order = sorted(PUBLIC_FILES, key=lambda name: (name == "index.html", name))
    for name in order:
        target = root / name
        record = metadata["files"][name]
        if record is None:
            target.unlink(missing_ok=True)
        else:
            atomic_copy(backup / "files" / name, target, record["mode"])
    for name in sorted(directories, key=lambda value: value.count("/"), reverse=True):
        try:
            (root / name).rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            # Unrelated files created after deployment must remain intact.
            pass


def install(root: Path, archive: Path, release_id: str, expected_homepage_sha: str, receipt: Path) -> Path:
    check_destinations(root)
    if not re.fullmatch(r"[a-f0-9]{40}", release_id):
        raise ValueError("A full Git commit SHA is required")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_homepage_sha):
        raise ValueError("The live homepage checksum is required")
    no_symlinks(archive)
    no_symlinks(receipt)
    if within(receipt, root) or within(archive, root):
        raise ValueError("Release packages and receipts must remain outside the webroot")
    if digest(root / "index.html") != expected_homepage_sha:
        raise ValueError("This SSH host or directory does not match the live website")
    with tempfile.TemporaryDirectory(prefix=".mled-verified-", dir=root.parent) as temporary:
        stage = Path(temporary)
        unpack(archive, stage)
        backup = make_backup(root, release_id)
        receipt_text = json.dumps({"webroot": str(root), "backup": str(backup), "release_id": release_id}) + "\n"
        (backup / "receipt.json").write_text(receipt_text)
        (backup / "receipt.json").chmod(0o600)
        receipt.write_text(receipt_text)
        receipt.chmod(0o600)
        # Install the access rules first and publish the homepage last.
        order = sorted(PUBLIC_FILES, key=lambda name: (name != "customer-portal/backend/.htaccess", name == "index.html", name))
        try:
            for name in order:
                atomic_copy(stage / name, root / name)
            for name in PUBLIC_FILES:
                if digest(root / name) != digest(stage / name):
                    raise ValueError("Installed website checksum failed")
        except BaseException:
            restore(root, backup)
            raise
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    parser.add_argument("--webroot", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--release-id")
    parser.add_argument("--expected-homepage-sha")
    args = parser.parse_args()
    root = webroot_path(args.webroot)
    receipt = args.receipt.absolute()
    if within(receipt, root):
        raise ValueError("Rollback receipts must remain outside the webroot")
    if args.action == "install":
        if not args.archive or not args.release_id or not args.expected_homepage_sha:
            parser.error("install needs --archive, --release-id and --expected-homepage-sha")
        install(root, args.archive.absolute(), args.release_id, args.expected_homepage_sha, receipt)
        print(f"WEBSITE_RELEASE_INSTALLED: all {len(PUBLIC_FILES)} public files; private records preserved")
    else:
        no_symlinks(receipt)
        data = json.loads(receipt.read_text())
        if data.get("webroot") != str(root):
            raise ValueError("Rollback receipt is for another website")
        restore(root, Path(data["backup"]))
        print("WEBSITE_RELEASE_ROLLED_BACK: public files restored; private records preserved")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise SystemExit(f"Website release stopped: {error}") from None
