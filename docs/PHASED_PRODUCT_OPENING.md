# Infinity Mirror and address-sign public opening

This release makes the root homepage a phased opening notice. Public navigation
leads to `/infinity-builder/`, `/address-builder/` and `/shop/`. The prior Customer
Portal URL redirects to the ordering account. Unopened product requests are
rejected for customers while authorized staff retain the existing workflow.
Premium media endpoints require `premium_enabled=true` or a verified staff role;
the private data and premium implementation are retained.

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
4. The customer reviews the current proof and quote. Secure Stripe checkout shows
   the final tax and total before a card payment. Account pages show product plus
   shipping as a subtotal and label tax separately until checkout.
5. Payment is recorded only after retrieving the merchant's canonical Checkout
   Session, verifying ownership, mode, proof, immutable terms, line items,
   subtotal, shipping, tax, total and the payment intent. Signed webhooks work
   without a customer returning to the page. The return page requests the same
   reconciliation and never trusts a URL claiming payment succeeded.
6. The existing material reservation, production file, scheduling and QC gates
   remain. A product checkout offer additionally requires a verified **live**
   payment before production release. Test payments cannot authorize production.
   Tracking and actual fulfillment updates appear in the customer's account.

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
- `commerce.stripe_secret_key`: `MLED_STRIPE_SECRET_KEY` environment value.
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

Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`
and `checkout.session.expired`. Use the endpoint's own signing secret, rather than
an unrelated CLI secret. Configure customer receipts/invoices in the actual
merchant account. Keys and receipts are not activated by shipping this source.

The public availability notice reflects account and payment configuration. It
labels unavailable or test-mode ordering accurately. Configuration readiness is
not proof that a live merchant charge has passed acceptance.

## Sales operation

Sign in at `/shop/` using an owner-assigned numeric staff account. Open Team.
Publish the current proof and complete product price; publish the separate
**Complete pricing & delivery** form using the customer's saved destination.
Production/transit days are business-day estimates starting after confirmed
payment and final artwork approval. Sales must confirm materials, shipping cost
and production capacity. Any changed address invalidates the shipping offer;
quote/proof revisions invalidate checkout terms. Offer versions are monotonic.
An active checkout locks address/proof/price changes, avoiding a payment for an
outdated design. Repeated checkout calls reuse the same provider session.

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
The separate sponsor VPS cannot deploy this main website. The previously observed
missing `HOSTINGER_SSH_PRIVATE_KEY` and `HOSTINGER_SSH_KNOWN_HOSTS` remain a hosting
blocker until resolved and freshly verified.

A live launch additionally needs an actual sandbox Checkout payment and signed
merchant webhook, then the real merchant configuration and confirmed product
quotes/fulfillment terms. This branch does not claim that `mirroriedled.com` is
updated or accepting payments.

Official integration references:

- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/checkout/fulfillment.md?payment-ui=stripe-hosted
- https://docs.stripe.com/webhooks/signature
