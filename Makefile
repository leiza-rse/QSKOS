# QSKOS — developer commands (see AGENTS.md § Commands)
#   make test       unit + export tests, no QGIS needed
#   make test-qgis  QGIS-bound and end-to-end tests in real headless QGIS
#   make docs       rebuild ontology example, diagrams and docs/
#   make next       work package status (context/roadmap.md, context/work-packages/)

.PHONY: test test-qgis docs next

test:
	@uv run pytest -q

test-qgis:
	@scripts/run_qgis_tests.sh -q

docs:
	@uv run python tools/main.py

next:
	@python3 scripts/wp_status.py
