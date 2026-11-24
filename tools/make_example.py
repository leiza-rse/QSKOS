"""Step `example`: ontology/example.ttl from the synthetic fixture in tests/fixture.py.

The example is produced by the same builder as a real export (utils/rdf_model.py),
with fixed dates, so it can never describe a model the code no longer writes.
"""
from . import ontology_io as oio
from utils.rdf_model import build_graph, serialize_deterministic


def run(**_):
    from tests import fixture as fx
    g, n, w = build_graph([fx.make_layer()], fx.make_meta(local_crs=True), fx.VOCAB_PREFIXES)
    serialize_deterministic(g, str(oio.EXAMPLE))
    print(f"  ontology/example.ttl  ({len(g)} triples, {n} features)")
