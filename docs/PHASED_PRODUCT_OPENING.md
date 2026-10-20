# Infinity Mirror and address-sign public opening

This release makes the root homepage a phased opening notice. Public navigation
leads to `/infinity-builder/`, `/address-builder/` and `/shop/`. The prior Customer
Portal URL redirects to the ordering account. Unopened product requests are
rejected for customers while authorized staff retain the existing workflow.
Premium media endpoints require `premium_enabled=true` or a verified staff role;
the private data and premium implementation are retained.

The owner-approved standard **12×12 mirror is $150.00 before tax and shipping**.
Final quote review confirms the selected configuration, artwork and delivery terms.
Other sizes, options, shipping and turnaround are not priced by this approval.

## Customer journey

1. Configure an Infinity Mirror, including artwork and LED/controller choices,
   or personalize an address sign. The address-sign dimensions are proposed
   design options; the final proof confirms fabrication and outdoor suitability.
2. Create an account or sign in. Save the complete design, engraving originals
   and masks, and delivery address. The two builders share the same local list.
3. The sales team publishes the actual artwork proof and complete product price,
   then confirms shipping to the saved address and production/transit ranges.
   No retail price, material availability or turnaround is invented. The existing
   supplier estimate retains the 20% frame-only rule.
4. The customer reviews the current proof and quote. New mirror quotes collect
   a **50% product deposit before production**, rounded up to cents. Shipping is
   collected with the balance. Stripe shows tax and the actual amount for each
   payment before confirmation; the $150 product example is $75 deposit plus $75
   product balance, with applicable tax and shipping extra. Address signs and
   existing accepted full-payment mirror orders retain their original terms.
5. Payment is recorded only after retrieving the merchant's canonical Checkout
   Session, verifying ownership, mode, proof, immutable terms, line items,
   subtotal, shipping, tax, total and the payment intent. Signed webhooks work
   without a customer returning to the page. The return page requests the same
   reconciliation and never trusts a URL claiming payment succeeded.
6. The existing material reservation, production file, scheduling and QC gates
   remain. A product checkout offer additionally requires a verified **live**
   deposit (or the original full payment) before production release. Test payments cannot authorize production.
   Tracking and actual fulfillment updates appear in the customer's account.
7. For mirrors, production/QC staff publish a photo of the actual finished
   engraving. New staged orders also display the final product/shipping price,
   which sales must authorize if changed. The customer approves both that current
   photo and its final price before paying the balance. A revised review requires
   fresh approval; an active balance attempt locks review changes.
8. **Your custom mirror will ship within three business days after we receive
   both your approval of the actual engraving and your final payment. Delivery
   time begins after shipment.** Monday–Friday excludes standard observed U.S.
   federal holidays, using Pacific calendar dates. The later approval/payment
   date is day zero. QC and all fulfillment gates must pass. The saved ship-by
   date appears in both accounts only once both conditions are met. Production
   time before the photo is ready still needs owner confirmation.

This is a reviewed custom-order flow. **Instant final pricing for every possible
build is not implemented**: incomplete supplier data and fabrication costs need
the team's final quote. A confirmed quote includes selected hardware, engraving,
assembly and fabrication; shipping and turnaround are explicit required terms.

## Private activation

Use the existing private config outside `public_html`; see
`customer-portal/backend/config.example.php`. Set the real merchant's Stripe key
and endpoint signing secret through private hosting configuration or its
environment. Do not paste credentials into chat or commit them.

- `commerce.enabled`: defaults to false.
- `commerce.mode`: `test` for sandbox acceptance, `live` for actual orders.
- `commerce.stripe_secret_key`: `MLED_STRIPE_SECRET_KEY` private environment value.
  Prefer a restricted server key (`rk_test_` in the sandbox or `rk_live_` for
  approved live operation); the legacy `sk_` server-key form remains supported.
  The key environment must match `commerce.mode`; publishable `pk_` keys are rejected.
  Prefix validation does not verify API permissions or actual merchant acceptance.
- `commerce.stripe_webhook_secret`: `MLED_STRIPE_WEBHOOK_SECRET` value.
- `commerce.tax_setup_confirmed`: confirm the actual merchant registrations and
  tax treatment for these physical products, including the general tangible
  product tax code used by checkout.
- `commerce.fulfillment_setup_confirmed`: confirm the real shipping policy,
  production capacity and proof workflow.
- `premium_enabled`: false during this two-product opening.

PHP 8.2+, SQLite, fileinfo, dom and cURL with TLS verification are needed.
Register the merchant webhook at:

`https://mirroriedled.com/customer-portal/backend/api.php?action=commerce-webhook`

Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed` and `checkout.session.expired`. Use the endpoint's own signing secret, rather than
an unrelated CLI secret. Configure customer receipts/invoices in the actual
merchant account. Keys and receipts are not activated by shipping this source.

The public availability notice reflects account and payment configuration. It
labels unavailable or test-mode ordering accurately. Configuration readiness is
not proof that a live merchant charge has passed acceptance.

### Private sandbox credential preflight

Save the website's restricted sandbox key as the GitHub Actions repository secret
`MLED_STRIPE_SANDBOX_KEY`. The `Verify Stripe Sandbox Key` workflow reads only
one sandbox Checkout Session and emits booleans, never the key or provider record.
It refuses unrestricted, publishable and live keys and refuses HTTP redirects.
Its success verifies only key presence and Checkout read access. It does not
install hosting credentials, prove write permissions, configure a webhook or
activate website payments. Start with Checkout Sessions Write and Customers Write;
add a specific dependency only when an actual sandbox API error requires it.
The existing website also creates inline prices/shipping and enables invoice
creation and automatic tax; exercise those paths during isolated app acceptance.
Do not claim tax readiness from this credential preflight.

## Sales operation

Sign in at `/shop/` using an owner-assigned numeric staff account. Open Team.
Publish the current proof and complete product price; publish the separate
**Complete pricing & delivery** form using the customer's saved destination.
Production days are business-day estimates starting after confirmed payment and
final artwork approval; carrier transit begins after shipment. Sales must confirm materials, shipping cost
and production capacity. Any changed address invalidates the shipping offer;
quote/proof revisions invalidate checkout terms. Offer versions are monotonic.
An active checkout locks address/proof/price changes, avoiding a payment for an
outdated design. Repeated checkout calls reuse the same provider session. Provider requests pin
Stripe API version `2026-09-30.endive`, allow dynamic payment methods and persist
a unique integration identifier in the immutable checkout snapshot. A timed-out
retry reuses identical provider parameters and the original idempotency key.
Legacy incomplete snapshots without that identifier require support review.

A completed unpaid Checkout remains locked as processing until canonical expanded
PaymentIntent data proves failure. A matching canceled intent or failed payment
method with zero received/capturable funds marks the attempt failed, records one
customer notice and permits a fresh attempt with a new idempotency key. Unknown,
processing or mismatched results cannot unlock payment. Paid records never regress,
and any review hold blocks another checkout across all attempts. A paid deposit
permits only its legitimate balance stage after current final-price/photo approval.
A paid stage with an unresolved sibling attempt remains on hold; refresh checks
that attempt even if it is older than the paid row. A second paid attempt requires
manual support review and cannot release production or shipping. Subscribe
to failed asynchronous payments as well as success/expiry events.

Cancelled browser checkout can be reopened while its session is valid. Expired
sessions are reconciled before retry. A mismatched paid session is held for
review and cannot trigger another payment or production release. Refunds,
disputes and payment-locked cancellations currently need manual merchant/support
resolution; automatic refund/dispute reconciliation is not part of this release.

## Validation and release state

Local acceptance uses a deterministic provider double and fabricated test data;
it does not prove a real Stripe connection or charge. HTTP tests cover private
accounts, both product configurations, proof approval, shipping terms, ownership,
CSRF, invalid signatures, offer/price locks, retry behavior and canonical payment
amounts. Retained media tests explicitly opt into private premium media.

Use `Deploy Complete Website to Hostinger`, not the legacy eight-file helpers.
The allowlisted full release includes both builders, the ordering portal and
protected `commerce.php`. It preserves existing private configuration and data.
Live verification uses `--require-commerce`: unconfigured customer accounts,
disabled product ordering or test/unavailable payment configuration fail the
launch check and restore the previous public files. This configuration check
does not replace actual merchant payment acceptance.
The separate sponsor VPS cannot deploy this main website. The October 6 verified release passed authenticated SSH preflight and exact-source
HTTPS verification (run 37538235814), resolving the earlier missing-settings
blocker. Recheck those settings at release time; this integration does not
perform or establish a new live deployment.

A live launch additionally needs an actual sandbox Checkout payment and signed
merchant webhook, then the real merchant configuration and confirmed product
quotes/fulfillment terms. This branch does not claim that `mirroriedled.com` is
updated or accepting payments.

Official integration references:

- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/checkout/fulfillment.md?payment-ui=stripe-hosted
- https://docs.stripe.com/webhooks/signature
