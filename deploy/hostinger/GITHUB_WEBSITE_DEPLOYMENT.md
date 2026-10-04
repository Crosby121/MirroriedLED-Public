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

The production environment uses these GitHub Actions secrets from the actual
Hostinger **website hosting** account:

| Secret | Required value |
| --- | --- |
| `HOSTINGER_SSH_HOST` | Website hosting SSH server, not the sponsor VPS |
| `HOSTINGER_SSH_PORT` | Website hosting SSH port |
| `HOSTINGER_SSH_USER` | Website hosting username, in `u` plus digits form |
| `HOSTINGER_SSH_PRIVATE_KEY` | Matching unattended deployment private key |
| `HOSTINGER_SSH_KNOWN_HOSTS` | Independently verified website hosting SSH host key |
| `HOSTINGER_PUBLIC_HTML` | `/home/<website-user>/domains/mirroriedled.com/public_html` |

The workflow does not create keys, change Hostinger access, read secret values,
reuse the sponsor VPS credentials or disable SSH host-key verification.
Missing settings fail before any upload or website modification.
Python 3.8+ and PHP 8.2+ with `pdo_sqlite`, `fileinfo` and `dom` are checked on
the destination before installation. The remotely installed homepage must
match the current live domain's checksum, preventing installation on a
different host even when a similarly named directory exists.

## Installation and verification

Only the 19 files in the packager's public allowlist are installed. Release
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
python3 website-release.py rollback \
  --webroot /home/WEBSITE_USER/domains/mirroriedled.com/public_html \
  --receipt /PRIVATE_BACKUP_DIRECTORY/receipt.json
```

Use the actual website username and the matching retained backup directory.
Rollback restores both prior contents and the original absence of files. It
does not restore or delete private customer data or replace the full webroot.
