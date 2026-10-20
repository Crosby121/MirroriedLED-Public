# 12-inch build: LED and power-supply pricing

Recorded October 4, 2026, Pacific time (October 5 UTC). This is procurement
research for the draft storefront, not a finished-product price or reserved
inventory. Standard LEDs use Alibaba / AliExpress; Amazon remains the rush
option. Freight, duties, tax, enclosure and installation are quoted separately.

## Owner costs and LED allowance

- The 12-inch frame uses **one 12 × 12 mirror**, about **$6**. No second mirror
  is added to that build. The Michaels frame estimate is $17 before the approved
  20% frame-only markup: **$20.40**.
- The owner supplied a provisional **$5–$30 LED budget** for a recommended
  12 × 12 configuration. The exact LED count/type, controller, panel layout and
  supplier determine the final build price. Controller and rear-panel costs
  remain separate rows, so they are not counted twice in the rim allowance.
- Amazon reference supplied by the owner: **about $28 for 300 WS2811 beads**.
  That pack price is not a verified current Amazon offer. It is retained as a
  reference until its voltage, spacing, connectors and exact listing are known.
- The current selectable rim design uses WS2812B strips. The WS2811 bead pack
  is not silently substituted for that part. Physical fit and its electrical
  design must be approved before offering a bead configuration.

## Supplier checks

| Supplier / item | Observed price basis | Treatment |
| --- | --- | --- |
| Amazon, 300 WS2811 beads | Owner reference: about $28 per 300-LED pack; matching current offer not verified | Reference only; no automatic strip price |
| Alibaba, KTRLIGHT 5V WS2811 seed pixels | Category preview lists $0.04–$0.05 per listed piece; MOQ 1 piece | Confirm that a piece means one LED, exact 300-count quantity, pitch and delivered quote. If confirmed per LED, 300 × this range is $12–$15 before shipping; this arithmetic is not an accepted offer |
| AliExpress, seed pixels in 100/200/300-count variants | Direct product page could not be retrieved; no usable current variant price | Quote pending; no mixed-variant floor or new-customer price applied |
| Amazon, BTF 5V 6A / 30W adapter (B01D8FM4N4) | Correct product candidate; retrieved page did not expose a usable selected-offer price | Suitable capacity candidate for the small 5V rim-only example below; price pending |
| Amazon, Aclorol 5V 20A / 100W (B07KC55TJF) | Product specification retrieved; selected-offer price unavailable | Candidate for a sufficiently small verified 5V load; not sized for every 12-inch build |
| Alibaba, Weihao S-100-5, 5V 20A / 100W | Public listing: **$6.61–$7.71**, MOQ **1** | Procurement reference only; exact quote, fit, stock and installation need review |
| Alibaba, S-150-5, 5V 30A / 150W | Indexed supplier listing: **$4.80–$5.40 per unit**, MOQ **50** | Bulk reference only: minimum order is $240–$270 before shipping. Do not present this as the cost of buying one supply |
| AliExpress, 5V supply listings with multiple amperage variants | Direct product pages were unavailable to retrieval | Exact 6A/15A/30A variant and delivered price remain pending |

Supplier pages checked:

- [Alibaba KTRLIGHT seed-pixel category price](https://www.alibaba.com/category/LED-Light-Strings_201717803.html)
- [Alibaba KTRLIGHT seed-pixel product](https://www.alibaba.com/product-detail/Outdoor-Waterproof-Led-WS2811-3PIN-White_1601104270269.html)
- [AliExpress seed-pixel candidate](https://www.aliexpress.com/item/1005012942317837.html)
- [Amazon 5V 6A candidate](https://www.amazon.com/dp/B01D8FM4N4)
- [Amazon 5V 20A candidate](https://www.amazon.com/dp/B07KC55TJF)
- [Alibaba 5V 20A price and MOQ](https://www.alibaba.com/pla/S-100-5-100W-5V-20A-AC-to_11000028989355.html)
- [Alibaba 5V 30A bulk reference](https://www.alibaba.com/wholesale/switching-power-supply-module-5v.html)
- [AliExpress multi-rating supply candidate](https://www.aliexpress.com/item/1005005710838777.html)
- [AliExpress second supply candidate](https://www.aliexpress.com/item/1005009121180274.html)

## Capacity recommendations for review

Frame dimensions do not establish supply capacity. These examples assume the
existing 5V addressable parts, one 72-LED rim row, and the builder's conservative
60 mA per addressable pixel planning model. A **25% planning allowance** is used
below; controller/accessory consumption, connector ratings, derating, measured
LED load and enclosure cooling still need review. The allowance is a studio
planning assumption, not a manufacturer-certified rating for every LED.

| Example 12-inch configuration | LED-load calculation | Supply capacity candidate |
| --- | --- | --- |
| 72 rim LEDs; no rear panel | 72 × 0.06 = 4.32A; × 1.25 = 5.40A | 5V 6A / 30W, subject to actual controller/accessory load |
| 72 rim LEDs plus one 8 × 8 flexible panel, if the artwork fits that layout | 136 × 0.06 = 8.16A; × 1.25 = 10.20A | 5V 15A / 75W; confirm actual load and connectors |
| 72 rim LEDs plus one 16 × 16 flexible panel | 328 × 0.06 = 19.68A; × 1.25 = 24.60A | 5V 30A / 150W with reviewed fused distribution; a 20A supply is not sufficient for this planning target |
| HUB75 rear panels | Addressable rim load plus the exact HUB75 panel datasheet/measured load | Quote pending; do not substitute addressable-pixel current for HUB75 current |
| WS2811 beads | Exact purchased bead voltage and measured/datasheet load are not established | Match the bead voltage first; a 12V bead string needs a 12V rail, while the catalog's 5V panels still need 5V |

One 8 × 8 panel is only an electrical example, not a promise that it covers every
engraving. The builder uses physical artwork coverage to determine panel count.
Every added row or panel changes the load; calculate from that actual count.

QuinLED's preassembled Digi-Uno v3 specifications state **15A continuous through
the board**. The 19.68A LED example therefore needs a reviewed alternative power
path or controller configuration. Digi-Quad v3 specifications distinguish **30A
continuous total for 2 oz copper** from **10A per terminal/fuse**; they do not
permit putting the entire supply capacity through one output. Actual board
version, fuses, wiring and injection points are verified in the production proof.

Primary specification sources:

- [Digi-Uno manufacturer specifications](https://quinled.info/quinled-dig-uno-pre-assembled-v3-1-specifications/)
- [Digi-Quad manufacturer specifications](https://quinled.info/quinled-dig-quad-pre-assembled-v3-1-specifications/)
- [BTF 5V adapter specifications and selectable capacities](https://www.btf-lighting.com/products/5v-power-supply)

The active power-supply row stays unpriced until an appropriate exact part and
landed cost are confirmed. The research prices are separate catalog references;
they never become checkout prices. Final staff pricing includes all fabrication,
wiring, testing, shipping and tax. No actual merchant checkout or live website
release is claimed by this research update.
