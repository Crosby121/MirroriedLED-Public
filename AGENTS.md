# Mirroried LED website work

Repository: Crosby121/MirroriedLED-Public. Default branch: main.
Main website: https://mirroriedled.com. The sponsor VPS is a separate destination.

## Start every website task

1. Refresh the repository and inspect the actual branch, HEAD and working tree.
   Use an isolated branch or worktree when another session has pending changes.
2. Read docs/ai-workflow/CURRENT_STATUS.md, state.json, tasks.json and the recent
   session records. These are dated observations; recheck GitHub before relying
   on their source, checks, task ownership or deployment status.
3. Read the documentation for the part you will change. The root is a static
   storefront with a PHP backend; it has no root npm project.
4. Record this session and its selected task. In a local Git checkout, run:

       python3 tools/ai_workflow.py status
       python3 tools/ai_workflow.py start --app "APP NAME" --task WF-003

   Supply the actual app name. Add --github-account only when that account is
   known. An app declaration is separate from GitHub's authenticated identity.
   A connector-only client can create the equivalent JSON record directly.
5. Publish the task claim on the work branch and share its PR before changing
   product code. Check the current shared queue and open work PRs for conflicts.
   Local file claims are advisory across separate checkouts. Resolve duplicate
   claims with the other session; the central connector is a queued follow-up.

## Leave a usable handoff

- Record only this session's changed files, the problem and fix, actual check
  results, unfinished items, evidence links and the next action.
- A Git author name does not identify the AI app. Declare application identity
  explicitly. Imported history retains unknown applications and access times.
- Finish the record with a completed or blocked outcome; release its task claim.
  CLI usage and connector-only record formats are in docs/ai-workflow/README.md.
- Refresh state.json when a checked source or deployment observation changes,
  then regenerate CURRENT_STATUS.md using the status --write command.
- Run the workflow validator before pushing:

       python3 tools/ai_workflow.py validate
       python3 -m unittest discover -s tests -p 'test_ai_workflow.py' -v

## Website validation and release

- Select checks for the actual change. JavaScript: node --check and
  node --test tests/infinity-builder.test.cjs. PHP: php -l and the relevant
  tests/test_*backend.py HTTP tests. Release helpers: tests/test_*release.py.
  Backend tests require PHP 8.2+, pdo_sqlite, fileinfo and dom.
- Use deploy/hostinger/GITHUB_WEBSITE_DEPLOYMENT.md for the complete release.
  Website-only staging helpers contain an older eight-file subset.
- Packaging success, GitHub Pages success and a merged PR do not prove that the
  PHP website is live on Hostinger. Record the exact verified deployed commit,
  verification time and evidence; otherwise keep the live commit unknown.
- Respect the user's existing task-specific release approvals and deployment
  gates. Permission to maintain work records alone does not authorize a release.
- Preserve private configuration, customer accounts, media, artwork and records.
  This repository is public: keep keys, passwords, tokens, private chat exports,
  customer data and unredacted hosting logs outside it.

## Product facts to preserve

- Brand spelling: Mirroried LED.
- Advertising is quote-based; Sponsor Partner Program exchanges defined
  deliverables for products or services.
- Artwork can be uploaded or designed by the team. Production engraving is
  frosted/diffused so individual LED dots do not show.
- The documented customer tiers are drafts. Requested subscriptions do not
  activate paid entitlements. Browser previews do not prove live WLED playback.
- Follow the configured supplier policy and the 20% frame-only markup in
  docs/INFINITY_MIRROR_BUILDER.md; supplier snapshots need dated verification.
