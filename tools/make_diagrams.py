"""Step `diagrams`: Mermaid sources -> docs/diagrams/*.mmd, rendered to SVG and PNG.

Three diagrams:

  model-simple   the QSKOS model in QSKOS terms (what the data contains)
  model-cidoc    the same model with the CIDOC CRM class of every node
  hierarchy      every qskos: class with its direct superclasses, generated
                 from ontology/qskos.ttl (so it cannot drift from the ontology)

The .mmd files are always written.  SVG/PNG need Mermaid CLI (`mmdc`, npm
package @mermaid-js/mermaid-cli) and a Chromium it can drive:

    Windows:  npm install -g @mermaid-js/mermaid-cli
    override: set QSKOS_MMDC=<path to mmdc>   (optional)
              set QSKOS_PUPPETEER_CONFIG=<json with {"executablePath": ..., "args": [...]}>   (optional)

Without mmdc the step warns and keeps the committed images; with --strict it fails.

Colour scheme (shared with the paper figures):
  QSKOS class #9a3412, vocabulary term #4c1d95, physical object #166534,
  metadata (DCAT) class #fbbf24, external standard class #e2e8f0.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import ontology_io as oio

CLASSDEFS = """
    classDef meta fill:#fbbf24,stroke:#000000,color:#000000
    classDef cls fill:#9a3412,stroke:#000000,color:#ffffff
    classDef real fill:#166534,stroke:#000000,color:#ffffff
    classDef term fill:#4c1d95,stroke:#000000,color:#ffffff
    classDef ext fill:#e2e8f0,stroke:#000000,color:#000000
"""

MODEL_SIMPLE = """flowchart TB
    CAT(["qskos:Catalog"])
    DS(["qskos:Dataset"])
    DIST(["qskos:Distribution"])
    LAYER(["qskos:FeatureLayer"])
    FEAT(["qskos:Feature"])
    GEOM(["qskos:Geometry"])
    CRS(["qskos:LocalCoordinateSystem"])
    ANN(["qskos:Annotation"])
    OBJ(["qskos:MappedObject"])
    FC(["Field concept<br/>(skos:Concept)"])
    VC(["Value concept<br/>(skos:Concept)"])

    CAT -->|dcat:dataset| DS
    DS -->|dcat:distribution| DIST
    DS -->|dct:hasPart| LAYER
    DS -->|dct:subject| OBJ
    LAYER -->|rdfs:member| FEAT
    FEAT -->|oa:hasSource| OBJ
    FEAT -->|geo:hasGeometry| GEOM
    GEOM -->|qskos:inCoordinateSystem| CRS
    ANN -->|oa:hasTarget| FEAT
    ANN -->|qskos:attribute| FC
    ANN -->|oa:hasBody| VC
""" + CLASSDEFS + """
    class CAT,DS,DIST meta
    class LAYER,FEAT,GEOM,CRS,ANN cls
    class OBJ real
    class FC,VC term
"""

MODEL_CIDOC = """flowchart TB
    CAT(["E73 Information Object<br/>(Catalog)"])
    DS(["E73 Information Object<br/>(Dataset)"])
    DIST(["E73 Information Object<br/>(Distribution)"])
    LAYER(["E73 Information Object<br/>(FeatureLayer)"])
    FEAT(["E53 Place<br/>(Feature)"])
    GEOM(["E73 Information Object<br/>(Geometry)"])
    CRS(["SP4 Spatial CRS<br/>(⊑ E29 Design or Procedure)"])
    ANN(["E13 Attribute Assignment<br/>(Annotation)"])
    OBJ(["E18 Physical Thing<br/>(E19 / E22 / ...)"])
    FC(["E55 Type<br/>(Field concept)"])
    VC(["E55 Type<br/>(Value concept)"])

    CAT -->|P106 is composed of| DS
    DS -->|P106 is composed of| LAYER
    DS -->|P67 refers to| OBJ
    FEAT -->|P157 is at rest relative to| OBJ
    ANN -->|P140 assigned attribute to| FEAT
    ANN -->|P141 assigned| VC
    ANN -->|P177 assigned property of type| FC
    GEOM -.->|"Q9 is expressed in terms of<br/>(CRMgeo, SP5, unchecked)"| CRS
    DS -.->|"no CRM property<br/>(dcat:distribution)"| DIST
    LAYER -.->|"no CRM property<br/>(rdfs:member)"| FEAT
    FEAT -.->|"no CRM property<br/>(geo:hasGeometry)"| GEOM
""" + CLASSDEFS + """
    class CAT,DS,DIST meta
    class LAYER,FEAT,GEOM,CRS,ANN cls
    class OBJ real
    class FC,VC term
"""

STATIC = {"model-simple": MODEL_SIMPLE, "model-cidoc": MODEL_CIDOC}

TITLES = {
    "model-simple": "QSKOS model (data view)",
    "model-cidoc": "QSKOS model, CIDOC CRM view",
    "hierarchy": "Class hierarchy: QSKOS classes and their direct superclasses",
}


def _node_id(iri) -> str:
    return oio.short(iri).replace(":", "_").replace("-", "_").replace(".", "_")


def _node_class(iri) -> str:
    s = str(iri)
    if s.startswith(str(oio.QSKOS)):
        return "cls"
    if s.startswith("http://www.w3.org/ns/dcat#"):
        return "meta"
    if s.startswith(oio.CRM + "E18_"):
        return "real"
    if s.startswith("http://www.w3.org/2004/02/skos/core#") or s.endswith("E55_Type"):
        return "term"
    return "ext"


def hierarchy_source(g=None) -> str:
    """Mermaid flowchart of qskos: classes -> direct superclasses, from the ontology."""
    g = g or oio.ontology()
    lines = ["flowchart LR"]
    nodes = {}
    edges = []
    for c in oio.qskos_classes(g):
        nodes[c] = True
        for p in oio.direct_superclasses(g, c):
            nodes[p] = True
            edges.append((c, p))
    for n in sorted(nodes, key=str):
        lines.append(f'    {_node_id(n)}["{oio.short(n)}"]')
    for c, p in sorted(edges, key=lambda e: (str(e[0]), str(e[1]))):
        lines.append(f"    {_node_id(c)} -->|subClassOf| {_node_id(p)}")
    lines.append(CLASSDEFS.rstrip("\n"))
    by_class = {}
    for n in sorted(nodes, key=str):
        by_class.setdefault(_node_class(n), []).append(_node_id(n))
    for k in sorted(by_class):
        lines.append(f"    class {','.join(by_class[k])} {k}")
    return "\n".join(lines) + "\n"


def sources() -> dict:
    out = dict(STATIC)
    out["hierarchy"] = hierarchy_source()
    return out


# ─── Rendering ────────────────────────────────────────────────────────────────

def find_mmdc():
    env = os.environ.get("QSKOS_MMDC")
    if env and Path(env).exists():
        return env
    for name in ("mmdc", "mmdc.cmd"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _render(mmdc, mmd: Path, out: Path, svg_id: str):
    cmd = [mmdc, "-i", str(mmd), "-o", str(out), "-b", "white", "-I", svg_id,
           "-c", str(Path(__file__).with_name("mermaid-config.json"))]   # fixed seed: byte-stable output
    if out.suffix == ".png":
        cmd += ["-s", "2"]
    cfg = os.environ.get("QSKOS_PUPPETEER_CONFIG")
    if cfg:
        cmd += ["-p", cfg]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError(f"mmdc failed for {out.name}:\n{res.stderr.strip()[-600:]}")


def run(strict: bool = False, **_):
    oio.DIAGRAMS.mkdir(parents=True, exist_ok=True)
    srcs = sources()
    for name, text in srcs.items():
        (oio.DIAGRAMS / f"{name}.mmd").write_text(text, encoding="utf-8", newline="\n")
        print(f"  {name}.mmd")
    mmdc = find_mmdc()
    if not mmdc:
        msg = ("Mermaid CLI (mmdc) not found: .mmd written, SVG/PNG left as they are. "
               "Install: npm install -g @mermaid-js/mermaid-cli")
        if strict:
            raise SystemExit("  !!  " + msg)
        print("  !!  " + msg)
        return
    for name in srcs:
        for ext in ("svg", "png"):
            _render(mmdc, oio.DIAGRAMS / f"{name}.mmd", oio.DIAGRAMS / f"{name}.{ext}", f"qskos-{name}")
            print(f"  {name}.{ext}")
