# Isolated website checkout sandbox

The `Install Isolated Checkout Sandbox` workflow prepares the complete reviewed
public allowlist in `public_html/MLED_checkout_TEST`. Its expected URL is
`https://mirroriedled.com/MLED_checkout_TEST/shop/`; a completed install and HTTPS
verification are required before claiming it exists. This is separate from the
legacy eight-file `MLED_v5_TEST` deployment.

The installer refuses existing sandbox directories, symlinks, foreign ownership
and group/world-writable domain or public roots. It preserves production public
files and the existing `mirroriedled-private/customer-portal` configuration/data.
Its own configuration, restricted test key, receipt and database live in
`mirroriedled-private/checkout-sandbox`, outside public_html. The private folder
is 0700 and private files are 0600. Only `rk_test_` credentials are accepted.

The generated copy makes these deployment-only changes:

- The API explicitly selects the sandbox private configuration and fails closed
  if the override cannot be installed; it never falls back to production.
- Server storage and session save files are separate; cookies use the sandbox
  portal path. Browser carts, pending orders, artwork IndexedDB and stadium
  selections use distinct sandbox names.
- HTML has a visible sandbox notice and noindex metadata. The folder disables
  indexes and sends a noindex header where Apache headers are available.
- A private receipt records every generated public-file checksum and exact
  source commit. HTTPS checks compare public assets with this receipt and verify
  the runtime source header, isolated session cookie path and internal PHP denial.

The initial private config has commerce disabled, mode test, no staff, no webhook
secret and false tax/fulfillment confirmation flags. Installing the key does not
enable checkout or establish write permissions, webhook delivery or payment
reconciliation. Premium media and real production release stay disabled.

The workflow reads `MLED_STRIPE_SANDBOX_KEY` and existing main-site Hostinger SSH
settings through GitHub Actions secrets. The production environment supplies
those existing SSH settings only. Private credential transport is removed after
installation; no credential or customer artifact is uploaded. Remote cleanup is
armed only after successful exclusive creation and refuses unsafe paths.

Next, register the deployed sandbox API webhook, store its endpoint-specific
signing secret privately, configure sandbox tax settings/registration and fake
fulfillment terms, then exercise an actual sandbox quoted order. Real merchant
registrations and production terms remain separately required for a live launch.
Do not copy sandbox accounts, payment flags or database files into production.

The installer is intentionally create-only. If verification fails after files
were created, preserve them for inspection and diagnose the failure; rerunning
does not overwrite or delete any test or production records.

## Install the endpoint signing secret

After registering and pausing the webhook in Mirroried Led sandbox, save its
`whsec_` value as Actions secret `MLED_STRIPE_SANDBOX_WEBHOOK_SECRET`. The separate
`Install Sandbox Webhook Secret` workflow reads that value privately, checks its
format, and sends it over the trusted SSH connection through stdin. No secret is
put in a command argument, public file, artifact or log.

The helper recognizes only its own unchanged disabled sandbox configuration.
It rejects unsafe paths/permissions, live API credentials and replacing an
existing different signer. Atomic private credential/config updates preserve all
public assets, production configuration and databases. The PHP runtime confirms
the configured signer matches private storage while checkout, tax and fulfillment
flags stay false. A session HTTPS check independently confirms payments remain
off. The secret format and runtime read do not establish a Stripe-signed delivery;
that remains a separate acceptance step. Stripe delivery remains paused.

The final signer workflow is manual-only with explicit acknowledgement. The
initial branch-scoped bootstrap was removed after the verified installation.

## Prepare a selected test quote

The CLI-only `prepare-sandbox-quote.php` helper accepts a SHA-256 fingerprint of
one owner-selected sandbox order reference. Raw order IDs, names, addresses,
artwork and account records stay in private storage. It validates the isolated
API/config/database paths and requires checkout off, mode test, no persistent
staff roles, a single 12-inch mirror and a saved California delivery address.

It copies the uploaded artwork into a private test proof and invokes the existing
business proof/offer validation with temporary CLI operator scope. It grants no
browser role and never approves on the customer's behalf. The summary states
SANDBOX, $1 product plus test tax, $0 shipping and no fabrication/shipping; the
1–2 day production/transit ranges are artificial acceptance fixtures. Other orders,
public assets and production configuration remain unchanged. Same-quote retries
preserve approval and avoid duplicate proof/offer versions. Existing unrelated
quotes, active checkouts and unsafe paths are rejected. The workflow emits only
non-identifying booleans and test amounts and removes its private helper transport.

Private proof copying uses a verified temporary sibling and atomic publication
under the same process lock. A process-scoped lock serializes retries and releases automatically
after interruption; partial private temporary copies cannot poison the final proof.

The final quote workflow is manual-only and requires a selected order fingerprint
and explicit test-quote acknowledgement. Its one-time push bootstrap was removed
after successful private proof/quote preparation.

## Enable an approved artificial quote

`Enable Approved Sandbox Checkout` requires the selected order fingerprint and
explicit acknowledgement. The helper reads the private database without changing
approval: the current one-dollar artwork-reference proof must already be approved
by its customer, with an unexpired California offer and no checkout records.
Restricted test credentials, the installed endpoint signer, fresh active sandbox
tax settings/registration and artificial fulfillment terms are required.

Only the isolated commerce backend and its private readiness flags are updated.
The original backend is backed up privately using atomic publication under a
process lock; interrupted same-source deployment can resume. The receipt keeps
both the installed base source and the separate checkout patch source/hash.
Production homepage/config hashes must remain identical. Private accounts, roles,
artwork and approved order data are preserved.

HTTPS verification checks the base/checkout source headers, sandbox cookie scope,
internal PHP denial, test checkout capability and disabled production payments.
A harmless self-signed unknown event tests HMAC validation and duplicate delivery;
invalid, stale and tampered signatures must be rejected. This probe makes no
provider calls and does not prove actual Stripe-signed delivery. Resume only the
sandbox provider webhook after these checks, then the customer opens test Checkout.
An actual test-card payment, canonical reconciliation and provider delivery/replay
are still required. Test payments cannot release production work.

The final activation workflow is manual-only; its initial branch/path push
bootstrap is removed after the verified activation. Existing different checkout
patches or checkout records require separate review; this is an initial enable
operation, not a general migration or reconfiguration tool.

Before expanding beyond this artificial card test, handle delayed payment failures
and test their retry/unlock path. Dynamic methods may include delayed payments;
current reconciliation handles successful or expired sessions but does not resolve
`checkout.session.async_payment_failed`. Live launch remains blocked on acceptance.
