"""Isolated, local-only storefront and portal for browser acceptance checks."""
import json
from pathlib import Path
import shutil
import sys

from test_business_backend import BusinessServer

ROOT=Path(__file__).resolve().parents[1]
server=BusinessServer()
try:
    shutil.copytree(ROOT/'infinity-builder',server.public/'infinity-builder')
    shutil.copytree(ROOT/'customer-portal',server.public/'customer-portal',dirs_exist_ok=True)
    for name in ['index.html','styles.css','app.js','repair.js','infinity-mirror.webp','stadium-model.webp','led-display.webp','address-sign.webp']:
        shutil.copyfile(ROOT/name,server.public/name)
    print(json.dumps({'url':server.origin}),flush=True)
    sys.stdin.read()
finally:
    server.close()
