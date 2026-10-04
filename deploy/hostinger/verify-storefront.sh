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
check_url "$DOMAIN/" "Advertising on the Go"
check_url "$DOMAIN/" "Sponsor Partner Program"

home="$(curl -L -sS --max-time 20 "$DOMAIN/")"
grep -q 'sponsors\.mirroriedled\.com' <<<"$home" || fail "Sponsor portal link missing from public storefront"

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

echo "Checking sponsor portal boundary..."
code="$(curl -L -sS -o /tmp/mirroriedled-sponsor.html -w '%{http_code}' --max-time 20 "$SPONSOR_URL" || true)"
case "$code" in
  200|301|302|303|307|308) echo "OK $SPONSOR_URL HTTP $code" ;;
  *) fail "Sponsor portal is not reachable: HTTP $code" ;;
esac

echo "PUBLIC STOREFRONT VERIFICATION SUCCESS"
