# Product page, mirror artwork and stadium catalog

`/products/` links to the existing `/infinity-builder/`, `/stadiums/`, and custom
request form. The homepage keeps its build section and links to the new catalog.

The mirror gallery retains the three original SVG starters and adds five saved
ChatGPT concepts: Dodgers bats and skyline, Dodgers engraved mirror, Dodgers LA
emblem, Dodgers skyline, and sports emblems. Only curated public previews are
included. Customer uploads, new private artwork and original build archives stay
outside this public release. The existing artwork approval, size selection,
hardware estimates, supplier policy and secure quote flow remain in place.

The stadium directory has 92 team entries: 30 MLB, 32 NFL and 30 NBA. Saved previews
exist for 31 entries; remaining teams explicitly need artwork. Images are labeled
as model concepts or stylized layouts, rather than finished inventory. Venue names
are saved catalog labels and are confirmed with the customer's production proof.

Customers can filter by sport and team, cycle through a team's saved images and
select Mini, Medium or Collector. The sample prices are $99.99, $199.99 and $299.99.
The sample selection uses a separate local storage key and does not place an order.
Requesting a real quote creates a `Layered Stadium Model` item in the existing
build list and hands it to the Customer Portal. Placeholder amounts are excluded
from that item. The studio supplies a final quote after review.

Both builders also offer a prefilled email quote request at the website's
existing `quotes@mirroriedled.com` address. This opens the customer's email app;
the customer reviews and sends it. Stadium emails include the selected team and
size without a placeholder amount. Mirror emails require an approved, valid
design and include its chosen configuration. Customers attach their uploaded
artwork and downloaded build file themselves. This keeps quote requests usable
while the private Customer Portal configuration and payment activation remain
pending; it does not claim email delivery or online payment processing.

Three full-size image entries in the source archive were empty. Their intact
curated thumbnail previews are used for Dodgers bats and skyline, the Yankees
cardboard concept and the Yankees layout preview. These are preview assets;
production source files remain in the private archive.

Both complete-website release allowlists include all 121 public files. The
installer's rollback directory validation includes every parent of those exact
paths so nested image folders can be safely restored or removed. Full-site
backups, unrelated files and private customer records retain their existing rules.

Checks: `node --test tests/*.test.cjs`, Python unittest discovery, release
packaging, and `tests/products.browser.cjs` with Playwright available in the
execution environment. The browser check covers navigation, all sport counts,
team filters, image cycling, sample isolation, quote import, storage failure,
saved artwork/upload approval and mobile overflow. PHP backend checks require
the extensions documented in `AGENTS.md`; the GitHub release validates those.
