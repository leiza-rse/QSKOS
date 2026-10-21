# state.py
# qskos QGIS Plugin - Shared state object
# Typed, explicit cross-tab state passed to managers, replacing the ad-hoc
# mutable attributes that previously lived directly on the plugin object
# (current_feature_layer, current_vocab_layer, current_vocab_scheme, ...).
# Making these explicit fields of a single object — instead of three globals
# that any tab could clobber — is what fixes the multi-layer binding bug
# (assessment items D/M).
#
# Pure Python (no QGIS import at module level) so it can be unit-tested.

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .utils.hierarchy import build_hierarchy_index
from .utils.gpkg import (
    gpkg_path_from_source, table_name_from_source, norm_path,
)


@dataclass
class QskosState:
    # Path to the active GeoPackage (single source of truth).
    active_gpkg_path: Optional[str] = None
    # Feature layer currently selected in the Layer tab.
    current_feature_layer: Any = None
    # Vocab layer currently shown in the concept tree.
    current_vocab_layer: Any = None
    # scheme_uri of the vocabulary currently shown in the tree.
    current_vocab_scheme: Optional[str] = None
    # Import language for vocabularies.
    selected_language: str = "en"
    # (gpkg path, table name) -> (children_map, concept_labels).
    # Keyed by stable identifiers (not the volatile QGIS layer id), so the
    # cache survives project reloads and is shared across feature layers bound
    # to the same vocabulary.
    hierarchy_cache: Dict[Tuple[str, str], Tuple[dict, dict]] = field(default_factory=dict)

    @staticmethod
    def _vocab_key(vocab_layer):
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
