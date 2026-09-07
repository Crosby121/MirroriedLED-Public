# Mirroried LED Hostinger Storefront Deployment

This folder contains guarded deployment tools for the public storefront at `mirroriedled.com`.

## Safety boundary

These scripts only replace:
- `index.html`
- `styles.css`
- `app.js`

They do not delete or replace the rest of `public_html`.

The deploy script creates a timestamped backup before changing any live file.

## Default Hostinger path

The scripts default to:

```bash
$HOME/domains/mirroriedled.com/public_html
```

If your account uses a different path, set it explicitly:

```bash
export PUBLIC_HTML=/actual/path/to/public_html
```

## Deploy

Upload/extract the generated storefront package to a private working folder, not directly into `public_html`.

Then run:

```bash
chmod +x deploy-storefront.sh rollback-storefront.sh verify-storefront.sh
./deploy-storefront.sh /path/to/extracted/storefront-package
```

The deploy script:
1. verifies required files
2. validates package SHA-256 checksums when present
3. backs up the current live storefront
4. checks JavaScript syntax
5. stages the new files
6. installs only the three storefront files
7. verifies the public homepage
8. prints the exact backup location

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

## Roll back

If the deployment has a problem, use the backup path printed by the deploy script:

```bash
./rollback-storefront.sh /path/to/mirroriedled-backups/storefront-YYYYMMDDTHHMMSSZ
```

Rollback itself creates a pre-rollback copy before restoring the previous storefront.

## Do not

- Do not delete the entire `public_html` folder.
- Do not overwrite unrelated API, portal, database, bridge, or configuration folders.
- Do not upload passwords, API keys, `.env` files, or database credentials with the public storefront.
- Do not redirect the root site to the Sponsor Portal. The Sponsor Portal remains a separate service at `sponsors.mirroriedled.com`.
