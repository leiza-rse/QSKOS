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
    # vocab layer id -> (children_map, concept_labels).
    hierarchy_cache: Dict[str, Tuple[dict, dict]] = field(default_factory=dict)

    def get_hierarchy_for_layer(self, vocab_layer):
        """
        Return (children_map, concept_labels) for vocab_layer, building and
        caching on first call. Keyed by layer id.
        """
        layer_id = vocab_layer.id()
        if layer_id not in self.hierarchy_cache:
            self.hierarchy_cache[layer_id] = build_hierarchy_index(vocab_layer)
        return self.hierarchy_cache[layer_id]
