#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HTML="${PUBLIC_HTML:-$HOME/domains/mirroriedled.com/public_html}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/mirroriedled-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_ROOT/public_html-full-$STAMP.tar.gz"
CHECKSUM="$ARCHIVE.sha256"
INFO="$BACKUP_ROOT/public_html-full-$STAMP.txt"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$PUBLIC_HTML" ]] || fail "PUBLIC_HTML does not exist: $PUBLIC_HTML"
[[ "$PUBLIC_HTML" == *public_html* ]] || fail "Refusing to back up a path that is not public_html: $PUBLIC_HTML"
[[ "$PUBLIC_HTML" != "/" ]] || fail "Refusing to back up /"
command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"

mkdir -p "$BACKUP_ROOT"
PARENT="$(dirname "$PUBLIC_HTML")"
BASE="$(basename "$PUBLIC_HTML")"
TMP="$ARCHIVE.tmp"
rm -f "$TMP"

echo "Creating full public_html backup..."
tar -C "$PARENT" -czpf "$TMP" "$BASE"

# Verify the archive can be read before accepting it as a backup.
tar -tzf "$TMP" >/dev/null
mv "$TMP" "$ARCHIVE"
sha256sum "$ARCHIVE" > "$CHECKSUM"

{
  echo "Mirroried LED full public_html backup"
  echo "Created UTC: $STAMP"
  echo "Source: $PUBLIC_HTML"
  echo "Archive: $ARCHIVE"
  echo "Checksum file: $CHECKSUM"
  echo "Archive bytes: $(wc -c < "$ARCHIVE")"
} > "$INFO"

echo "FULL BACKUP SUCCESS"
echo "Archive: $ARCHIVE"
echo "Checksum: $CHECKSUM"
echo "Info: $INFO"
