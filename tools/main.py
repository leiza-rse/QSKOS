"""QSKOS ontology tools: one command rebuilds everything that is generated.

Run from the repository root (Windows cmd or any shell):

    python tools/main.py                  all steps, in order
    python tools/main.py --list           print the steps and exit
    python tools/main.py --only diagrams  one step
    python tools/main.py --from docs      this step and everything after
    python tools/main.py --skip diagrams  everything but this step
    python tools/main.py --dry-run        print the plan, run nothing
    python tools/main.py --strict         warnings become errors (what CI should run)

Steps write to ontology/example.ttl, docs/ (diagrams, pages, report).
Nothing here needs QGIS.  Needs: rdflib (the copy in libs/ is used if none is
installed), pyshacl for the SHACL tests, Mermaid CLI (mmdc) for SVG/PNG.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STEPS = [
    ("example", "tools.make_example", "ontology/example.ttl from the synthetic fixture"),
    ("test", "tools.run_tests", "unit tests (model, queries, ontology, SHACL, QGIS adapter)"),
    ("diagrams", "tools.make_diagrams", "Mermaid sources, SVG and PNG into docs/diagrams/"),
    ("report", "tools.make_report", "ontology and example statistics into docs/report.md"),
    ("docs", "tools.make_docs", "overview, model, vocabulary, crosswalk into docs/*.md"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--from", dest="from_")
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    names = [s[0] for s in STEPS]

    if a.list:
        for n, _, d in STEPS:
            print(f"{n:9s} {d}")
        return 0
    for opt in [a.only, a.from_, *a.skip]:
        if opt and opt not in names:
            ap.error(f"unknown step '{opt}' (see --list)")

    plan = names
    if a.only:
        plan = [a.only]
    elif a.from_:
        plan = names[names.index(a.from_):]
    plan = [n for n in plan if n not in a.skip]

    for i, (n, mod, d) in enumerate([s for s in STEPS if s[0] in plan], 1):
        print(f"[{i}/{len(plan)}] {n}: {d}")
        if a.dry_run:
            continue
        importlib.import_module(mod).run(strict=a.strict)    # lazy: --list/--dry-run import nothing heavy
    return 0


if __name__ == "__main__":
    sys.exit(main())
