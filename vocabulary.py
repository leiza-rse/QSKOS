# vocabulary.py
# qskos QGIS Plugin - Vocabulary Tab Logic
# Handles loading SKOS sources, converting to layers, etc.

from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QPushButton, QLineEdit, QComboBox, QFileDialog, QLabel
)
from PyQt5.QtCore import Qt, QVariant
from qgis.core import QgsProject, QgsMapLayerProxyModel, QgsMapLayer
from qgis.gui import QgsMapLayerComboBox
from PyQt5.QtWidgets import QMessageBox, QInputDialog
import os

# Import utility functions from separate module
from .qskos_utils import (
    load_skos_source,
    convert_to_delimited_text_layer
)


class VocabularyManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.source_type_combo = None
        self.language_combo = None
        self.source_input = None
        self.load_vocab_button = None
        self.vocab_status_label = None
        
    def setup_vocab_tab(self):
        """Fully implemented Vocabulary Tab UI for loading SKOS sources."""
        layout = QFormLayout()

        # Source Type Selector
        self.source_type_combo = QComboBox()
        self.source_type_combo.addItems([
            "Local Turtle (.ttl)",
            "Local JSON-LD (.jsonld)",
            "Local CSV (.csv)",
            "Remote URL (Turtle/JSON-LD)"
        ])
        layout.addRow("Source Type:", self.source_type_combo)

        # Language Selector — NEW
        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "de"])
        self.language_combo.setCurrentText("en")
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        layout.addRow("Display Language:", self.language_combo)

        # Source Path/URL Input
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Enter file path or URL...")
        layout.addRow("Source:", self.source_input)

        # Browse Button (for local files)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_skos_file)
        layout.addRow("", browse_button)

        # Load Button
        self.load_vocab_button = QPushButton("Load Vocabulary")
        self.load_vocab_button.clicked.connect(self.on_load_vocab_clicked)
        layout.addRow("", self.load_vocab_button)

        # Status Label
        self.vocab_status_label = QLabel("Ready to load vocabulary.")
        layout.addRow("", self.vocab_status_label)

        vocab_tab = QWidget()
        vocab_tab.setLayout(layout)
        return vocab_tab

    def on_language_changed(self, lang):
        """Update selected language for display and storage."""
        self.plugin.selected_language = lang

    def browse_skos_file(self):
        """Open file dialog to select local SKOS file."""
        options = QFileDialog.Options()
        source_type = self.source_type_combo.currentIndex()

        if source_type == 0:  # TTL
            file_filter = "Turtle Files (*.ttl);;All Files (*)"
        elif source_type == 1:  # JSON-LD
            file_filter = "JSON-LD Files (*.jsonld);;All Files (*)"
        elif source_type == 2:  # CSV
            file_filter = "CSV Files (*.csv);;All Files (*)"
        else:  # URL — no file dialog
            return

        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select SKOS File", "", file_filter, options=options
        )
        if file_path:
            self.source_input.setText(file_path)

    def on_load_vocab_clicked(self):
        """Load and convert SKOS vocabulary based on user input."""
        source_text = self.source_input.text().strip()
        if not source_text:
            QMessageBox.warning(None, "Input Required", "Please enter a file path or URL.")
            return

        source_type_index = self.source_type_combo.currentIndex()
        source_type_map = {
            0: 'ttl',
            1: 'jsonld',
            2: 'csv',
            3: 'url'
        }
        source_type = source_type_map[source_type_index]

        try:
            # Load concepts — pass selected language for filtering
            concepts = load_skos_source(source_text, source_type, self.plugin.selected_language)

            if not concepts:
                raise ValueError("No concepts loaded from source.")

            # Extract or prompt for scheme URI
            scheme_uri = self.extract_or_prompt_scheme_uri(concepts, source_text)
            if not scheme_uri:
                return  # User canceled

            # Convert to layer — store only selected language's labels
            vocab_layer = convert_to_delimited_text_layer(concepts, scheme_uri, self.plugin.selected_language)

            # Success
            self.vocab_status_label.setText(f"✅ Loaded: {vocab_layer.name()}")
            QMessageBox.information(None, "Success", f"Vocabulary '{vocab_layer.name()}' loaded successfully.")

            # Refresh dropdowns to include new layer
            self.plugin.refresh_layer_combos()

        except Exception as e:
            self.vocab_status_label.setText("❌ Load failed.")
            QMessageBox.critical(None, "Load Error", f"Failed to load vocabulary:\n{str(e)}")
            import traceback
            traceback.print_exc()  # For debugging in QGIS log

    def extract_or_prompt_scheme_uri(self, concepts, source_hint=""):
        """Try to extract scheme URI from data, or prompt user."""
        # Try to get from first concept's inScheme
        for c in concepts:
            if c.get('skos:inScheme'):
                return c['skos:inScheme']

        # Fallback: use source as scheme (for CSV or URL)
        default_scheme = source_hint if source_hint else "http://example.org/scheme/unknown"

        scheme_uri, ok = QInputDialog.getText(
            None,
            "Enter Concept Scheme URI",
            "No skos:inScheme found. Please enter the Concept Scheme URI:",
            text=default_scheme
        )
        return scheme_uri if ok else None