# Review checklist

Batch review of all packages in `Status: review` (`make next` lists them). The reviewer is a stronger model or a human, in a **fresh session**.
Review a batch at least before a release and before starting a package that changes reviewed code again.

## Context for the reviewer (keep it small)
Read only: this file, the work packages, `context/adr/README.md`, ADRs the packages list, and the diff:
`git diff reviewed..HEAD -- . ':!qskos/libs' ':!docs' ':!ontology/example.ttl' ':!uv.lock'`.
Do not read the whole codebase; open a file only to check a specific finding.

## Checks
1. **Scope:** every task done; nothing outside the package (extra features, unrelated refactors, dependencies not named in the summary).
2. **Acceptance criteria:** each one has a test or a reproducible command; run `make test` and `make test-qgis`.
3. **Real QGIS path:** QGIS-facing behaviour is tested through real widgets/signals and real GPKG round trips, not by setting state or
   writing values directly (ADR-0006). New bug fixes have a regression test that fails on the old code.
4. **Edit sessions and results:** no commit/rollback of a layer the user is editing; every `commitChanges`/`startEditing`/`addAttribute`
   result is checked and reported; programmatic UI updates block signals.
5. **GeoPackage safety (ADR-0002/0004):** parameterised SQL only (identifiers from `qskos_layer_config` or `vocab_table_name`, quoted);
   no DROP/ALTER of non-qskos tables; schema changes of user tables only behind an explicit user action.
6. **Field types (ADR-0001):** annotation fields use the native GPKG JSON type; no new text annotation fields.
7. **Parsers and network:** no network access in parsers except the explicit remote import (timeout, off the GUI thread); errors are
   shown as messages and logged, no stack traces in dialogs.
8. **Export:** output is valid RDF for any user input (IRIs validated, literals for free text); `make docs` leaves `git status` clean
   when the model did not change; ontology, shapes and generated docs change together.
9. **Code rules:** no duplicates/`_v2`, state in classes, pure logic without Qt/QGIS imports, tabs thin, size limits, no dead code.
10. **Docs:** `context/STATUS.md` updated (≤ 1 page), `CHANGELOG.md` entry, open questions added where the implementer guessed.

## Result
Write findings into the package file under `## Review` (date, reviewer, findings with file:line, verdict).
Verdict `pass` → set `Status: done`. Verdict `changes`:
- **Small findings** (local fix, a few lines): the reviewer fixes them in the same session, each with a test that fails on the old code,
  notes the fix under the finding, and sets `pass`.
- **Larger findings** (design change, new behaviour, many files): keep `Status: review`; the implementer fixes and the review is repeated
  on the fix diff only.
When every package of the batch passed: `git tag -f reviewed HEAD` (the next batch starts there).
