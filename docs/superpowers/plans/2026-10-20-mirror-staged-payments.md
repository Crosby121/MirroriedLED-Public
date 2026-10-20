# Mirror Staged Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect the approved 50% mirror deposit, confirm final price with the
actual engraving approval, collect the balance, then start the dispatch clock.

**Architecture:** Extend immutable checkout snapshots with deposit/balance stages.
Keep legacy snapshots unchanged; add final-price rows keyed by engraving review.
The existing canonical reconciliation remains the sole authority for paid money.

**Tech Stack:** PHP 8.2+, SQLite/PDO, browser JavaScript, Python HTTP tests.

**Spec:** docs/superpowers/specs/2026-10-20-mirror-staged-payments.md

## Global Constraints

- 50% product deposit, rounded up to cents; shipping collected with the balance.
- USD; Stripe computes tax on each payment's actual partial product/shipping amount.
- Only verified live payments permit production/shipping; sandbox cannot fabricate.
- Final engraving AND final price require owner approval; no automatic price increase.
- Three business days after BOTH approval and final payment, Pacific timezone.
- Existing immutable snapshots, quotes, paid records and private files remain unchanged.
- Only isolated sandbox deployment; no live activation or automatic refund policy.

## Review Focus

- Paid deposit masks a processing balance: refresh and UI must select balance state.
- Failed/expired balance becomes paid after a new photo: hold for review, never ship.
- Odd-cent quote or zero/small remaining total: exact sums, no invented overcharge.
- Approval and balance webhook race: transactionally use the later verified timestamp.
- Cross-year observed holiday and DST: count calendar dates, not 72-hour intervals.

### Task 1: Staged checkout and final-price records

**Files:** customer-portal/backend/commerce.php; tests/test_commerce_backend.py;
tests/test_staged_payments_backend.py (new focused acceptance fixture).
**Interfaces:** CommercePortal::paymentSummary(PDO,string): ?array exposes deposit,
final amounts/current review, balance state and readiness. Existing publicTerms
adds installments without changing legacy payment fields. New snapshots have
paymentStage, originalProductCents and the immutable stage product/shipping amount.

- [ ] Add failing HTTP/CLI canonical-provider tests for the $150/$75 split, taxes,
  duplicate/retry/processing protection, owner/stage identity and old snapshots.
- [ ] Run the focused tests and observe missing behavior failures.
- [ ] Implement the additive final-price table, staged selection, checkout amounts
  and canonical payment validation while preserving legacy request parameters.
- [ ] Assert final offer/price owner approval, stale balance mismatch/review and
  final-price below deposit, zero/subminimum balance and rounding boundaries.
- [ ] Run commerce and stage tests; publish a reviewed coherent source checkpoint.

### Task 2: Actual engraving, readiness and holiday dates

**Files:** customer-portal/backend/business.php; tests/test_business_backend.py;
tests/test_staged_payments_backend.py.
**Interfaces:** BusinessPortal engraving review publishes final price by review ID.
Owner approval also accepts final price. CommercePortal::paymentSummary returns
shippingReadyAt only for a settled current review. engravingShipBy(int) excludes
weekends and standard observed U.S. federal holidays.

- [ ] Add failing tests for no shipping before BOTH approval and full settlement,
  price/photo revision locks, live/test boundary and approval/webhook ordering.
- [ ] Implement transactional final-price capture/approval, deposit production gate
  and shipping balance gate; save deadline only once readiness is established.
- [ ] Add weekend, observed holiday/year boundary and Pacific DST assertions.
- [ ] Run business, commerce and stage suites and independently review money gates.

### Task 3: Customer/team interaction and isolated deployment

**Files:** shop/shop.js,index.html; customer-portal/business.js,operations.html;
deploy/hostinger/update-sandbox-recovery.py,verify-sandbox-engraving.php;
.github/workflows/update-sandbox-recovery.yml; existing deployment tests and docs.

- [ ] Show separate deposit, accepted final price, balance/tax and status. Bind the
  final-price acceptance to the existing photo approval and current order revision.
- [ ] Add final price/shipping inputs only for staged mirror photo reviews. Explain
  the two payment stages and holiday-aware dispatch rule before each acceptance.
- [ ] Extend preservation verification for new additive schema; retain original
  paid full-payment artificial order and avoid creating any customer approval.
- [ ] Run all Python tests, JS tests/syntax, PHP lint, actionlint and work validation.
- [ ] Obtain independent review, publish source, run the guarded isolated updater,
  verify exact hashes/headers/private records, restore manual-only workflow.
- [ ] Publish verified handoff with remaining production/live acceptance gates.
