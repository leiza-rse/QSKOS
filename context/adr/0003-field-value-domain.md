# ADR-0003: Field value domain = concept plus descendants

Status: accepted (2026-11-09, decided by the maintainer)

## Context
Originally an annotation field for concept C offered only C's narrower concepts, so a field on a leaf concept had nothing to select.

## Decision
The ValueRelation filter of a field for C lists C itself and all its descendants (`hierarchy.get_descendant_uris_fast`). The symbology group
rule of a field uses the same set. Any concept, including a leaf, can become a field.

## Consequences
Users can annotate with the general concept itself. Widget domain, symbology and export agree on which values belong to a field.
