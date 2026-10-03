# Mirroried LED Public Storefront — Hostinger Deployment

This guide deploys the static storefront only. It does not modify the Sponsor Portal VPS service.

## Production target

- Domain: `https://mirroriedled.com`
- Hostinger web root: `public_html`
- Static files to deploy: `index.html`, `styles.css`, `app.js`, `repair.js`
- Sponsor Portal target: `https://sponsors.mirroriedled.com/`

## Safety rule

Use the guarded helpers in `deploy/hostinger` to create a verified full-site backup
outside `public_html` and a separate four-file storefront backup before installation.

## Pre-deploy checklist

1. Confirm Storefront CI is green for the exact commit being deployed.
2. Confirm `https://sponsors.mirroriedled.com/` is reachable over HTTPS before exposing Sponsor Login buttons.
3. Correct and verify the staging SSH settings, including the private key and independently verified host key.
4. Confirm the physical website webroot, then deploy to `MLED_v5_TEST` and complete the staging acceptance checks.
5. Keep full-site and storefront backups outside the public webroot, following `deploy/hostinger/README.md`.

## Deploy

1. Download the generated `mirroriedled-storefront` artifact from the matching GitHub Actions run.
2. Extract it locally.
3. Verify the included `SHA256SUMS.txt`.
4. Upload only:
   - `index.html`
   - `styles.css`
   - `app.js`
   - `repair.js`
5. Use the package's guarded `deploy-storefront.sh` with the verified `PUBLIC_HTML` path to install those four files.
6. Do not move or delete unrelated API, portal, WLED bridge, database, configuration, asset, or backup folders.

## Acceptance checks

After upload, verify in a private/incognito browser:

- Home page loads at `https://mirroriedled.com/`
- Mobile navigation opens and closes
- Products section is visible
- Custom Design configurator opens
- Add-to-cart / quote-cart behavior works
- Sponsor Partner Program and Advertising on the Go remain distinct sections
- Sponsor Login opens `https://sponsors.mirroriedled.com/`
- Contact mail links use the intended Mirroried LED mailboxes
- No browser console errors block navigation or cart actions

## Rollback

If the storefront fails acceptance:

1. Stop further changes.
2. Use `rollback-storefront.sh` with the printed storefront backup path to restore all four recorded file states:
   - `index.html`
   - `styles.css`
   - `app.js`
   - `repair.js`
3. Hard-refresh and verify `https://mirroriedled.com/`.
4. Keep the failed deployment files outside production for diagnosis.

Never delete the backup until the new storefront has passed acceptance and remained stable.
