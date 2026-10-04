# Automated business integration

The public storefront previously kept custom requests in a browser cart and prepared an email. Its current Customer Portal draft added private media accounts, but it did not save build requests, artwork proofs, stock reservations, production progress or support conversations. The selected **automated bussiness** folder contains 267 files: 255 historical automation archives with 5,709 members, plus 12 supporting files. Many archives are specifications or partial modules; the later Stage 162–164 gates default to disabled. They cannot be installed together as a working application: schemas, function names, configuration paths and authority assumptions conflict.

The website now uses one authenticated PHP/SQLite implementation in `customer-portal/backend/business.php`. It shares the existing private Customer Portal database and account sessions. It does not run the legacy schemas or placeholder endpoints. Every source archive is identified by filename, byte size and SHA-256 in `SOURCE_INVENTORY.json`; its README requirements and explicit current treatment are in `REFERENCE_CATALOG.md`. These reference files are not included in the public deployment ZIP. The 12 supporting files include private records and local installation/audit evidence and remain in their original folder.

## Working website records

| Area | Current behavior |
| --- | --- |
| Product selection | Existing catalog and cart feed a private build request; stadium sizes are Mini, Medium and Collector. |
| Artwork | Customer uploads or team design requests; private PNG/JPEG/PDF/SVG originals, separate proof/production assets and SHA-256 references. |
| Quotes and proofs | Team creates an immutable proof and quote revision. Customer accepts its current proof and quoted USD total. A revision clears earlier approval. |
| Order status | Owner-only configuration, quote, approval, production, QC, pickup/shipping and completion timelines. |
| Materials | Incoming lot inspection, quantities, reservations, transactional consumption, location/unit/cost references and low-stock tasks. Quantities use integer thousandths. |
| Shop queue | Release requires customer approval, reserved materials, reviewed SVG/LBRN2, a documented financial release reference and a resource/time slot without a recorded collision. |
| Quality | Dimensions, finish/diffusion, electrical and function checks with inspection evidence. Holds block fulfillment and create reinspection tasks. |
| Fulfillment | Team records shipment/pickup references and completion evidence after QC. |
| Support | Owner-only support, warranty, return-review and LED-setup conversations with team replies. These do not authorize refunds or establish warranty eligibility. |
| Operations | Numeric account roles, open tasks, queue counts, stock lots and append-only activity records. In-portal customer updates are stored with order events. |
| Handoff | Authenticated production manifest includes configuration, approved proof, hashed file references and reserved/consumed material lots. Operator performs the physical shop work locally. |
| Training | Team orientation for laser/mirror production, HUB75/HUB75E and controller validation, blockers and next commitments. |

## Boundaries and remaining work

The implementation records and routes business work. It does **not** claim all historical specifications are running. Card payments, refunds, accounting reconciliation, email/SMS delivery, external shipping APIs, omnichannel marketing and supplier purchasing need provider setup and separate validated integrations. Advanced BOM/cutlist generation, AI design generation, CNC/laser execution, firmware provisioning and controller pairing remain reference/local work. The existing Chataigne/WLED-MM browser media preview stays usable; real-time show playback requires a local bridge.

Advertising on the Go and the Sponsor Partner Program retain their separate existing portal links and scope. This change does not publish private fleet information or invent confirmed events, audience delivery, warranty terms, prices or revenue.

## Access and consistency

- The private config must explicitly enable `business_enabled`. Accounts may use media features while business operations are disabled.
- `staff_users` maps owner-approved numeric account IDs to roles. Public signup, requested Premium plans, customer-provided prices and unverified email addresses cannot grant staff access.
- Every mutation checks the existing session, CSRF/origin, method, object ownership or team role. Customer order responses omit financial release references, internal inspection notes and production assets.
- A request key with a payload digest makes retries idempotent. Conflicting key reuse returns 409. Revision checks reject stale approvals and workflow transitions.
- Stock changes, reservations, events and tasks are written in one SQLite `BEGIN IMMEDIATE` transaction. Quarantined/insufficient stock cannot be reserved. Build start consumes reservations once.
- Files are outside the document root, use random internal names and are served through an authenticated attachment endpoint. XML rejects external entity/DOCTYPE definitions and is not rendered as active page content. No credentials or uploaded media are added to the repository or release.

## Validation

Run the release tests, private media HTTP tests and business HTTP tests:

```bash
python3 -m unittest discover -s tests -p 'test_*release.py' -v
python3 -m unittest discover -s tests -p 'test_*backend.py' -v
node --check app.js
node --check customer-portal/portal.js
node --check customer-portal/business.js
php -l customer-portal/backend/business.php
python3 deploy/hostinger/package-customer-portal.py --output /absolute/path/MirroriedLED_Automated_Business_Website.zip
```

The integration has 13 business HTTP tests in addition to the existing 11 media and 22 release tests. They verify actual saved records/files, account isolation, CSRF/roles, proof revisions, stock idempotency, quarantine, scheduling, quality holds, cancellation and service conversations. The public package uses an exact 19-file allowlist and excludes reference documents, private config/data, installers, supplier records and legacy modules.

Browser visual review remains a staging check. This execution environment could not launch its headless browser, and Cloud Browser could not reach the local test server. HTML checks verified unique IDs, labels and referenced assets; JavaScript syntax and backend/release tests passed. Do not treat those checks as a completed visual review.
