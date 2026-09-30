# Mirroried LED Public Storefront — Hostinger Deployment

This guide deploys the static storefront only. It does not modify the Sponsor Portal VPS service.

## Production target

- Domain: `https://mirroriedled.com`
- Hostinger web root: `public_html`
- Static files to deploy: `index.html`, `styles.css`, `app.js`
- Sponsor Portal target: `https://sponsors.mirroriedled.com/`

## Safety rule

Do not delete or overwrite the current production files until a backup of the existing `public_html/index.html`, `public_html/styles.css`, and `public_html/app.js` has been created and verified.

## Pre-deploy checklist

1. Confirm Storefront CI is green for the exact commit being deployed.
2. Confirm `https://sponsors.mirroriedled.com/` is reachable over HTTPS before exposing Sponsor Login buttons.
3. In Hostinger File Manager, create a timestamped backup folder under `public_html/_backups/`, for example `public_html/_backups/storefront-2026-09-07/`.
4. Copy the current production `index.html`, `styles.css`, and `app.js` into that backup folder.
5. Download or otherwise preserve a second copy outside `public_html` when practical.

## Deploy

1. Download the generated `mirroriedled-storefront` artifact from the matching GitHub Actions run.
2. Extract it locally.
3. Verify the included `SHA256SUMS.txt`.
4. Upload only:
   - `index.html`
   - `styles.css`
   - `app.js`
5. Place those three files directly in Hostinger `public_html`.
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
2. Copy the three backed-up production files from the timestamped backup folder back into `public_html`:
   - `index.html`
   - `styles.css`
   - `app.js`
3. Hard-refresh and verify `https://mirroriedled.com/`.
4. Keep the failed deployment files outside production for diagnosis.

Never delete the backup until the new storefront has passed acceptance and remained stable.