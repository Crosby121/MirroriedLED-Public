# Mirroried LED staging deployment

The `Deploy Storefront to Staging` workflow is manual. It uploads only
`index.html`, `styles.css`, `app.js`, and `repair.js` into `MLED_v5_TEST`.
It does not call the production deployment scripts.

## Before running

1. Merge the repaired workflow into `main` after Storefront CI passes.
   GitHub requires a manually dispatched workflow to exist on the default branch.
2. Verify the physical server path to this website's `public_html` directory.
   The required input is that path followed by `/MLED_v5_TEST`, with no trailing
   slash. A VPS address alone does not establish the website's filesystem path.
3. Confirm these secrets in the repository or its `staging` environment:

| Secret | Value needed |
| --- | --- |
| `STAGING_SSH_HOST` | Verified SSH server hostname or IPv4 address |
| `STAGING_SSH_PORT` | SSH port, from 1 to 65535 |
| `STAGING_SSH_USER` | SSH account with access to the staging directory |
| `STAGING_SSH_PRIVATE_KEY` | Matching private key without a passphrase |
| `STAGING_SSH_KNOWN_HOSTS` | Independently verified SSH host key entry |

The previously recorded VPS address was `45.90.108.202`, user `root`, port `22`.
Those details do not prove that this VPS serves `mirroriedled.com`; confirm that
mapping and the physical webroot before uploading. Do not paste secrets into
commits or workflow inputs.

## Run and verify

In GitHub **Actions → Deploy Storefront to Staging → Run workflow**, select
`main` and enter the verified absolute staging path. The path must end exactly
with `/public_html/MLED_v5_TEST`. Paths with `.` or `..` components, symlinked
directories, and existing upload directories are refused.

If the server mapping has been confirmed, the optional verification URL is
`https://mirroriedled.com/MLED_v5_TEST/` (the `www` host is also accepted).
This is an expected URL shape, not a claim that staging is already deployed.
When provided, the workflow requires HTTP 200 and an exact byte match for all
four uploaded assets. It does not follow redirects. If omitted, the run verifies
server-side checksums only; browser/HTTP acceptance is still outstanding.

Open the verified staging URL and check the mobile navigation, custom-design
dialog, Cancel/Close controls, quote cart, and sponsor/advertising links.
Staging remains quote-based. A staging test does not publish the production site.

## Local checks

```bash
node --check app.js
node --check repair.js
bash -n deploy/hostinger/staging-release.sh
python3 -m unittest discover -s tests -p 'test_staging_release.py' -v
```

Storefront CI also runs actionlint against every workflow. This catches the
invalid `defaults.name` structure that previously passed storefront-only CI.

Each upload uses its own `.release-<run-id>-<attempt>` directory. An interrupted
upload can leave that directory for inspection. Never repurpose a failed upload
directory or point staging to a symlink; rerun with a new attempt after diagnosing
the error. Activation validates every asset before installing any, but moves
the four files separately, so a server/disk failure during installation can leave
a partial staging update. Rerun and complete acceptance checks before relying
on that staging copy.
