"""Step `test`: run tests/ with unittest; a failure stops the pipeline."""
import unittest

from . import ontology_io as oio


def run(strict: bool = False, **_):
    import os
    if strict:
        os.environ["QSKOS_STRICT"] = "1"        # missing pyshacl becomes an error
    suite = unittest.defaultTestLoader.discover(str(oio.ROOT / "tests"), top_level_dir=str(oio.ROOT))
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    if not res.wasSuccessful():
        raise SystemExit("  !!  tests failed")
