# Mirroried LED deployment readiness

Checked October 4, 2026, 11:26 PM America/Los_Angeles (October 5, 06:26 UTC).

**SSH access and hosting preflight are verified.** The replacement key authenticates, and Python 3.11/PHP 8.3 checks pass. PR #17 contains the remote Python selection fix; it must reach main before the release workflow can use it. No live deployment was performed. Earlier build-review findings below remain dated observations.

## Build status

| Build | Exact checked source | Result | Deployment readiness |
| --- | --- | --- | --- |
| Main storefront, configurator and supplier pricing | `3b1e04aae7277239e14a216bbfe4557e80e5da29` | Main packaging and workflow validation pass; configurator/pricing PRs 10/11 are merged | Release package prepared; SSH/preflight verified with PR #17 Python configuration |
| Customer account/media portal | Same main source | PHP portal checks included in successful CI; private account/media configuration is required | Paid subscriptions, recovery and physical playback are not ready in this repository release |
| Phased opening and checkout, [PR 14](https://github.com/Crosby121/MirroriedLED-Public/pull/14) | `554c118724eaa02cc9bc410cb8597293cff45dd5` | Latest Storefront CI and workflow checks pass; PR remains draft | Merchant Checkout/webhook acceptance, live configuration and fulfillment confirmation remain outstanding |
| Chat-capture fixes, [PR 15](https://github.com/Crosby121/MirroriedLED-Public/pull/15) | `8e59fa929bb400665bdfa26cc7275cf515eb2602` | Latest CI passes; two unresolved review threads | Blocked by reproduced secret-redaction defects |
| AI database, [PR 16](https://github.com/Crosby121/MirroriedLED-Public/pull/16) | `caf12c902c2e98fa31e370e34915fc33f8333bce` | Latest CI passes; six unresolved review threads | Needs privacy, permissions and import correctness fixes before installation |

## Historical Hostinger SSH blocker

[Deployment run 37236890583, attempt 2](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37236890583) passed release validation and “Verify main website hosting settings.” It failed at “Check website host and PHP before any upload.”

The job log reports `Permission denied (publickey,password)`. Upload, backup/install and live verification were skipped. The configured main-site key parsed successfully locally in the runner; server authorization was rejected. This does not identify whether the mismatch is the authorized public key, the selected account or account SSH access.

The older record saying both main-site secrets were missing is superseded by this retry. Secret values were not retrieved. The expected website account/host/webroot remain in the existing main-website profile; the sponsor VPS is a separate destination.

Historical next action (superseded by the verified result below): confirm that the public key authorized for the website account matches the GitHub deployment private key, verify account SSH access, and pass authenticated host/PHP preflight. Check settings available to the production environment. Do not substitute sponsor-VPS keys or bypass host verification.

No verified live Hostinger revision is established. GitHub Pages and packaging success do not establish a PHP deployment.

## Independently reproduced blockers

Exact-source excerpts were fetched through the GitHub connector. Small local checks used synthetic inputs only.

- **PR 15:** line-by-line plaintext filtering leaves a synthetic multiline private-key body intact. Browser suffix capture loses the sensitive field name; the native redactor consequently accepts a synthetic streamed token value. Both review findings reproduced.
- **PR 16:** the credential guard accepts synthetic Bearer values separated by a tab or newline, and an uppercase-scheme URL containing a signed query. A valid half-second session is rejected by lexical timestamp comparison. These findings reproduced.
- **PR 16:** source inspection also confirms WAL is enabled before tightening recognized database permissions, replay equality uses Python value equality, and session source creation precedes event replay. The related permission/import/type findings were not exercised against a full database in this audit.

A green automated-review run means the review completed; it does not mean the review found no defects. No review thread was resolved by this audit.

## Scope and limits

This was a readiness check. No product source was changed, no builds were merged, no deployment was triggered, no payment was made, and no customer/hardware connection was activated. Public project status and a session handoff are updated on a documentation branch.

The standalone Customer Portal repository contains README/docs, with no deployable application at its root. The older private repository contains isolated Stage 162 adapter work; its open PR 4 is documentation/test evidence, not an operational release. Use the current public website release repository for the checked Hostinger build.

The Hostinger AI Builder connector returned no Agentic websites. It does not inventory manually hosted PHP websites. Public website retrieval was unavailable in the web tool, so no fresh live-page comparison is claimed.

## Evidence

- [Main package](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37242502555)
- [Main shared workflow](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37242502505)
- [Checkout CI](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37254755130)
- [Capture CI](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37244488440)
- [AI database CI](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37265647051)
- [Latest failed SSH job](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37236890583/job/111546207432)



## Earlier SSH verification — October 4, 11:43 PM Pacific

A dedicated [read-only check](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37273814509/job/111646329411) ran using the existing production key and trusted host settings. Key preparation passed; public-key-only SSH authentication was rejected. Webroot/PHP tests were not reached and no website writes were attempted.

Verified deployment public key: ED25519, `SHA256:9abf5Se5+p8Em9rCEhsN2KXStEJ4DVagcUpCK9EB8X0`. Compare this fingerprint with the key authorized for the Hostinger website account. The private key was never printed or retrieved by this session. The result cannot distinguish a key mismatch from account SSH-access settings.

## Replacement key and runtime verification — October 5, 1:02 AM Pacific

The user authorized the generated public key for the website hosting account and updated GitHub's matching repository secret. GitHub uses the new ED25519 fingerprint `SHA256:lUQfuZRVSm+Odyk+i4LmKt9TfcRXAKZ5WaWvFCShTEo`. Authentication passed at 00:54 Pacific, exposing a separate preflight failure: the hosting account's default `python3` is 3.6.8. No existing live files were modified.

Read-only checks found Python 3.8.20 and 3.11.16 installed at explicit alternative paths. The main website profile now selects `/opt/alt/python311/bin/python3`. The website release, connector release and diagnostic workflows validate and use that setting for remote preflight; installation and rollback use the same interpreter. Runner-local packaging continues to use runner Python. The diagnostic reports each failed requirement separately.

[Successful full read-only preflight](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37281128606/job/111669230359): authenticated SSH; expected directory and existing index.html; Python 3.11.16; PHP 8.3.33; pdo_sqlite, fileinfo and dom. [Storefront CI](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37281133203) and [workflow CI](https://github.com/Crosby121/MirroriedLED-Public/actions/runs/37281133181) pass for fix commit `929ec0b8d6e2e80704f9ad68b75ec4e93c758617`. Local YAML/Bash/embedded-Python checks and all 13 workflow lifecycle tests pass.

The change is published in [PR #17](https://github.com/Crosby121/MirroriedLED-Public/pull/17), not merged. Apply the configuration fix before running the authorized website release. The live revision remains unknown; no upload, installation, payment activation or hardware connection occurred. Generated private-key material remains outside the public repository.
