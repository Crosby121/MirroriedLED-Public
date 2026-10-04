#!/usr/bin/env python3
"""Verify the full public release through HTTPS after Hostinger installation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import runpy
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

RELEASE = runpy.run_path(str(Path(__file__).with_name("website-release.py")))
PUBLIC_ASSETS = tuple(name for name in RELEASE["PUBLIC_FILES"] if not name.startswith("customer-portal/backend/"))


def fetch(base: str, path: str, release: str) -> tuple[int, bytes]:
    separator = "&" if "?" in path else "?"
    request = Request(base + "/" + path + separator + "mled_release=" + release,
                      headers={"Cache-Control": "no-cache", "User-Agent": "MirroriedLED-release-verification"})
    try:
        with urlopen(request, timeout=30) as response:
            final = urlparse(response.url)
            if final.scheme != "https" or final.hostname not in ("mirroriedled.com", "www.mirroriedled.com"):
                raise ValueError("Public verification redirected outside the website")
            return response.status, response.read(5 * 1024 * 1024 + 1)
    except HTTPError as error:
        return error.code, b""


def verify(source: Path, base: str, release: str) -> bool:
    if base not in ("https://mirroriedled.com", "https://www.mirroriedled.com"):
        raise ValueError("Verify the main Mirroried LED website over HTTPS")
    if not release.isalnum():
        raise ValueError("A safe release identifier is required")

    def verify_asset(name: str) -> None:
        status, body = fetch(base, name, release)
        expected = hashlib.sha256((source / name).read_bytes()).digest()
        if status != 200 or hashlib.sha256(body).digest() != expected:
            raise ValueError("Live release differs from GitHub: " + name)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(verify_asset, PUBLIC_ASSETS))
    status, homepage = fetch(base, "", release)
    if status != 200 or hashlib.sha256(homepage).digest() != hashlib.sha256((source / "index.html").read_bytes()).digest():
        raise ValueError("The website homepage does not serve the new release")
    for name in ("portal.php", "business.php", "builder.php", "config.php", "config.example.php", ".htaccess", ".user.ini"):
        status, _ = fetch(base, "customer-portal/backend/" + name, release)
        if status not in (403, 404):
            raise ValueError("An internal portal file is publicly reachable: " + name)
    status, body = fetch(base, "customer-portal/backend/api.php?action=session", release)
    if status != 200:
        raise ValueError("The customer portal API is unavailable")
    session = json.loads(body)
    if session.get("ok") is not True or not isinstance(session.get("configured"), bool):
        raise ValueError("The customer portal API did not return a valid status")
    print("LIVE_WEBSITE_VERIFIED: storefront, customer portal, team page, assets and PHP access rules")
    print("PRIVATE_PORTAL_CONFIGURED=" + ("yes" if session["configured"] else "no; private setup remains required"))
    return session["configured"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--url", default="https://mirroriedled.com")
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    verify(args.source, args.url.rstrip("/"), args.release)
