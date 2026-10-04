# Automated business website deployment

Use the `MirroriedLED_Automated_Business_Website.zip` created by the dedicated customer-portal packager. It contains the eight current storefront assets and eleven public portal/operations assets. Do not upload the selected automation archives or extracted legacy PHP/SQL modules into `public_html`.

This change is based on the current `main` storefront plus the Customer Portal draft in PR #6. Both sets of public files must be present together. The historical eight-file shell deployment tools do not install the portal and are not the installer for this release.

## Stage the public files

1. Keep the existing Hostinger Auto-deployment setting off. Its historical `storefront-vnext` connection is not the release source.
2. Back up the existing public files. Extract the public ZIP into the site's test directory with `index.html` at that directory root and `customer-portal/` directly beneath it. Preserve unrelated sponsor/advertiser files and all existing private storage.
3. Review the storefront, mobile layouts and local music/video preview. Until private setup is complete, account and build forms clearly remain unavailable.
4. Configure an isolated staging account database/storage outside the site's actual document root. Set `MLED_PORTAL_CONFIG` to that private config path when the host supports environment settings; otherwise use the documented default private path from `CUSTOMER_PORTAL_BACKEND.md`. Never test against production customer storage.

## Enable private records

PHP 8.2+ needs `pdo_sqlite`, `fileinfo` and `dom`. Retain the original private account configuration, plans, exact HTTPS origin, session limits and storage path. Add:

```php
'business_enabled' => true,
'staff_users' => [],
```

Create and verify the owner account, find its exact numeric user ID in the private account database, then assign that ID the `admin` role in private config. Do not infer IDs, assign a role to an unverified email or expose a staff role selector in signup. Other approved IDs may receive `sales`, `inventory`, `production`, `qc`, `fulfillment` or `support` roles.

The `business_*` tables are created idempotently in the same private SQLite database on the first authenticated business request. Existing users/media remain intact. Artwork uses a separate private `business-files/` directory. Back up the whole private storage directory together with the database using an SQLite-aware backup or a paused service; protect the backup outside the web root.

Verify a real small artwork upload, current proof approval, stock reservation, recorded shop handoff, QC hold/pass and support reply in staging. Check that another account cannot read the files/order and that sign-out removes the displayed records. External payments, email/SMS, automated shipping, marketing and hardware remain unconnected and must not be advertised as active.

## Install the verified public release

After the existing launch approval boundary is satisfied, back up the production public storefront and existing `customer-portal/`, install the allowlisted public release, and use production's private configuration/storage. Do not copy staging accounts or edit the private database to bypass a workflow gate. Keep the original public backup for rollback; rolling back public files must not delete customer records or uploaded artwork/media.

This repository update does not activate Hostinger production. It contains the tested source and deployment package.
