# vocabulary.py
# qskos QGIS Plugin - Vocabulary Tab Logic
# Imports SKOS sources into the active GeoPackage as attribute tables.

import os

from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QPushButton, QLineEdit, QComboBox,
    QFileDialog, QLabel, QMessageBox, QInputDialog
)

from .skos import load_skos_source
from .gpkg import (
    import_vocab_to_gpkg,
    ensure_vocab_layer_loaded,
    scheme_exists_in_gpkg,
    get_vocab_entries,
)


class VocabularyManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.source_type_combo  = None
        self.language_combo     = None
        self.source_input       = None
        self.load_vocab_button  = None
        self.vocab_status_label = None

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_vocab_tab(self):
        """Build and return the Vocabulary import tab widget."""
        layout = QFormLayout()

        self.source_type_combo = QComboBox()
        self.source_type_combo.addItems([
            "Local Turtle (.ttl)",
            "Local JSON-LD (.jsonld)",
            "Local CSV (.csv)",
            "Remote URL (Turtle/JSON-LD)",
        ])
        layout.addRow("Source Type:", self.source_type_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "de"])
        self.language_combo.setCurrentText("en")
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        layout.addRow("Language:", self.language_combo)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Enter file path or URL…")
        layout.addRow("Source:", self.source_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_skos_file)
        layout.addRow("", browse_btn)

        self.load_vocab_button = QPushButton("Load into GeoPackage")
        self.load_vocab_button.clicked.connect(self.on_load_vocab_clicked)
        self.load_vocab_button.setEnabled(False)   # enabled once a GPKG is selected
        layout.addRow("", self.load_vocab_button)

        self.vocab_status_label = QLabel("Select a GeoPackage first.")
        layout.addRow("", self.vocab_status_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── Called by GeopackageManager when a GPKG is loaded ─────────────────────

    def on_gpkg_selected(self):
        """Enable the import button now that a GPKG is available."""
        if self.load_vocab_button:
            self.load_vocab_button.setEnabled(True)
        if self.vocab_status_label:
            self.vocab_status_label.setText("Ready to import.")

    # ── UI callbacks ───────────────────────────────────────────────────────────

    def _on_language_changed(self, lang):
        self.plugin.selected_language = lang

    def browse_skos_file(self):
        """Open a file dialog to pick a local SKOS source file."""
        filters = {
            0: "Turtle Files (*.ttl);;All Files (*)",
            1: "JSON-LD Files (*.jsonld);;All Files (*)",
            2: "CSV Files (*.csv);;All Files (*)",
        }
        idx = self.source_type_combo.currentIndex()
        if idx not in filters:
            return
        path, _ = QFileDialog.getOpenFileName(
            None, "Select SKOS File", "", filters[idx]
        )
        if path:
            self.source_input.setText(path)

    def on_load_vocab_clicked(self):
        """Parse the SKOS source and import it into the active GeoPackage."""
        if not self.plugin.active_gpkg_path:
            QMessageBox.warning(None, "No GeoPackage",
                "Please select a GeoPackage in the GeoPackage tab first.")
            return

        source_text = self.source_input.text().strip()
        if not source_text:
            QMessageBox.warning(None, "Input Required",
                "Please enter a file path or URL.")
            return

        source_type_map = {0: "ttl", 1: "jsonld", 2: "csv", 3: "url"}
        source_type = source_type_map.get(
            self.source_type_combo.currentIndex(), "ttl"
        )

        try:
            concepts = load_skos_source(
                source_text, source_type, self.plugin.selected_language
            )
            if not concepts:
                raise ValueError("No concepts loaded from source.")

            scheme_uri = self.extract_or_prompt_scheme_uri(concepts, source_text)
            if not scheme_uri:
                return   # user cancelled

            # Import guard — confirm before replacing an existing vocab
            if scheme_exists_in_gpkg(self.plugin.active_gpkg_path, scheme_uri):
                reply = QMessageBox.question(
                    None, "Vocabulary Already Exists",
                    f"A vocabulary for\n'{scheme_uri}'\nalready exists in this "
                    f"GeoPackage.\n\nReplace it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

            table_name = import_vocab_to_gpkg(
                concepts,
                scheme_uri,
                self.plugin.selected_language,
                self.plugin.active_gpkg_path,
            )
            # Load the new table into the project so ValueRelation can reference it
            ensure_vocab_layer_loaded(self.plugin.active_gpkg_path, table_name)

            self.vocab_status_label.setText(f"✅ Imported: {table_name}")
            QMessageBox.information(None, "Success",
                f"Vocabulary '{table_name}' imported into GeoPackage.")

            # Refresh the GeoPackage tab vocab list and layer combos
            self.plugin.geopackage_manager.refresh_vocab_list()
            self.plugin.layer_manager.refresh_layer_combos()

        except Exception as e:
            self.vocab_status_label.setText("❌ Import failed.")
            QMessageBox.critical(None, "Import Error",
                f"Failed to import vocabulary:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def extract_or_prompt_scheme_uri(self, concepts, source_hint=""):
        """Extract the scheme URI from the concept list, or prompt the user."""
        for c in concepts:
            if c.get("inScheme"):
                return c["inScheme"]

        default = source_hint if source_hint else "http://example.org/scheme/unknown"
        scheme_uri, ok = QInputDialog.getText(
            None, "Enter Concept Scheme URI",
            "No inScheme found. Please enter the Concept Scheme URI:",
            text=default,
        )
        return scheme_uri if ok else None