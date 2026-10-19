# Storefront Integration Implementation Plan

> Execute inline in this session; use the existing regression suites for merge resolution.

**Goal:** Reconcile draft PR #14 with current main into a reviewable, tested branch, preserving current product galleries and deployment safeguards.

**Architecture:** Merge the existing ordering implementation into current main. Retain main's work records and modern release runtime, preserve the draft's gated checkout, and keep deployment and payment activation separate.

**Tech Stack:** Static HTML/JS, PHP 8.2+, SQLite, Python release helpers, GitHub Actions.

**Spec:** AGENTS.md; draft docs/PHASED_PRODUCT_OPENING.md; deploy/hostinger/GITHUB_WEBSITE_DEPLOYMENT.md.

## Constraints and review focus

- Preserve all current gallery images and private data boundaries.
- Retain current workflow tasks/sessions; reconcile the old branch's WF-006 to WF-008 and WF-010 owner-cost history.
- Keep live payments disabled by default and both launch PRs draft.
- Retain hosted Python 3.11, exact-source verification, backups and rollback.
- Check the complete configure/save/quote/proof/test-payment flow, duplicate payment handling and production gating.

## Tasks

- [x] Publish WF-008 task claim before product changes; reproduce eight conflicting paths with git merge-tree.
- [x] Resolve the merge, preserve newer browsing, and reconcile historical task references. Inspect the final diff and confirm no conflict markers remain.
- [x] Run Node behavior suites, Python suites, workflow validation and packaging. Run PHP locally if available; otherwise verify native PHP in GitHub CI and report the distinction.
- [x] Review the final integration; publish source and verify the remote commit/tree. Record actual checks and remaining merchant/private-configuration blockers. No production release is part of this merge repair.

## Execution ledger

- Claim published in PR #26, commit 49ce77a515c6cae38eb23a36fb58b0e7ab2aad8d; 13 workflow tests passed.
- Eight conflicting paths reproduced before edits. Original PR #14 remains preserved.
- Decision: use current main's shared workflow authority and deployment runtime; importing older state would regress verified deployment and capture history.

- Source integration published as 6b7e64ff153d7983f67eef77be4a6478821f9b59; both GitHub checks passed, including nine commerce tests. Cache correction published as 6652c68ae1b69de565403860b8f434bcc0fd1ba1.
- All 176 Python tests passed locally with extracted PHP 8.3 and required extensions; all 37 Node tests passed. Package contains 136 allowlisted files. Gallery image bytes match main.
- Independent review found stale staff JavaScript cache key; repaired all stale versioned local asset references and checked content hashes. No other critical/important integration findings.
- Browser replay unavailable: Playwright browser download failed. Actual merchant acceptance, private account setup, final quotes/fulfillment and a fresh verified production release remain required.
- Decision: preserve the draft phased homepage/legacy portal redirect on this draft branch; no merge to main or live deployment occurs while release acceptance is incomplete.
