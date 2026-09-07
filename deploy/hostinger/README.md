# Mirroried LED Hostinger Storefront Deployment

This folder contains guarded deployment tools for the public storefront at `mirroriedled.com`.

## Safety boundary

The deployment replaces only:
- `index.html`
- `styles.css`
- `app.js`

It does not delete or replace the rest of `public_html`.

Before any live file is changed, the deployment now creates **two backups**:
1. a verified compressed archive of the **entire `public_html` directory**
2. a lightweight copy of the three storefront files for fast rollback

## Default Hostinger path

The scripts default to:

```bash
$HOME/domains/mirroriedled.com/public_html
```

If your account uses a different path, set it explicitly:

```bash
export PUBLIC_HTML=/actual/path/to/public_html
```

## Full backup only

You can create the complete safety backup without deploying anything:

```bash
chmod +x backup-public-html.sh
./backup-public-html.sh
```

The backup is saved outside the web root under:

```bash
$HOME/mirroriedled-backups/public_html-full-YYYYMMDDTHHMMSSZ.tar.gz
```

A SHA-256 checksum and metadata file are created next to the archive. The script verifies that the archive can be read before reporting success.

## Deploy

Upload/extract the generated storefront package to a private working folder, not directly into `public_html`.

Then run:

```bash
chmod +x backup-public-html.sh deploy-storefront.sh rollback-storefront.sh verify-storefront.sh
./deploy-storefront.sh /path/to/extracted/storefront-package
```

The deploy script:
1. verifies required package files
2. validates package SHA-256 checksums when present
3. creates and verifies a **full `public_html` archive**
4. creates a storefront-only fast rollback backup
5. checks JavaScript syntax
6. stages the new files
7. installs only the three storefront files
8. verifies the public homepage
9. prints the backup locations

## Verify again

```bash
./verify-storefront.sh
```

This verifies:
- public homepage returns HTTP 200
- `Mirroried LED` branding exists
- `Advertising on the Go` exists
- `Sponsor Partner Program` exists
- Sponsor Portal link exists
- sponsor subdomain is reachable

## Fast rollback

If the storefront deployment has a problem, use the storefront backup path printed by the deploy script:

```bash
./rollback-storefront.sh /path/to/mirroriedled-backups/storefront-YYYYMMDDTHHMMSSZ
```

Rollback itself creates a pre-rollback copy before restoring the previous storefront files.

## Full-site disaster recovery

The `public_html-full-*.tar.gz` archive is the complete pre-deployment site backup. Keep it intact. A full-site restore is intentionally not performed automatically because replacing the entire web root is destructive; use it only if the targeted rollback is insufficient.

## Do not

- Do not delete the entire `public_html` folder during a normal storefront deployment.
- Do not overwrite unrelated API, portal, database, bridge, or configuration folders.
- Do not upload passwords, API keys, `.env` files, or database credentials with the public storefront.
- Do not redirect the root site to the Sponsor Portal. The Sponsor Portal remains a separate service at `sponsors.mirroriedled.com`.
