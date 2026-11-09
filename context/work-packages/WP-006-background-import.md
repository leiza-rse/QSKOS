# WP-006: Vocabulary import as a cancellable background task

Status: draft

Tier: strong+review   ·   Depends on: WP-004   ·   Size: M

## Goal
Importing a large vocabulary or one from a remote URL does not freeze QGIS; it shows progress, can be cancelled, and times out.

## Read first
`context/open-questions.md` Q14; `qskos/services/vocabulary_import.py` (WP-004), `qskos/utils/skos.py`; PyQGIS cookbook § Tasks
(`context/reference/QGIS-3.44-PyQGISDeveloperCookbook-en.pdf`, chapter "Tasks - doing heavy work in the background").

## Tasks
1. `qskos/services/import_task.py`: `QgsTask` subclass running `VocabularyImportService.load` (parsing only; no GPKG writes and no
   QGIS layer access off the main thread). `finished()` runs on the main thread: scheme prompt, replace confirmation, `commit`.
2. Remote URLs: download with an explicit timeout (Q14, default 30 s) and size limit (e.g. 50 MB) into memory, then parse from bytes —
   rdflib never fetches by itself; JSON-LD remote contexts are not fetched.
3. Vocabulary tab: progress via `QgsApplication.taskManager()`, "Load" button disabled while a task runs, cancel supported.

## Acceptance criteria
- pytest-qgis: import of the bundled thesaurus via the task completes and registers the vocabulary; a cancelled task writes nothing.
- A local HTTP server test: slow response → timeout error message; oversized response → size error; no GPKG change in both cases.
- The GUI thread is never blocked longer than the prompt dialogs (manual check in QGIS desktop with a remote vocabulary).

## Tests required
The task tests above (use `QgsApplication.taskManager().waitForFinished()` or the task's `run()` directly where appropriate).

## Out of scope
Importing from conserFAIRy (WP-021); CSV dialects (WP-020).

## Review focus
No QGIS/GPKG object touched in `run()`; network limits; error messages without stack traces.

## Human steps
Decide Q14. Manual check with a remote vocabulary in QGIS desktop.
