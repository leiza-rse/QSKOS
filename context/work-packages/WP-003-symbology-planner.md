# WP-003: Pure symbology rule planner, thin symbology tab

Status: draft

Tier: strong   ·   Depends on: WP-001   ·   Size: M

## Goal
The rules for the rule-based renderer are planned by a pure, unit-tested function; the tab only turns the plan into
`QgsRuleBasedRenderer.Rule` objects. `generate_rule_based_symbology` (226 lines) is gone.

## Read first
`context/adr/0003-field-value-domain.md`, `context/adr/0001-annotation-fields-json.md` § Decision; `qskos/tabs/symbology.py`,
`qskos/utils/hierarchy.py`; open question Q13.

## Tasks
1. `qskos/utils/symbology_rules.py` (no Qt/QGIS): dataclass `RuleSpec(label, filter_expression, colour_key, children, is_else)` and
   `plan_rules(fields, children_map, labels, present_values, field_types)` returning the rule tree. Contains: ancestor walk
   (polyhierarchy-safe), descendant sets, the array expression for JSON vs legacy text fields (`_field_array_expression` moves here).
2. Deterministic colours stay (`colour_key` = URI; the tab maps it to `QColor` via the existing hash).
3. `tabs/symbology.py`: collect inputs (via `bound_vocabularies` once WP-002 is done, else the current loop), call `plan_rules`,
   build renderer, show result. Each method ≤ 50 lines.
4. Apply the decision on Q13 (symbol-less group rules or not).

## Acceptance criteria
- `plan_rules` has unit tests for: leaf field, nested hierarchy, polyhierarchy, two fields from two vocabularies, legacy text field
  expression, field without values (no group).
- `TestWidgetToSymbology` (all parametrisations) passes unchanged.

## Tests required
`tests/test_symbology_rules.py` (pure); existing QGIS tests.

## Out of scope
Colour schemes / UI for choosing colours; changes to the value domain (ADR-0003).

## Human steps
Decide Q13. Look at the generated legend in QGIS desktop once.
