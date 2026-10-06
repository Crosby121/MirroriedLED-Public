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
    "infinity-builder/artwork/orbit.svg", "infinity-builder/artwork/tree.svg", "infinity-builder/artwork/wave.svg",
    "products/index.html",
    "products/products.css",
    "stadiums/index.html",
    "stadiums/stadiums.css",
    "stadiums/stadiums.js",
    "stadiums/core.js",
    "stadiums/data.js",
    "stadiums/assets/baseball/arizona-diamondbacks/layout-preview-thumb.webp",
    "stadiums/assets/baseball/arizona-diamondbacks/layout-preview.webp",
    "stadiums/assets/baseball/athletics/layout-preview-thumb.webp",
    "stadiums/assets/baseball/athletics/layout-preview.webp",
    "stadiums/assets/baseball/atlanta-braves/layout-preview-thumb.webp",
    "stadiums/assets/baseball/atlanta-braves/layout-preview.webp",
    "stadiums/assets/baseball/baltimore-orioles/layout-preview-thumb.webp",
    "stadiums/assets/baseball/baltimore-orioles/layout-preview.webp",
    "stadiums/assets/baseball/boston-red-sox/layout-preview-thumb.webp",
    "stadiums/assets/baseball/boston-red-sox/layout-preview.webp",
    "stadiums/assets/baseball/boston-red-sox/showcase-thumb.webp",
    "stadiums/assets/baseball/boston-red-sox/showcase.webp",
    "stadiums/assets/baseball/boston-red-sox/stadium-only-thumb.webp",
    "stadiums/assets/baseball/boston-red-sox/stadium-only.webp",
    "stadiums/assets/baseball/chicago-cubs/layout-preview-thumb.webp",
    "stadiums/assets/baseball/chicago-cubs/layout-preview.webp",
    "stadiums/assets/baseball/chicago-white-sox/layout-preview-thumb.webp",
    "stadiums/assets/baseball/chicago-white-sox/layout-preview.webp",
    "stadiums/assets/baseball/cincinnati-reds/layout-preview-thumb.webp",
    "stadiums/assets/baseball/cincinnati-reds/layout-preview.webp",
    "stadiums/assets/baseball/cleveland-guardians/layout-preview-thumb.webp",
    "stadiums/assets/baseball/cleveland-guardians/layout-preview.webp",
    "stadiums/assets/baseball/colorado-rockies/layout-preview-thumb.webp",
    "stadiums/assets/baseball/colorado-rockies/layout-preview.webp",
    "stadiums/assets/baseball/detroit-tigers/layout-preview-thumb.webp",
    "stadiums/assets/baseball/detroit-tigers/layout-preview.webp",
    "stadiums/assets/baseball/houston-astros/layout-preview-thumb.webp",
    "stadiums/assets/baseball/houston-astros/layout-preview.webp",
    "stadiums/assets/baseball/kansas-city-royals/layout-preview-thumb.webp",
    "stadiums/assets/baseball/kansas-city-royals/layout-preview.webp",
    "stadiums/assets/baseball/los-angeles-angels/layout-preview-thumb.webp",
    "stadiums/assets/baseball/los-angeles-angels/layout-preview.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/birch-concept-thumb.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/birch-concept.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/layout-preview-thumb.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/layout-preview.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/showcase-thumb.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/showcase.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/stadium-only-thumb.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/stadium-only.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/sizes-thumb.webp",
    "stadiums/assets/baseball/los-angeles-dodgers/sizes.webp",
    "stadiums/assets/baseball/miami-marlins/layout-preview-thumb.webp",
    "stadiums/assets/baseball/miami-marlins/layout-preview.webp",
    "stadiums/assets/baseball/milwaukee-brewers/layout-preview-thumb.webp",
    "stadiums/assets/baseball/milwaukee-brewers/layout-preview.webp",
    "stadiums/assets/baseball/minnesota-twins/layout-preview-thumb.webp",
    "stadiums/assets/baseball/minnesota-twins/layout-preview.webp",
    "stadiums/assets/baseball/new-york-mets/layout-preview-thumb.webp",
    "stadiums/assets/baseball/new-york-mets/layout-preview.webp",
    "stadiums/assets/baseball/new-york-yankees/birch-concept-thumb.webp",
    "stadiums/assets/baseball/new-york-yankees/birch-concept.webp",
    "stadiums/assets/baseball/new-york-yankees/cardboard-concept-thumb.webp",
    "stadiums/assets/baseball/new-york-yankees/cardboard-concept.webp",
    "stadiums/assets/baseball/new-york-yankees/layout-preview-thumb.webp",
    "stadiums/assets/baseball/new-york-yankees/layout-preview.webp",
    "stadiums/assets/baseball/new-york-yankees/showcase-thumb.webp",
    "stadiums/assets/baseball/new-york-yankees/showcase.webp",
    "stadiums/assets/baseball/philadelphia-phillies/layout-preview-thumb.webp",
    "stadiums/assets/baseball/philadelphia-phillies/layout-preview.webp",
    "stadiums/assets/baseball/pittsburgh-pirates/layout-preview-thumb.webp",
    "stadiums/assets/baseball/pittsburgh-pirates/layout-preview.webp",
    "stadiums/assets/baseball/san-diego-padres/layout-preview-thumb.webp",
    "stadiums/assets/baseball/san-diego-padres/layout-preview.webp",
    "stadiums/assets/baseball/san-francisco-giants/layout-preview-thumb.webp",
    "stadiums/assets/baseball/san-francisco-giants/layout-preview.webp",
    "stadiums/assets/baseball/seattle-mariners/layout-preview-thumb.webp",
    "stadiums/assets/baseball/seattle-mariners/layout-preview.webp",
    "stadiums/assets/baseball/st-louis-cardinals/layout-preview-thumb.webp",
    "stadiums/assets/baseball/st-louis-cardinals/layout-preview.webp",
    "stadiums/assets/baseball/tampa-bay-rays/layout-preview-thumb.webp",
    "stadiums/assets/baseball/tampa-bay-rays/layout-preview.webp",
    "stadiums/assets/baseball/texas-rangers/layout-preview-thumb.webp",
    "stadiums/assets/baseball/texas-rangers/layout-preview.webp",
    "stadiums/assets/baseball/toronto-blue-jays/layout-preview-thumb.webp",
    "stadiums/assets/baseball/toronto-blue-jays/layout-preview.webp",
    "stadiums/assets/baseball/washington-nationals/layout-preview-thumb.webp",
    "stadiums/assets/baseball/washington-nationals/layout-preview.webp",
    "stadiums/assets/football/los-angeles-rams/model-concept-thumb.webp",
    "stadiums/assets/football/los-angeles-rams/model-concept.webp",
    "stadiums/assets/football/los-angeles-rams/showcase-thumb.webp",
    "stadiums/assets/football/los-angeles-rams/showcase.webp",
    "stadiums/assets/football/los-angeles-rams/wood-concept-thumb.webp",
    "stadiums/assets/football/los-angeles-rams/wood-concept.webp",
    "infinity-builder/artwork/generated/dodgers-bats.webp",
    "infinity-builder/artwork/generated/dodgers-engraved.webp",
    "infinity-builder/artwork/generated/dodgers-la.webp",
    "infinity-builder/artwork/generated/dodgers-skyline.webp",
    "infinity-builder/artwork/generated/sports-emblems.webp",
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
