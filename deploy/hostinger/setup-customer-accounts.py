#!/usr/bin/env python3
"""Install a missing private portal template; never replace existing configuration."""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile


def private_directory(path: Path, require_owner_only: bool = True) -> None:
    if path.is_symlink():
        raise ValueError('Private directory symlink is not allowed')
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Private directory must be owned by the hosting account')
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ValueError('Existing private directory write permissions need owner review')
    if require_owner_only and stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Existing private directory permissions need owner review')


def setup(webroot: Path, template: Path) -> dict:
    webroot = webroot.absolute()
    if any(path.is_symlink() for path in (webroot, *webroot.parents)):
        raise ValueError('Webroot ancestor symlinks are not allowed')
    if webroot.name != 'public_html' or not webroot.is_dir():
        raise ValueError('Use the existing public_html directory without symlinks')
    root = webroot.resolve(strict=True)
    parent = root.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o022:
        raise ValueError('Domain parent ownership or write permissions need owner review')
    shared = root.parent / 'mirroriedled-private'
    private_directory(shared, require_owner_only=False)
    private = shared / 'customer-portal'
    private_directory(private)
    config = private / 'config.php'
    if config.is_symlink():
        raise ValueError('Private configuration symlink is not allowed')
    if config.exists():
        if not config.is_file():
            raise ValueError('Existing configuration needs owner review')
        return {'created': False, 'existing_configuration_preserved': True}
    private_directory(private / 'storage')
    data = template.read_bytes()
    if not data.startswith(b'<?php') or len(data) > 65536:
        raise ValueError('Use the reviewed PHP configuration template')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=private, prefix='.config-', delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        # Atomic, exclusive publication: concurrent setup cannot replace any file.
        os.link(temporary, config, follow_symlinks=False)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'created': True, 'private_configuration_installed': True,
            'merchant_activation_performed': False, 'staff_accounts_created': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webroot', required=True, type=Path)
    parser.add_argument('--template', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(setup(args.webroot, args.template), sort_keys=True))
