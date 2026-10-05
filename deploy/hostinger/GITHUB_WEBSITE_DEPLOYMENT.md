# Complete website deployment through GitHub

The `Deploy Complete Website to Hostinger` workflow installs the full public
storefront, Customer Portal and team operations release. It runs after an
allowlisted website change reaches `main`, or from its manual Actions trigger.
It validates the exact triggering commit and never installs a moving branch.

The saved `STAGING_SSH_*` connection is separate: its latest successful preflight
found the sponsor VPS's Nginx site at `/var/www/sponsors.mirroriedled.com` and no
main-domain `public_html`. Those credentials cannot deploy the main website.
The existing staging workflow remains limited to its test directory.

## Main website hosting connection

The main website connection supplied by the owner on October 4, 2026 is saved
in `deploy/hostinger/main-website.json`:

```bash
ssh -p 65002 u655491421@82.180.171.18
```

The expected webroot is
`/home/u655491421/domains/mirroriedled.com/public_html`. The deployment still
checks that directory on the server before uploading anything.

Only these two GitHub Actions secrets are required from the actual Hostinger
**website hosting** account:

| Secret | Required value |
| --- | --- |
| `HOSTINGER_SSH_PRIVATE_KEY` | Matching unattended deployment private key |
| `HOSTINGER_SSH_KNOWN_HOSTS` | Independently verified website hosting SSH host key |

Optional `HOSTINGER_SSH_HOST`, `HOSTINGER_SSH_PORT`, `HOSTINGER_SSH_USER` and
`HOSTINGER_PUBLIC_HTML` secrets override the saved non-secret connection
settings. Keep them separate from the sponsor VPS credentials.

`Check Main Hostinger Connection` checks HTTPS and reads candidate SSH server
public keys from a GitHub runner. It does not use credentials, authenticate,
upload website files or automatically trust the returned keys. A successful
connection check alone does not establish authenticated SSH access.

The workflow does not create keys, change Hostinger access, read secret values,
reuse the sponsor VPS credentials or disable SSH host-key verification.
Missing settings fail before any upload or website modification.
Python 3.8+ and PHP 8.2+ with `pdo_sqlite`, `fileinfo` and `dom` are checked on
the destination before installation. The profile selects the verified
`/opt/alt/python311/bin/python3` (Python 3.11) for remote preflight, installation
and rollback, because the hosting account default `python3` is 3.6.8. Runner-local
packaging and HTTP verification continue to use the runner Python. The remotely installed homepage must
match the current live domain's checksum, preventing installation on a
different host even when a similarly named directory exists.

## Installation and verification

Only the 29 files in the packager's public allowlist are installed, including
the Infinity Mirror builder and its private artwork service. Release
archives, receipts and full-site backups remain outside `public_html` with
private permissions. The complete backup is verified before a live file is
changed. Access rules are installed first and the homepage last.

Existing bridge services, unrelated files and private account/media/artwork
storage remain intact. Account and team features retain the server's existing
configuration; public installation does not enable billing, email delivery,
machine operation or live WLED playback.

The workflow compares all live HTML, JavaScript, CSS and image assets with the
exact commit, including the root homepage. It also checks the portal status API
and denies direct access to internal PHP/configuration files. An unconfigured
portal is reported explicitly; this release can still display its private setup
status and local preview. Refer to `CUSTOMER_PORTAL_BACKEND.md` for activation.

Installation errors restore the prior allowlisted files. Failed HTTPS checks
also trigger rollback and leave the Actions run failed. A successful packaging
job or GitHub Pages deployment alone is not evidence of Hostinger deployment.

## Retained rollback

The private backup contains `receipt.json`, `metadata.json`, the prior public
files and a verified full-site archive. The same release helper can restore
the prior public files using that retained receipt:

```bash
/opt/alt/python311/bin/python3 website-release.py rollback \
  --webroot /home/WEBSITE_USER/domains/mirroriedled.com/public_html \
  --receipt /PRIVATE_BACKUP_DIRECTORY/receipt.json
```

Use the actual website username and the matching retained backup directory.
Rollback restores both prior contents and the original absence of files. It
does not restore or delete private customer data or replace the full webroot.
