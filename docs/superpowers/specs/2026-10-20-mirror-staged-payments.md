# Mirror deposit, final price and balance

Owner-approved requirements recovered from the October 19 continuation:
50% deposit before production; actual engraving and final product/shipping price
approved by the customer; remaining balance before shipment. Dispatch within three
business days after BOTH actual engraving approval and final payment. Business days
are Monday–Friday excluding holidays. No production duration is yet confirmed.

Extend the current PHP/SQLite Checkout Sessions flow. New mirror offers default to
50% of the quoted product price (rounded up to cents), with tax on the deposit
calculated by Stripe. Shipping and the remaining product amount, plus applicable
tax, are collected at the final payment. State this allocation before payment.
For the $150 product example: $75 product deposit, then $75 product balance plus
quoted shipping; checkout shows applicable tax separately at each payment.
Address signs retain their existing full-payment process. Existing accepted offers,
creating checkout requests, paid orders and tax/payment history remain unchanged.

Use the existing commerce_checkouts ledger and immutable per-attempt snapshots.
New snapshots identify deposit or balance. Legacy snapshots without a stage retain
their original behavior and provider parameters. Only a canonically verified paid
live deposit can release a new staged order to production. Test payments never
release production. Payment processing/review blocks retries and price/photo
changes; paid/review full legacy payments continue blocking duplicate payments.

Production/QC staff attach final product and shipping amounts to the actual-photo
review. Persist those amounts in a new additive commerce_engraving_prices table,
keyed by review ID. Approval explicitly accepts the current photo and displayed
final price, including any increase. It never changes the initial proof/quote or
paid deposit. A new photo/price requires new customer approval. Any active,
processing, paid or review balance payment locks the final photo/price; resolving
such payments needs support before revision. Never silently charge a changed price.
A final price below already-paid product value requires manual refund review.
A zero balance can settle from the verified deposit and customer approval without
creating a fake payment. A positive remaining amount below Stripe's USD minimum
requires manual review instead of rounding up the charge.

An order exposes original quote, paid deposit/tax, proposed/approved final total,
remaining product/shipping subtotal, current balance status and ship-by date.
A deposit does not display as a fully paid order. The balance button appears only
after the owner approves the current final engraving/price. Refresh selects the
current balance attempt rather than being masked by the paid deposit. Success
pages never prove payment; canonical retrieval and signed webhooks remain required.

For staged mirrors the ship-by date remains unset until both approval and full
settlement are verified. Then save three business days after the later timestamp
in America/Los_Angeles. Exclude standard nationally observed U.S. federal holidays;
this is the explicit implementation assumption for the otherwise unspecified
holiday calendar. The published OPM calendar is the source for standard observed
holidays: https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/ .
Do not import federal-only one-off agency closures or regional inauguration days.
Previously stored legacy deadlines are not rewritten. A revised engraving cannot
reuse a prior approval. QC is still required, and overdue shipment records remain
recordable without falsifying approval/payment dates.

No live merchant activation, real payment, real fabrication, staff assignment,
email notification, automatic refund or cancellation-fee policy is authorized by
this change. Keep the original paid artificial sandbox order and every private
record/config unchanged. Deploy reviewed source only to the existing isolated test
shop using the guarded update workflow, with a fresh schema/row-preservation audit.
