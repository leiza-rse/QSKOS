# WP-xxx: Title

Status: draft   <!-- draft | ready | review | done. ready only on the human's instruction (AGENTS.md § Batch cycle). Agent sets review (review tier) or done. -->

Tier: cheap | strong | strong+review   ·   Depends on: WP-…   ·   Size: S/M/L (one commit series)

## Goal
One or two sentences: what exists afterwards that does not exist now.

## Read first
Only what this package needs, as sections: `context/adr/00xx-*.md`, code paths.

## Tasks
Numbered, concrete, in order. Name files/modules to create or change.

## Acceptance criteria
Observable checks. Each one maps to a test or a command whose result can be verified.

## Tests required
Which tests must exist (pure pytest and/or pytest-qgis through the real UI path).

## Out of scope
What the agent must not do in this package.

## Review focus
Only for `review` tier: what the reviewer must look at beyond `context/review-checklist.md`.

## Human steps
Anything only the human can do (credentials, files to place, decisions, manual check in QGIS desktop).
