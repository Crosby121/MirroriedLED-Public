# Infinity Mirror customer builder

`Choose a build → Build Infinity Mirror → /infinity-builder/`

The builder has six linked steps: supported mirror size / frame finish, WS2812B rim
rows and counts, customer-approved artwork, rear lighting / panel layout,
compatible controllers, and the remaining hardware. A live SVG preview shows
the mirror and a separate panel coverage view. Device-local drafts and artwork
are stored in IndexedDB; they are not shared until a customer saves a quote
request in the signed-in Customer Portal. The complete configuration is retained
in the quote record, with the original upload and engraving mask attached.

## Production rules

- Backside engraving must be frosted / diffused, with broad continuous light
  areas and no pinholes, clear thin etches or visible RGB / HUB75 dots.
- The artwork stays inside the mirror's safe interior, including its rim rows.
- Catalog suggestions use physical width / height, not the number of pixels as
  a stand-in for physical size. Each candidate is a uniform rectangular tiling;
  both orientations are evaluated. Candidates must cover the entire artwork
  bounding box and fit inside the frame. Among these candidates, the default
  minimizes unused area, then panel count, then pitch. Irregular shapes and
  mixed-panel layouts are left for the production proof; the result is not
  described as a global packing optimum.
- Physical panel dimensions in the draft catalog are nominal. Scan modes,
  drivers, measured board dimensions, actual quantities and mounting clearances
  must be verified against inventory before fabrication. Unknown stock is not
  advertised as reserved or confirmed. An incompatible layout blocks completion.
- Flexible LEDs use Digi-Uno or Digi-Quad. HUB75 uses MatrixPortal S3; the rim
  uses a separate Digi-Uno or Digi-Quad. Beast is unavailable until fabricated,
  validated and released into inventory. No firmware or approved pin map is
  silently replaced by this configurator.
- The addressable current estimate uses a conservative 60 mA / pixel assumption.
  HUB75 current is not invented. The team sizes actual power supplies, fuses,
  wires, cooling, output grouping and audio input in the production proof.
- Customer concept approval does not start a laser, collect payment or authorize
  fabrication. Existing quote, staff review, proof and production gates continue.

## Artwork library and upload

`infinity-builder/catalog.json` contains a public curated gallery. The initial
three SVGs are original vector studio starters, explicitly labeled as starters
that need a final proof. They are not presented as historical AI artwork or
production-certified engraving files. Add owner-approved existing artwork or
pre-generated ChatGPT images to this curated manifest with a unique ID, title,
source attribution and local URL; include each asset in both public deployment
allowlists. Do not expose the owner's private ChatGPT Library to customers.

Upload preview accepts PNG, JPEG and WebP up to 10 MB / 24 million pixels, with a
light/dark polarity setting. The preview makes a high-contrast mask and crops its
blank outer margin; it keeps the original for the production proof. This is not
an automatic certification of fine detail or frosted diffusion. PDF/SVG source
artwork can be attached separately through the Customer Portal.

## Private AI activation

Keep the existing private config outside `public_html`. Its optional
`infinity_builder` section is shown in `customer-portal/backend/config.example.php`:

```php
'infinity_builder' => [
    'ai_enabled' => true,
    'openai_api_key' => getenv('MLED_OPENAI_API_KEY') ?: '',
    'allowed_user_ids' => [/* owner-approved numeric customer IDs */],
    'text_model' => 'gpt-4o-mini',
    'image_model' => 'gpt-image-1.5',
    'daily_images_per_user' => 3,
    'daily_images_total' => 10,
],
```

PHP cURL with TLS verification is required for AI. The server's HTTP timeout must
allow image generation (up to 210 seconds upstream / 240 seconds PHP). The default
is disabled, with no key and no approved accounts. No secret is sent to the page.
Existing effective subscription / account activation is not inferred from signup.
The owner approves each allowed account. The page reports unavailable AI clearly
and retains subject-specific local questions and answers without pretending an
image was generated.

`builder-guide` calls the Responses API with a strict question schema to determine
which follow-up questions the image needs. `builder-generate` calls the Images API
with the production rules prepended and appended to the customer design data.
Consent is required, and daily account plus site allocations are reserved before
a paid request. A repeated request key retrieves its existing image and does not
start a second generation. Provider errors consume the reserved allocation because
the provider may already have incurred work. New image descriptions get new keys.
Generated PNGs stay outside the webroot and are served only to their owner.
`builder-approve` records that owner's concept approval before quote submission.
The quote service rechecks ownership, availability and physical layout server-side.

Official implementation references:

- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/image-generation
- https://learn.adafruit.com/adafruit-matrixportal-s3
- https://quinled.info/quinled-dig-uno/
- https://quinled.info/quinled-dig-quad/

## Deployment and verification

Use the **Deploy Complete Website to Hostinger** workflow and the expanded
`package-customer-portal.py` / `website-release.py` public allowlists. This release
contains 29 public files; private configuration and customer data are excluded.
The older eight-file storefront-only staging/manual helpers do not include this
builder or the Customer Portal and must not be used to publish this release.
The complete website installer backs up the entire site, protects `builder.php`
through `.htaccess`, verifies every installed file and supports rollback of new
files and directories. AI activation requires the separate private config above.

Validation: Node planning tests, PHP HTTP tests for account / CSRF / artwork
ownership / approval / tampered configurations, existing portal and release tests,
and desktop/mobile browser checks for artwork approval, LED rows, panel fit,
controller switching, draft restoration and quote handoff. Paid OpenAI generation
requires an activated account and an actual key for a live acceptance check.
