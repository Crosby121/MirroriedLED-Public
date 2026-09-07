#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HTML="${PUBLIC_HTML:-$HOME/domains/mirroriedled.com/public_html}"
PACKAGE_DIR="${1:-$(pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/mirroriedled-backups}"
DOMAIN="${DOMAIN:-https://mirroriedled.com}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$BACKUP_ROOT/storefront-$STAMP"

required=(index.html styles.css app.js)

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$PUBLIC_HTML" ]] || fail "PUBLIC_HTML does not exist: $PUBLIC_HTML"
[[ "$PUBLIC_HTML" == *public_html* ]] || fail "Refusing to deploy outside a public_html path: $PUBLIC_HTML"
[[ "$PUBLIC_HTML" != "/" ]] || fail "Refusing to deploy to /"

for f in "${required[@]}"; do
  [[ -f "$PACKAGE_DIR/$f" ]] || fail "Missing package file: $PACKAGE_DIR/$f"
done

if [[ -f "$PACKAGE_DIR/SHA256SUMS.txt" ]]; then
  echo "Verifying deployment package checksums..."
  (cd "$PACKAGE_DIR" && sha256sum -c SHA256SUMS.txt)
fi

mkdir -p "$BACKUP_DIR"
echo "Backing up current storefront to $BACKUP_DIR"
for f in "${required[@]}"; do
  if [[ -f "$PUBLIC_HTML/$f" ]]; then
    cp -p "$PUBLIC_HTML/$f" "$BACKUP_DIR/$f"
  fi
done

printf '%s\n' "$PUBLIC_HTML" > "$BACKUP_DIR/PUBLIC_HTML_PATH.txt"
printf '%s\n' "$STAMP" > "$BACKUP_DIR/BACKUP_UTC.txt"

STAGE="$PUBLIC_HTML/.mirroriedled-stage-$STAMP"
mkdir -p "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

for f in "${required[@]}"; do
  cp "$PACKAGE_DIR/$f" "$STAGE/$f"
done

node --check "$STAGE/app.js" >/dev/null

for f in "${required[@]}"; do
  mv "$STAGE/$f" "$PUBLIC_HTML/$f.new"
done
for f in "${required[@]}"; do
  mv "$PUBLIC_HTML/$f.new" "$PUBLIC_HTML/$f"
done

chmod 0644 "$PUBLIC_HTML/index.html" "$PUBLIC_HTML/styles.css" "$PUBLIC_HTML/app.js" 2>/dev/null || true

echo "Deployment files installed. Running public verification..."
if command -v curl >/dev/null 2>&1; then
  code="$(curl -L -sS -o /tmp/mirroriedled-home.html -w '%{http_code}' --max-time 20 "$DOMAIN/")"
  [[ "$code" == "200" ]] || fail "Homepage returned HTTP $code. Backup is at $BACKUP_DIR"
  grep -qi 'Mirroried LED' /tmp/mirroriedled-home.html || fail "Homepage response does not contain Mirroried LED. Backup is at $BACKUP_DIR"
else
  echo "curl not installed; skipped public HTTP verification."
fi

echo "DEPLOYMENT SUCCESS"
echo "Backup: $BACKUP_DIR"
echo "Site: $DOMAIN"
