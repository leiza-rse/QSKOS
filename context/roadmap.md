# Roadmap

Planned 2026-11-09, after the fix-forward branch (multi-vocabulary bug, JSON fields, export merge). Goal: a plugin whose tabs are thin,
whose logic is testable without QGIS, and whose export is correct for any input — then interop with conserFAIRy and a public release.

**Delegation.** A package is delegable only if its file in `context/work-packages/` has `Status: ready` and its dependencies are `review` or
`done` (`make next`). Rows without a file are outlines. `ready` is set by the human (AGENTS.md § Batch cycle). Dependencies are listed here
**and** in the package file; `make next` fails if they differ.

**Tier** = model class. `cheap` = clear spec, local change. `strong` = multi-file design or tricky logic.
`review` = after implementation, a stronger model or a human runs `context/review-checklist.md` before `done`.

## Phase 0 — Baseline
| WP | Title | Tier | Depends |
|---|---|---|---|
| 001 | Tooling baseline: ruff in CI, pre-push hook, plugin zip build, ignore QGIS leftovers | cheap | – |

## Phase 1 — Structure
| WP | Title | Tier | Depends |
|---|---|---|---|
| 002 | `GpkgStore` class for all GeoPackage access | strong+review | 001 |
| 003 | Pure symbology rule planner, thin symbology tab | strong | 001 |
| 004 | Tab decoupling: state signals, `VocabularyImportService`, dialogs at the edge | strong | 002 |
| 005 | Split the LOD export tab, one spec path | cheap | 004 |
| 006 | Vocabulary import as a cancellable background task | strong+review | 004 |
| 007 | QGIS 4 readiness and cleanups (qgis.PyQt, deprecations, broad excepts, import languages) | cheap | 001 |

## Phase 2 — Export correctness (decisions by the export author: Q4, Q5, Q9, Q10)
| WP | Title | Tier | Depends |
|---|---|---|---|
| 010 | Collision-free export IRIs | strong+review | 005 |
| 011 | Export fixes: vocabulary usage, metadata copy, serialisation, licence check | cheap | 005 |

## Phase 3 — Interop and release (outlines)
| WP | Title | Tier | Depends |
|---|---|---|---|
| 020 | Import the conserFAIRy vocabulary CSV dialect (Q12) | cheap | 004 |
| 021 | Import a vocabulary release from conserFAIRy (file or API) | strong+review | 006 |
| 022 | Upgrade legacy text annotation fields to JSON (Q7) | strong+review | 002 |
| 023 | Persist object namespace and dataset metadata in the GeoPackage | cheap | 011 |
| 024 | Publish to the QGIS plugin repository | cheap | 001, 007 |
