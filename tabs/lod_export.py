# lod_export.py
# qskos QGIS Plugin - LOD Export Tab Logic
# Exports annotated features as Linked Open Data (Turtle): DCAT 3 metadata,
# GeoSPARQL geometries and Web Annotations (one qskos:Annotation per feature
# and annotation field: field concept → qskos:attribute, selected value
# concepts → oa:hasBody).  The model is built in utils/rdf_model.py.
#
# One form is shown per annotated feature layer (one object per layer).
# All layers can be exported together into a single Turtle; layers using the
# same object ID are merged automatically (same subject URI).
#
# Object namespace and annotation namespace use the plugin defaults and are
# not user-configurable.

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QScrollArea,
    QPushButton, QLabel, QLineEdit, QComboBox, QFileDialog, QMessageBox,
    QCheckBox
)
from qgis.core import QgsApplication, QgsProject, QgsMapLayer

from ..utils.lod import (
    export_lod_ttl, derive_prefix,
    DEFAULT_OBJECT_NAMESPACE, DEFAULT_ANNOTATION_NAMESPACE,
)
from ..utils.rdf_model import ExportMeta, DEFAULT_LICENSE
from ..utils.gpkg import (
    get_bound_vocab_schemes,
    get_vocab_entries, read_config, ROLE_VOCAB,
    find_vocab_table_for_scheme, ensure_vocab_layer_loaded,
    layer_gpkg_path, layer_table_name, norm_path,
)

# CIDOC CRM classes offered in the (editable) class dropdown.
# All are subclasses of crm:E18_Physical_Thing, because qskos:MappedObject is
# (CRM 7.1 spells them with a hyphen: E22_Human-Made_Object).
CRM_CLASSES = [
    "crm:E19_Physical_Object",
    "crm:E22_Human-Made_Object",
    "crm:E24_Physical_Human-Made_Thing",
    "crm:E25_Human-Made_Feature",
    "crm:E26_Physical_Feature",
    "crm:E20_Biological_Object",
    "crm:E21_Person",
    "crm:E18_Physical_Thing",
]

LICENSES = [
    DEFAULT_LICENSE,
    "https://creativecommons.org/licenses/by-sa/4.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
]


class LODExportManager:
    def __init__(self, plugin_instance):
        self.plugin            = plugin_instance
        self.tab_widget        = None
        self.namespace_input   = None
        self.title_input       = None
        self.license_input     = None
        self.creator_input     = None
        self.local_crs_check   = None
        self.forms_layout      = None
        self.export_btn        = None
        self.status_label      = None
        self.forms             = []   # list of per-layer form dicts

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_lod_tab(self):
        """Build and return the LOD export tab widget."""
        layout = QVBoxLayout()

        layout.addWidget(QLabel(
            "Export annotated features as Linked Open Data (Turtle).\n"
            "One object per layer — set an Object ID, Label and CRM class "
            "for each annotated layer."
        ))

        # Institution-specific object namespace (applies to all layers)
        self.namespace_input = QLineEdit(DEFAULT_OBJECT_NAMESPACE)
        self.namespace_input.setPlaceholderText("http://w3id.org/archlink/objects/")
        layout.addWidget(QLabel("Object Namespace:"))
        layout.addWidget(self.namespace_input)

        # Dataset metadata (DCAT) and provenance, applies to the whole export
        meta_box = QGroupBox("Dataset metadata (DCAT)")
        meta_form = QFormLayout(meta_box)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Condition mapping of O.34736")
        meta_form.addRow("Dataset title:", self.title_input)
        self.license_input = QComboBox()
        self.license_input.setEditable(True)
        self.license_input.addItems(LICENSES)
        meta_form.addRow("Licence (IRI):", self.license_input)
        self.creator_input = QLineEdit(self._default_creator())
        self.creator_input.setPlaceholderText("Name or ORCID/ROR IRI")
        meta_form.addRow("Creator:", self.creator_input)
        self.local_crs_check = QCheckBox(
            "Geometries are in an object-local coordinate system "
            "(not a geographic CRS)")
        meta_form.addRow(self.local_crs_check)
        layout.addWidget(meta_box)

        # Scrollable per-layer forms
        self.forms_layout = QVBoxLayout()
        forms_container = QWidget()
        forms_container.setLayout(self.forms_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(forms_container)
        layout.addWidget(scroll, 1)

        # Export-all button
        self.export_btn = QPushButton("Export All Layers to Turtle")
        self.export_btn.clicked.connect(self.on_export_all_clicked)
        layout.addWidget(self.export_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        tab = QWidget()
        tab.setLayout(layout)
        self.tab_widget = tab
        return tab

    # ── Form generation ────────────────────────────────────────────────────────

    def refresh_forms(self):
        """Rebuild one export form per annotated feature layer."""
        # Clear existing forms
        while self.forms_layout.count():
            item = self.forms_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.forms = []

        gpkg = self.plugin.active_gpkg_path
        if not gpkg:
            self._set_status("Select a GeoPackage first.")
            return

        feature_layers = self._feature_layers()
        if not feature_layers:
            self._set_status(
                "No feature layers from the active GeoPackage found in the "
                "project.\nLoad your layers from the GeoPackage first."
            )
            return

        concept_labels = self._collect_concept_labels()
        if not concept_labels:
            self._set_status(
                "No bound vocabularies found. Bind vocabularies in the "
                "Layer tab first."
            )
            return

        n_forms = 0
        for layer in feature_layers:
            annotation_fields = [
                f.name() for f in layer.fields() if f.name() in concept_labels
            ]
            if not annotation_fields:
                continue
            self.forms.append(self._build_layer_form(
                layer, annotation_fields
            ))
            n_forms += 1

        if n_forms == 0:
            self._set_status(
                "No annotation fields found matching any bound vocabulary. "
                "Check concepts in the Layer tab to create annotation fields "
                "first."
            )
        else:
            self._set_status(
                f"Found {n_forms} annotated layer(s). Set an Object ID, "
                "Label and CRM class for each, then export."
            )

    def _build_layer_form(self, layer, annotation_fields):
        """Create a group box with metadata inputs for one annotated layer."""
        box = QGroupBox(layer.name())
        form = QFormLayout(box)

        id_input = QLineEdit()
        id_input.setPlaceholderText("e.g. O.34736")
        form.addRow("Object ID:", id_input)

        label_input = QLineEdit()
        label_input.setPlaceholderText("e.g. Lederschuh")
        form.addRow("Object Label:", label_input)

        class_combo = QComboBox()
        class_combo.setEditable(True)
        class_combo.addItems(CRM_CLASSES)
        class_combo.setCurrentText(CRM_CLASSES[0])
        form.addRow("CRM Class:", class_combo)

        # Per-layer export button
        export_row = QHBoxLayout()
        export_btn = QPushButton("Export This Layer…")
        export_btn.clicked.connect(
            lambda checked=False, l=layer, f=annotation_fields,
                   i=id_input, lb=label_input, c=class_combo:
                self._export_one_layer(l, f, i, lb, c)
        )
        export_row.addWidget(export_btn)
        form.addRow(export_row)

        self.forms_layout.addWidget(box)

        return {
            "layer":             layer,
            "annotation_fields": annotation_fields,
            "id_widget":         id_input,
            "label_widget":      label_input,
            "class_widget":      class_combo,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _default_creator():
        """QGIS user name (profile full name, else login name)."""
        try:
            return (QgsApplication.userFullName()
                    or QgsApplication.userLoginName() or "")
        except Exception:
            return ""

    def _export_meta(self):
        """ExportMeta from the metadata box, or None (with a warning) if invalid."""
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(None, "Input Required",
                "Please enter a dataset title.")
            return None
        return ExportMeta(
            title=title,
            creator=self.creator_input.text().strip(),
            license=self.license_input.currentText().strip(),
            local_crs=self.local_crs_check.isChecked(),
        )

    def _set_status(self, text):
        if self.status_label:
            self.status_label.setText(text)

    def _feature_layers(self):
        """All vector feature layers from the active GeoPackage."""
        gpkg = self.plugin.active_gpkg_path
        if not gpkg:
            return []
        vocab_table_names = {
            r["layer_name"]
            for r in read_config(gpkg)
            if r["layer_role"] == ROLE_VOCAB
        }
        layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != QgsMapLayer.VectorLayer:
                continue
            if layer_table_name(layer) in vocab_table_names:
                continue
            if norm_path(layer_gpkg_path(layer)) != norm_path(gpkg):
                continue
            layers.append(layer)
        return layers

    def _collect_concept_labels(self):
        """Map concept URI → label across all bound vocabularies in the GPKG."""
        concept_labels = {}
        seen_schemes = set()
        for r in read_config(self.plugin.active_gpkg_path):
            if r["layer_role"] == ROLE_VOCAB and r["scheme_uri"] not in seen_schemes:
                seen_schemes.add(r["scheme_uri"])
                table_name = find_vocab_table_for_scheme(
                    self.plugin.active_gpkg_path, r["scheme_uri"]
                )
                if not table_name:
                    continue
                try:
                    vocab_layer = ensure_vocab_layer_loaded(
                        self.plugin.active_gpkg_path, table_name
                    )
                    _, labels = self.plugin.get_hierarchy_for_layer(vocab_layer)
                    concept_labels.update(labels)
                except Exception as e:
                    print(f"[qskos] LOD export: skipping vocab: {e}")
                    continue
        return concept_labels

    def _vocab_prefixes(self):
        return {
            v["scheme_uri"]: derive_prefix(v["scheme_uri"])
            for v in get_vocab_entries(self.plugin.active_gpkg_path)
        }

    def _layer_schemes(self, layer):
        """Vocabulary schemes bound to this layer in the GeoPackage."""
        try:
            return get_bound_vocab_schemes(
                self.plugin.active_gpkg_path, layer_table_name(layer))
        except Exception:
            return []

    def _object_namespace(self):
        """Return the object namespace, or warn and return None if empty."""
        ns = self.namespace_input.text().strip() if self.namespace_input else ""
        if not ns:
            QMessageBox.warning(None, "Input Required",
                "Please enter an object namespace.")
            return None
        return ns

    def _form_spec(self, form):
        """Build a graph spec dict from a form, or None if Object ID is empty."""
        object_id = form["id_widget"].text().strip()
        if not object_id:
            return None
        return {
            "layer":             form["layer"],
            "annotation_fields": form["annotation_fields"],
            "object_id":         object_id,
            "object_label":      form["label_widget"].text().strip(),
            "object_type":       form["class_widget"].currentText().strip(),
            "vocab_schemes":     self._layer_schemes(form["layer"]),
        }

    # ── UI callbacks ───────────────────────────────────────────────────────────

    def _export_one_layer(self, layer, annotation_fields,
                          id_input, label_input, class_combo):
        """Export a single layer as its own object to a user-chosen file."""
        object_id = id_input.text().strip()
        if not object_id:
            QMessageBox.warning(None, "No Object ID",
                f"Enter an Object ID for layer '{layer.name()}' first.")
            return
        object_namespace = self._object_namespace()
        if not object_namespace:
            return
        meta = self._export_meta()
        if meta is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            None, f"Save LOD for {layer.name()}", "",
            "Turtle Files (*.ttl);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".ttl"):
            path += ".ttl"

        spec = {
            "layer":             layer,
            "annotation_fields": annotation_fields,
            "object_id":         object_id,
            "object_label":      label_input.text().strip(),
            "object_type":       class_combo.currentText().strip(),
            "vocab_schemes":     self._layer_schemes(layer),
        }
        try:
            n = export_lod_ttl(
                path, [spec], object_namespace, self._vocab_prefixes(), meta
            )
        except Exception as e:
            self._set_status("❌ Export failed.")
            QMessageBox.critical(None, "Export Error",
                f"Failed to export LOD:\n{str(e)}")
            import traceback
            traceback.print_exc()
            return
        self._set_status(f"✅ Exported {n} feature(s) to {os.path.basename(path)}")
        QMessageBox.information(None, "Success",
            f"Exported {n} feature(s) as Linked Open Data to:\n{path}")

    def on_export_all_clicked(self):
        """Export all layers with an Object ID into one Turtle file."""
        if not self.plugin.active_gpkg_path:
            QMessageBox.warning(None, "No GeoPackage", "No active GeoPackage.")
            return

        specs = []
        skipped = 0
        for form in self.forms:
            spec = self._form_spec(form)
            if spec is None:
                skipped += 1
                continue
            specs.append(spec)

        if not specs:
            QMessageBox.warning(None, "No Object ID",
                "No layers have an Object ID set.\n"
                "Enter an Object ID for at least one layer before exporting.")
            return

        object_namespace = self._object_namespace()
        if not object_namespace:
            return
        meta = self._export_meta()
        if meta is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            None, "Save All Layers as LOD", "",
            "Turtle Files (*.ttl);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".ttl"):
            path += ".ttl"

        try:
            n = export_lod_ttl(
                path, specs, object_namespace, self._vocab_prefixes(), meta
            )
        except Exception as e:
            self._set_status("❌ Export failed.")
            QMessageBox.critical(None, "Export Error",
                f"Failed to export LOD:\n{str(e)}")
            import traceback
            traceback.print_exc()
            return

        msg = f"Exported {n} feature(s) from {len(specs)} layer(s)."
        if skipped:
            msg += f"\n{skipped} layer(s) skipped (no Object ID)."
        self._set_status(
            f"✅ {msg} → {os.path.basename(path)}"
        )
        QMessageBox.information(None, "Success", f"{msg}\n\n{path}")
