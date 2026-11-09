"""Step `test`: run the export tests with unittest; a failure stops the pipeline."""
import unittest

from . import ontology_io as oio


def run(strict: bool = False, **_):
    import os
    if strict:
        os.environ["QSKOS_STRICT"] = "1"        # missing pyshacl becomes an error
    # Only the unittest-style export tests: the other modules in tests/ are
    # pytest / pytest-qgis suites (run them with `uv run pytest` and
    # scripts/run_qgis_tests.sh).
    suite = unittest.defaultTestLoader.discover(
        str(oio.ROOT / "tests"), pattern="test_export*.py",
        top_level_dir=str(oio.ROOT))
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    if not res.wasSuccessful():
        raise SystemExit("  !!  tests failed")
