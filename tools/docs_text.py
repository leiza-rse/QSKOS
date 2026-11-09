"""Prose for the generated documentation (docs/*.md).

The generator reads classes, properties and superclasses from
ontology/qskos.ttl and takes the human text from here.  A term of the
ontology without an entry in TERM_DOCS makes `python tools/main.py --only docs`
fail, so the documentation cannot silently fall behind the ontology.
"""

# term local name -> how the term shows up in an export (what the plugin writes, and when)
TERM_DOCS = {
    "Catalog": "One per export file. Groups the dataset(s) of that file; a place to hang institution-level metadata later.",
    "Dataset": "One per export run: title, licence and creator come from the three fields of the LOD Export tab, the issue date from the export time. `dct:subject` points to every mapped object, `dct:hasPart` to every layer, `dct:requires` to every vocabulary scheme the layers are bound to.",
    "Distribution": "Describes the Turtle file itself (media type, file name).",
    "MappedObject": "Created once per Object ID of the LOD Export tab. Also typed with the CRM class chosen in the dropdown (an E18 subclass).",
    "FeatureLayer": "One per QGIS layer that has an Object ID. Lists its features with `rdfs:member`, its configured annotation fields with `qskos:hasAttribute`, and its vocabulary bindings with `qskos:usesVocabulary`.",
    "Feature": "One per QGIS feature, annotated or not. Its IRI is built from the object ID, the layer name and the `uuid` column if the layer has one, else the QGIS feature id (stable only while the GeoPackage rows are not re-created).",
    "Geometry": "The feature's geometry as `geo:asWKT` with the CRS IRI in front of the WKT, plus the matching `sf:` type (Polygon, Point, ...). Written only for features that have a geometry.",
    "LocalCoordinateSystem": "Written only when the 'object-local coordinate system' box is ticked: one per layer. Without the box the layer's EPSG code is used as CRS IRI and no local CRS node is written.",
    "Annotation": "One per feature and annotation field that has a value. Several selected concepts in one cell become several `oa:hasBody` values on the same annotation. `dct:creator` is the creator field, `dct:created` the export time.",
    "FieldConcept": "A role, not something the plugin writes: every object of `qskos:attribute`. Defined for reasoners and documentation; it is never asserted on publisher IRIs.",
    "ValueConcept": "A role, not something the plugin writes: every object of `oa:hasBody` of a `qskos:Annotation`.",
    "attribute": "The annotation field (a concept IRI; in the plugin the layer's column name is that IRI).",
    "hasAttribute": "Layer schema: all configured fields, also those that have no annotation yet.",
    "usesVocabulary": "The concept schemes bound to the layer in the GeoPackage (`qskos_layer_config`).",
    "inCoordinateSystem": "Only in local-CRS exports: the explicit link from a geometry to its `qskos:LocalCoordinateSystem`.",
    "definedByRaster": "File name of the raster that defines the local CRS, if the adapter is given one (currently not filled by the UI).",
}

# (term shown, target, kind, note) rows of the crosswalk tables that are not plain rdfs:subClassOf
PROPERTY_BRIDGES = [
    ("oa:hasTarget", "crm:P140_assigned_attribute_to", "CONSTRUCT rule Q3",
     "The annotation's target is the feature that receives the attribute."),
    ("oa:hasBody", "crm:P141_assigned", "CONSTRUCT rule Q3",
     "The value concept that is assigned."),
    ("qskos:attribute", "crm:P177_assigned_property_of_type", "rdfs:subPropertyOf (ontology)",
     "The field concept says which kind of property is assigned."),
    ("dct:creator", "crm:P14_carried_out_by", "CONSTRUCT rule Q5",
     "Who made the annotation."),
    ("dct:created", "crm:P4_has_time-span / E52 Time-Span / P82_at_some_time_within", "CONSTRUCT rule Q5",
     "When the annotation was made (export time)."),
    ("dct:hasPart (Dataset to FeatureLayer)", "crm:P106_is_composed_of", "documentation only",
     "Both sides are E73 Information Object. Not materialised."),
    ("dct:subject (Dataset to MappedObject)", "crm:P67_refers_to", "documentation only",
     "Not materialised."),
    ("crm:P157_is_at_rest_relative_to (Feature to MappedObject)", "itself", "written directly",
     "The only CRM property that the export writes itself, because it places the E53 Place on the object."),
    ("geo:hasGeometry, rdfs:member, dcat:distribution", "no CRM property", "none",
     "GeoSPARQL and DCAT structure with no CRM counterpart; CRM does not need to see it."),
]

CROSSWALK_NOTES = [
    ("Why the crosswalk lives only in the ontology",
     "Exports stay small and readable: they use `qskos:` classes. Anyone who needs the CIDOC CRM, DCAT, GeoSPARQL or Web Annotation view loads `ontology/qskos.ttl` into the same store and entails `rdfs:subClassOf` (RDFS). SPARQLing Unicorn reads properties (`geo:hasGeometry`, `geo:asWKT`, `rdfs:member`), not classes, and needs no entailment."),
    ("Feature is an E53 Place, not an E26 Physical Feature",
     "A QSKOS feature is a region on a 2D derivative of the object, positioned relative to it (`crm:P157`). Typing it E26 would say that the polygon *is* the damage."),
    ("No CRMgeo SP6 on Feature",
     "In CRMgeo 1.2, SP6 Declarative Place is also a subclass of `geo:Geometry`; `geo:Feature` and `geo:Geometry` are disjoint in GeoSPARQL, so both together would be inconsistent under a reasoner."),
    ("Local coordinate systems",
     "`qskos:LocalCoordinateSystem` is a CRMgeo SP4 (itself an E29 Design or Procedure). The link `qskos:inCoordinateSystem` is a candidate for alignment with `crmgeo:Q9_is_expressed_in_terms_of` once SP5 is settled."),
    ("Bridges between foreign properties are rules, not axioms",
     "The ontology asserts `subClassOf` / `subPropertyOf` only for its own terms. Mapping `oa:hasTarget` to `crm:P140` would assert something about a W3C property from outside; it is therefore a SPARQL CONSTRUCT rule in `ontology/queries.rq`."),
    ("Open points",
     "The ontology namespace `http://archaeology.link/ontology/qskos#` is a placeholder; a w3id.org IRI would be persistent. The CRMgeo parents are checked against CRMgeo 1.2 and should be re-checked against the CRMbase 7.1.x harmonised release."),
]
