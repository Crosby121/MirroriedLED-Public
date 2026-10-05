#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-https://mirroriedled.com}"
SPONSOR_URL="${SPONSOR_URL:-https://sponsors.mirroriedled.com/}"

fail() { echo "ERROR: $*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "curl is required"

check_url() {
  local url="$1"
  local expect="$2"
  local out
  out="$(mktemp)"
  local code
  code="$(curl -L -sS -o "$out" -w '%{http_code}' --max-time 20 "$url")"
  [[ "$code" == "200" ]] || fail "$url returned HTTP $code"
  grep -qi "$expect" "$out" || fail "$url did not contain expected text: $expect"
  rm -f "$out"
  echo "OK $url"
}

check_url "$DOMAIN/" "Mirroried LED"
check_url "$DOMAIN/" "Infinity Mirrors"
check_url "$DOMAIN/" "Address signs"

echo "Checking storefront files and product images..."
for asset in index.html styles.css app.js repair.js infinity-mirror.webp stadium-model.webp led-display.webp address-sign.webp; do
  out="$(mktemp)"
  code="$(curl --location --fail --silent --show-error -o "$out" -w '%{http_code}' --max-time 20 "${DOMAIN%/}/$asset")" || {
    rm -f "$out"
    fail "$asset could not be downloaded"
  }
  if [[ "$code" != "200" || ! -s "$out" ]]; then
    rm -f "$out"
    fail "$asset returned HTTP $code or an empty response"
  fi
  rm -f "$out"
  echo "OK ${DOMAIN%/}/$asset"
done

echo "PUBLIC STOREFRONT VERIFICATION SUCCESS"

echo "This legacy check verifies storefront assets only; use verify-website.py for the complete customer ordering release."
