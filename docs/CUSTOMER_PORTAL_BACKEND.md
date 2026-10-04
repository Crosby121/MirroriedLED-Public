# Customer Portal private server setup

The API implements real password accounts and owner-only music/video storage on PHP 8.2+ with `pdo_sqlite` and `fileinfo`. All three subscription plans are drafts. Payments are off. A customer's requested plan is saved separately from their effective entitlement; every new account receives **Free** limits. No email verification, password reset, payment processor, hardware pairing or live controller connection is implemented in this release.

## Hostinger layout

Upload the public `customer-portal/` folder to the existing website. Place the working configuration and every private file **next to `public_html`, outside the web document root**:

```text
domains/mirroriedled.com/
  public_html/customer-portal/
    index.html
    portal.css
    portal.js
    backend/api.php
    backend/portal.php
    backend/.htaccess
    backend/config.example.php
  mirroriedled-private/customer-portal/
    config.php
    storage/
      portal.sqlite
      media/
      sessions/
```

1. Copy `backend/config.example.php` to `mirroriedled-private/customer-portal/config.php` using File Manager. Do not rename the public example to a working config inside `public_html`.
2. Keep `'storage_path' => __DIR__ . '/storage'`, set the exact HTTPS website origin and edit the draft limits as needed. Leave `allow_insecure_localhost` false on hosting.
3. Set private directories to owner access only (`0700`) and config/data files to `0600`. The API creates its private storage directories and database. The hosting PHP user needs access to the private directory.
4. Use PHP 8.2 or newer with `pdo_sqlite` and `fileinfo`, HTTPS and writable private storage. In PHP settings, set `upload_max_filesize` to at least `128M` and `post_max_size` to at least `130M`; the application then enforces the configured per-file limits (64 MiB audio and 128 MiB video by default). Additional hosting/request limits may be lower.
5. Open `https://mirroriedled.com/customer-portal/backend/api.php?action=session`. `configured:true` confirms the private setup initialized. Check sign-up, a small upload, playback, deletion and sign-out on the HTTPS site before accepting customer registrations.

The default config path is `dirname(DOCUMENT_ROOT) + /mirroriedled-private/customer-portal/config.php`. A server administrator can override it using the **server environment variable** `MLED_PORTAL_CONFIG`; the alternative must still be outside the document root. The API refuses public config/storage, storage symlinks into the public root, and a symlinked database. Without safe private configuration, the public session endpoint reports `configured:false`; account, library and upload actions return 503. GitHub Pages cannot execute this PHP API.

For `/MLED_v5_TEST/customer-portal/` staging, session cookies automatically use `/MLED_v5_TEST/customer-portal/`; production cookies use `/customer-portal/`. Both locations otherwise discover the same default private configuration because they have the same document root. Before staging account/upload testing, have the administrator set a separate `MLED_PORTAL_CONFIG` for the staging location pointing to a private staging config/storage directory. Do not test account creation against an existing production customer database.

## Draft limits and entitlement

| Plan | Songs | Videos | Total private storage |
| --- | ---: | ---: | ---: |
| Free | 3 | 1 | 256 MiB |
| Premium | 25 | 5 | 2 GiB |
| Premium+ | 100 | 20 | 8 GiB |

Edit `plans` in the private config to change limits. A trusted administrator may update a user's `effective_plan` in the private SQLite `users` table to `free`, `premium` or `premium-plus`. There is no public endpoint for changing entitlements. Requested plans and displayed draft limits never activate billing or paid access. Quotas are checked inside an immediate SQLite transaction; deletion releases count and storage quotas.

## API contract

All API requests use `backend/api.php?action=...`. Responses are JSON `{ok:true,...}` or `{ok:false,error:"human-readable message"}`, except successful media playback. Private JSON actions accept `Content-Type: application/json`. Every POST requires the current `csrf` token returned by `session`, sign-up, login or logout. A present `Origin` header must match the configured website origin. No cross-origin API access is enabled.

| Action | Method | Input / result |
| --- | --- | --- |
| `session` | GET | `{configured,authenticated,user,csrf,plans,status,capabilities}`; `csrf:null` when unconfigured. |
| `signup` | POST JSON | `{name,email,password,requestedPlan,csrf}`; real account creation returns 201 and a new session. Password length: 12–72 bytes. |
| `login` | POST JSON | `{email,password,csrf}`; authenticated session with a rotated session ID and CSRF token. |
| `logout` | POST JSON | `{csrf}`; destroys the old session ID, returns an unsigned session with a new token. |
| `library` | GET | `{items,usage:{songs,videos,bytes},limits:{songs,videos,bytes}}` for the signed-in owner. |
| `upload` | POST multipart | Fields `csrf` and `file`; returns 201 `{item,usage,limits}`. |
| `delete` | POST JSON | `{id,csrf}`; deletes only the signed-in owner's media. |
| `media&id=…` | GET | Owner-only media bytes; single byte ranges return 206, invalid ranges 416. |

`user` is `{id,name,email,requestedPlan,effectivePlan}`. `plans` is `[{id,name,songs,videos,price:null,draft:true}]`. `capabilities` includes `{signup,upload,hardwareSync:false,payments:false,maxFileBytes:{audio,video}}`. A media item is `{id,name,kind,mime,bytes,url}`; the URL is relative to the portal page (`backend/api.php?action=media&id=…`). A missing owner item and an item belonging to another customer both return 404.

Uploads accept MP3, WAV and audio OGG, plus MP4 and WebM video. The server inspects file content using `finfo`, checks MIME/extension agreement and container headers, ignores the client-declared MIME, stores random filenames without public paths, and serves only the verified media MIME with `nosniff` and `no-store`. Executable/HTML/SVG file extensions, disguised executable filenames, empty files and oversized files are rejected. The customer's browser preview uses these authenticated media URLs; it does not indicate a connected WLED device.

Sessions use a dedicated private directory, cookie-only strict session IDs, HttpOnly cookies, `SameSite=Strict` and HTTPS Secure cookies. Session IDs and CSRF tokens rotate after authentication and sign-out. The default idle timeout is two hours and the maximum signed-in lifetime is twelve hours. Passwords use PHP `password_hash`/`password_verify`; login attempts are transactionally rate limited per account and IP. HTTPS is mandatory outside explicitly enabled loopback-only development.

## Verification

```bash
php -l customer-portal/backend/api.php
php -l customer-portal/backend/portal.php
php -l customer-portal/backend/config.example.php
python3 -m unittest discover -s tests -p 'test_customer_portal_backend.py' -v
```

The HTTP integration suite starts an isolated PHP server with a private temporary database and tests unconfigured/unsafe setup, CSRF, origin checks, session rotation, free entitlements, password hashing, trusted media detection, private ownership, ranges, sign-out, quotas and throttling. It needs PHP with the two extensions; the optional real-video fixture test additionally uses `ffmpeg`. Tests do not send email, take payment, connect hardware or alter the deployed site.
