# Customer Portal draft

The Customer Access link now opens a dedicated music/video portal. It includes Free, Premium and Premium+ draft plans, account signup/login, an owner-only media library and a browser LED matrix preview. Prices are unset and payments are off. A new account always has Free limits; Premium is a request for team approval.

## Preview behavior

The Light Studio has two separate actions:

- **Preview on this device** plays a selected local file without uploading or retaining it. The browser uses Web Audio frequency analysis for music-reactive pixels, or samples the current video frame into a 32 × 18 matrix. Playback, pause and seeking use the same media element so the displayed light follows its playback time. Preview brightness affects only the visualization.
- **Save to my library** sends a real authenticated upload to the PHP API. It is available only after private server configuration and sign-in. Saved media is streamed through the owner-checked API, never a public upload directory. Remove requires a second explicit confirmation.

**Play demo** synthesizes a quiet 12-second sample in the browser and drives the music preview from its analyzed audio. Nothing plays automatically. The default matrix is labelled Illustration. Unsupported media produces a visible error.

The page labels physical controller access **Setup required**. This release does not send hardware commands, pair a controller, or claim real LEDs are connected. The installation path remains Chataigne for local show timing and WLED/WLED-MM for the controller. Low-latency music/video output requires the customer's local show computer/bridge; the shared website cannot directly address private LAN controllers.

GitHub Pages is a **frontend preview only**. It does not execute PHP or enable account signup/uploads. The page keeps those operations disabled while the API is unavailable; local playback and the demo remain usable.

## Deployment checkpoint

The live storefront already contains the verified product images. Keep Hostinger Auto-deployment **Off**; its connected `storefront-vnext` branch is stale. Do not use the Sponsor VPS to install this portal.

Build the public release:

```bash
python3 deploy/hostinger/package-customer-portal.py --output /absolute/path/MirroriedLED_Customer_Portal_Draft.zip
```

The ZIP has only the eight current public storefront files and the public Customer Portal code. It has no credentials, working private config, database, customer sessions or uploaded media. Its exact allowlist and checksums are checked during packaging. The public API remains disabled until it finds safe private configuration outside `public_html`.

1. In the website's File Manager, back up the current public storefront files. Upload and extract the ZIP **inside `public_html/MLED_v5_TEST`** to review the layout and local music/video preview first. Files must land directly in that staging directory, with `customer-portal/` beneath it, not inside another ZIP-named folder.
2. Test the staging portal on HTTPS. Account/upload tests require a separate private staging configuration and storage, as described in [CUSTOMER_PORTAL_BACKEND.md](CUSTOMER_PORTAL_BACKEND.md). Do not use a production customer database for testing.
3. After staging is verified, back up the current production files, place `customer-portal/` in `public_html`, and install the updated root `index.html`. The other seven root storefront files are unchanged. Leave existing sponsor/advertiser files and any private customer storage intact.
4. Configure production private storage outside `public_html` and verify real signup, a small music/video upload, private playback and sign-out before accepting customer registrations. Real recurring subscriptions, email verification/recovery and controller pairing remain follow-up work.

The original storefront shell scripts intentionally update their original eight-file allowlist. They do not install or overwrite the Customer Portal or private storage. Use the dedicated portal package for this change.

## Validation

Run the existing release-boundary tests and the portal HTTP integration tests. PHP 8.2+ with `pdo_sqlite` and `fileinfo` is required; the video fixture additionally uses `ffmpeg`.

```bash
node --check customer-portal/portal.js
php -l customer-portal/backend/api.php
php -l customer-portal/backend/portal.php
python3 -m unittest discover -s tests -p 'test_*release.py' -v
python3 -m unittest discover -s tests -p 'test_customer_portal_backend.py' -v
```
