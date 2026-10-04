#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HTML="${PUBLIC_HTML:-$HOME/domains/mirroriedled.com/public_html}"
BACKUP_DIR="${1:-}"
DOMAIN="${DOMAIN:-https://mirroriedled.com}"
required=(index.html styles.css app.js repair.js infinity-mirror.webp stadium-model.webp led-display.webp address-sign.webp)

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -n "$BACKUP_DIR" ]] || fail "Usage: $0 /path/to/storefront-backup"
[[ -d "$BACKUP_DIR" ]] || fail "Backup directory not found: $BACKUP_DIR"
[[ -d "$PUBLIC_HTML" ]] || fail "PUBLIC_HTML does not exist: $PUBLIC_HTML"
[[ "$PUBLIC_HTML" == *public_html* ]] || fail "Refusing to restore outside a public_html path: $PUBLIC_HTML"

for f in "${required[@]}"; do
  [[ -f "$BACKUP_DIR/$f" ]] || {
    [[ -f "$BACKUP_DIR/ABSENT_FILES.txt" ]] && grep -Fxq "$f" "$BACKUP_DIR/ABSENT_FILES.txt" || fail "Backup has no recorded state for $f; use the full-site backup to recover it"
  }
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PRE_ROLLBACK="$BACKUP_DIR/pre-rollback-$STAMP"
mkdir -p "$PRE_ROLLBACK"
for f in "${required[@]}"; do
  if [[ -f "$PUBLIC_HTML/$f" ]]; then
    cp -p "$PUBLIC_HTML/$f" "$PRE_ROLLBACK/$f"
  else
    printf '%s\n' "$f" >> "$PRE_ROLLBACK/ABSENT_FILES.txt"
  fi
done

for f in "${required[@]}"; do
  [[ ! -f "$BACKUP_DIR/$f" ]] || cp "$BACKUP_DIR/$f" "$PUBLIC_HTML/$f.restore"
done
for f in "${required[@]}"; do
  if [[ -f "$BACKUP_DIR/$f" ]]; then
    mv "$PUBLIC_HTML/$f.restore" "$PUBLIC_HTML/$f"
    chmod 0644 "$PUBLIC_HTML/$f"
  else
    rm -f -- "$PUBLIC_HTML/$f"
  fi
done

if command -v curl >/dev/null 2>&1; then
  code="$(curl -L -sS -o /tmp/mirroriedled-home-rollback.html -w '%{http_code}' --max-time 20 "$DOMAIN/")"
  [[ "$code" == "200" ]] || fail "Rollback files restored, but homepage returned HTTP $code"
fi

echo "ROLLBACK SUCCESS"
echo "Restored from: $BACKUP_DIR"
echo "Pre-rollback copy: $PRE_ROLLBACK"
