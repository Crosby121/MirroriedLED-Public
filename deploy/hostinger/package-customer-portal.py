#!/usr/bin/env python3
"""Package only the public storefront and draft Customer Portal; never private data."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_FILES = (
    "index.html", "styles.css", "app.js", "repair.js",
    "infinity-mirror.webp", "stadium-model.webp", "led-display.webp", "address-sign.webp",
    "customer-portal/index.html", "customer-portal/portal.css", "customer-portal/portal.js",
    "customer-portal/business.css", "customer-portal/business.js", "customer-portal/operations.html",
    "customer-portal/backend/api.php", "customer-portal/backend/portal.php",
    "customer-portal/backend/business.php",
    "customer-portal/backend/.htaccess", "customer-portal/backend/.user.ini",
    "customer-portal/backend/builder.php",
    "infinity-builder/index.html", "infinity-builder/builder.css", "infinity-builder/builder.js",
    "infinity-builder/engine.js", "infinity-builder/draft-store.js", "infinity-builder/catalog.json",
    "customer-portal/backend/commerce.php",
    "shop/index.html", "shop/shop.css", "shop/shop.js", "shop/availability.js",
    "address-builder/index.html", "address-builder/builder.js",
    "infinity-builder/artwork/orbit.svg", "infinity-builder/artwork/tree.svg", "infinity-builder/artwork/wave.svg",
)


def package(output: Path) -> None:
    contents: dict[str, bytes] = {}
    for name in PUBLIC_FILES:
        source = ROOT / name
        if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
            raise ValueError(f"Missing or unsafe public release file: {name}")
        contents[name] = source.read_bytes()
    checksums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in contents.items())
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in contents.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, data)
        bundle.writestr("CUSTOMER_PORTAL_SHA256SUMS.txt", checksums)
    with zipfile.ZipFile(output) as bundle:
        if bundle.testzip() is not None or set(bundle.namelist()) != set(PUBLIC_FILES) | {"CUSTOMER_PORTAL_SHA256SUMS.txt"}:
            raise ValueError("Release ZIP validation failed")
    print(f"PUBLIC_PORTAL_PACKAGE={output.resolve()}")
    print(f"FILES={len(PUBLIC_FILES)}")
    print(f"SHA256={hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    package(parser.parse_args().output)
