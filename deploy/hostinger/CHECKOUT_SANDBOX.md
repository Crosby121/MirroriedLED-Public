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

The recovery patch handles `checkout.session.async_payment_failed` by retrieving
canonical session and expanded PaymentIntent data. Completed unpaid payments stay
locked until verified failure; failed attempts can be retried with a new session.
Actual delayed-payment failure acceptance remains required before live launch.

## Verify a paid test order

`Verify Paid Sandbox Checkout` takes one-way fingerprints of the selected order,
canonical Checkout Session, actual completed event and PaymentIntent. First verify
those records through authenticated Stripe reads: test mode, paid109cents including
9cents tax, successful payment intent, and event delivery success. The server helper
opens only the isolated SQLite database with read-only/query-only settings. It
requires the same paid snapshot, approved artificial proof, matching payment
reference, exactly one payment confirmation, no review entry, and the exact actual
provider event already present in the processed-webhook table. It emits only
booleans and test amounts; identifiers and customer information stay private.

Optional duplicate acceptance self-signs the already-processed canonical event ID
and posts it twice to the fixed sandbox webhook, then rechecks the same invariants.
This tests deduplication after actual provider delivery; it is not a provider resend.
The helper refuses to replay an event that has not already been recorded, so this
probe cannot manufacture the evidence of original Stripe processing. No provider
call or production release is made. The workflow checks unchanged production
homepage/config hashes and removes its private helper transport.

The final payment-verification workflow is manual-only and requires explicit
acknowledgement and all four canonical fingerprints. Its initial branch/path push
bootstrap is removed after verification.

## Update the isolated payment-recovery files

`Update Sandbox Payment Recovery` changes six reviewed files: commerce.php,
business.php, customer-portal/business.js, customer-portal/operations.html,
shop/shop.js and shop/index.html. It verifies the exact current checkout patch, private test config,
selected paid artificial order, source hashes and single confirmation. Before
publishing, the installed restricted sandbox key must successfully read the actual
canonical paid session with expanded PaymentIntent, proving the new read permission.
No provider writes or broadening of key permissions are performed by the helper.

Private atomic backups and a source-bound journal allow same-source interruption
recovery. Files may match only the reviewed original or exact generated replacement;
unknown source or receipt changes are preserved and rejected. The private receipt
records the new PHP and UI hashes and prior patch source. The installed base API
source header is retained; the checkout and business headers identify the new patch. Browser
storage namespaces and sandbox/noindex markers are regenerated, and the UI script
URL changes to avoid retaining the previous code in a browser cache.

After publication, the workflow rechecks the existing paid order and known-event
self-signed duplicate probe, exact public JS/HTML hashes, runtime headers/cookie scope
and unchanged production homepage/config hashes. Private config and order data are
not rewritten. Subscribe the verified sandbox endpoint to async_payment_failed only
after these checks. Production payments remain disabled. A source/payload simulation
does not replace actual delayed-method failure acceptance.

The final recovery updater is manual-only and requires the current installed patch
commit, canonical fingerprints and explicit acknowledgement. Its one-time
branch/path bootstrap is removed after the verified patch.


## Finished engraving approval and dispatch

Owner-confirmed policy: the customer reviews a photo of the **actual engraving on
their mirror**, separate from the digital artwork proof approved before production.
Custom Infinity Mirror orders cannot record shipment or pickup until the owner of
that order approves its latest finished-engraving review. QC must also pass; payment,
material and production-release prerequisites remain in force. Address signs keep
their existing process.

Production or QC staff upload a private PNG/JPEG/WebP photo after build start and
publish it with review notes. The customer opens their order, reviews that version,
and selects **Approve finished engraving**. A new photo review version clears
shipping readiness until the customer approves it. Each version, approving account,
approval timestamp and ship-by date remain in private history. Portal updates are
implemented; email/SMS delivery is not connected.

New mirror quotes collect a **50% product deposit before production**, rounded
up to cents, with shipping deferred to the final balance. Stripe calculates tax
on each payment's actual product/shipping amounts. For a $150 product this is a
$75 product deposit and $75 product balance, plus applicable tax and shipping.
Address signs and pre-existing full-payment offers/snapshots keep their terms.

For staged orders each actual-photo review stores immutable final product and
shipping amounts. Changing quoted amounts requires sales/admin authorization.
The owning customer explicitly approves both that review and its final price
before opening balance checkout. A current unpaid/processing/paid/review balance
locks replacement reviews. Final product price below the paid deposit and positive
remaining totals below the provider minimum require manual support; zero remaining
balance settles without an invented charge. Refunds are not automated.

Owner-approved wording: **Your custom mirror will ship within three business days
after we receive both your approval of the actual engraving and your final payment.
Delivery time begins after shipment.** The later condition's date is day zero;
the next three business dates are counted in America/Los_Angeles, excluding
weekends and standard observed U.S. federal holidays, including adjacent-year
observances and daylight-saving transitions. Holiday reference:
https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/ .
The saved ship-by date is shown only after both conditions are met. This does not
supply the still-unconfirmed production lead time. Late shipments can be recorded
truthfully without changing the original approval or deadline.

A paid deposit does not mean the order is fully paid. Any unresolved sibling of
a paid stage holds production/shipping until canonical reconciliation resolves it;
a second success stays on manual review. Refresh finds unresolved attempts even
when a paid row is newer. Balance payment must match the current accepted final
review and exact immutable stage amounts. Only verified live funds permit actual
production or shipment; test payments never release fulfillment.

New mirror checkout offers disclose these terms. Existing accepted offer history
and creating/paid checkout snapshots are not rewritten; legacy provider retries
retain their original request text. Deterministic provider/HTTP tests exercise
both stages, revised prices, failure/expiry, duplicate success, late events and
holiday readiness. **Actual two-stage merchant checkout acceptance has not been
performed.** The earlier actual $1.09 full-payment test remains evidence only for
that original legacy flow. Do not claim the newer stages are merchant-tested from
schema initialization or preservation of the original order.

After updating the six files, the CLI-only `verify-sandbox-engraving.php` helper
checks exact receipt hashes, private test-only configuration and the selected
approved test order. It initializes the additive review and per-review final-price
tables through the installed constructors, verifies the legacy customer-facing
order remains full-payment with no finished engraving approval or final-price row, and compares every pre-existing table's rows and private config
before committing. It never assigns staff roles, changes a price, publishes a photo,
approves engraving or advances production. The original artificial paid test order
stays unreleased. Keep this helper outside public_html and remove its transport.
