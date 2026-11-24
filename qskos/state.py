# state.py
# qskos QGIS Plugin - Shared state object
# The little state that is genuinely shared between tabs: the active GPKG, the
# feature layer selected in the Layer tab (Symbology acts on it), the import
# language and the hierarchy cache.  Which vocabulary's tree is displayed is
# private to the Layer tab (tabs/layer.py), not shared state.
#
# Pure Python (no QGIS import at module level) so it can be unit-tested.

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .utils.hierarchy import build_hierarchy_index
from .utils.gpkg import (
    VOCAB_PROPERTY, gpkg_path_from_source, norm_path,
    split_vocab_source_key, table_name_from_source,
)


@dataclass
class QskosState:
    # Path to the active GeoPackage (single source of truth).
    active_gpkg_path: Optional[str] = None
    # Feature layer currently selected in the Layer tab.
    current_feature_layer: Any = None
    # Import language for vocabularies.
    selected_language: str = "en"
    # (gpkg path, table name) -> (children_map, concept_labels).
    # Keyed by stable identifiers (not the volatile QGIS layer id), so the
    # cache survives project reloads and is shared across feature layers bound
    # to the same vocabulary.
    hierarchy_cache: Dict[Tuple[str, str], Tuple[dict, dict]] = field(default_factory=dict)

    @staticmethod
    def _vocab_key(vocab_layer):
        # In-memory vocab copies carry their GPKG table in a custom property
        # (ADR-0007); their source() says nothing about the GPKG.
        marker = getattr(vocab_layer, "customProperty", lambda *_: None)(VOCAB_PROPERTY)
        if marker:
            return split_vocab_source_key(marker)
        return (
            norm_path(gpkg_path_from_source(vocab_layer.source())),
            table_name_from_source(vocab_layer.source()),
        )

    def get_hierarchy_for_layer(self, vocab_layer):
        """
        Return (children_map, concept_labels) for vocab_layer, building and
        caching on first call. Keyed by (gpkg path, table name).
        """
        key = self._vocab_key(vocab_layer)
        if key not in self.hierarchy_cache:
            self.hierarchy_cache[key] = build_hierarchy_index(vocab_layer)
        return self.hierarchy_cache[key]

    def invalidate_vocab_cache(self, gpkg_path, table_name):
        """
        Drop the cached hierarchy for a vocabulary, e.g. after it is
        re-imported (which replaces its GPKG table).
        """
        self.hierarchy_cache.pop(
            (norm_path(gpkg_path), table_name), None
        )
