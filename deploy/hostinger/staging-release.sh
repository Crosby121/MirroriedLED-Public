#!/usr/bin/env bash
set -euo pipefail

# Runs through SSH on the server. It never invokes the production deploy tools.
mode="${1:-}"
stage="${2:-}"
release_name="${3:-}"
assets=(index.html styles.css app.js repair.js infinity-mirror.webp stadium-model.webp led-display.webp address-sign.webp)

fail() { echo "Refusing staging release: $*" >&2; exit 1; }

case "$mode" in validate|prepare|activate) ;; *) fail 'unknown operation' ;; esac
[[ "$stage" =~ ^(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*/public_html/MLED_v5_TEST$ ]] || fail 'invalid staging path'
if [[ "$mode" == validate ]]; then
  exit 0
fi
[[ "$release_name" =~ ^\.release-[0-9]+-[0-9]+$ ]] || fail 'invalid release name'

# A text suffix alone cannot protect production when a directory is a symlink.
parent="${stage%/*}"
[[ -d "$parent" && "$(realpath -e -- "$parent")" == "$parent" ]] || fail 'use the existing physical public_html path'
if [[ -e "$stage" || -L "$stage" ]]; then
  [[ -d "$stage" && ! -L "$stage" && "$(realpath -e -- "$stage")" == "$stage" ]] || fail 'staging directory must not be a symlink'
fi
release="$stage/$release_name"

if [[ "$mode" == prepare ]]; then
  mkdir -p -- "$stage"
  # An existing release is refused, including symlinks and interrupted uploads.
  mkdir -m 700 -- "$release" || fail 'release directory already exists'
  echo 'Staging upload directory prepared'
  exit 0
fi

[[ -d "$release" && ! -L "$release" && "$(realpath -e -- "$release")" == "$release" ]] || fail 'invalid release directory'
[[ -f "$release/SHA256SUMS.txt" && ! -L "$release/SHA256SUMS.txt" ]] || fail 'missing checksum manifest'
declare -A seen=()
count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^([a-f0-9]{64})\ \ (index\.html|styles\.css|app\.js|repair\.js|infinity-mirror\.webp|stadium-model\.webp|led-display\.webp|address-sign\.webp)$ ]] || fail 'invalid checksum entry'
  asset="${BASH_REMATCH[2]}"
  [[ -z "${seen[$asset]:-}" ]] || fail 'duplicate checksum entry'
  seen["$asset"]=1
  count=$((count + 1))
done < "$release/SHA256SUMS.txt"
[[ "$count" == "${#assets[@]}" ]] || fail 'checksum manifest must contain all eight assets'

for asset in "${assets[@]}"; do
  [[ -f "$release/$asset" && -s "$release/$asset" && ! -L "$release/$asset" ]] || fail "missing or unsafe uploaded $asset"
  if [[ -e "$stage/$asset" || -L "$stage/$asset" ]]; then
    [[ -f "$stage/$asset" && ! -L "$stage/$asset" ]] || fail "unsafe staging destination for $asset"
  fi
done
(cd "$release" && sha256sum --check --strict --status SHA256SUMS.txt) || fail 'uploaded files failed checksum verification'

# Validate every file before installing any. Only these eight staging assets move.
for asset in "${assets[@]}"; do
  chmod 644 -- "$release/$asset"
  mv -T -- "$release/$asset" "$stage/$asset"
done
rm -- "$release/SHA256SUMS.txt"
rmdir -- "$release"
echo 'Eight storefront files installed in staging; upload checksums verified'
