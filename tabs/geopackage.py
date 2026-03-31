# geopackage.py
# qskos QGIS Plugin - GeoPackage Tab Logic
# Handles GeoPackage selection and displays registered vocabularies.
# This tab must be completed before the other tabs are functional.

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog
)

from ..utils.gpkg import ensure_config_table, get_vocab_entries


class GeopackageManager:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.gpkg_path_label  = None
        self.vocab_list_widget = None
        self.status_label     = None

    # ── Tab setup ──────────────────────────────────────────────────────────────

    def setup_geopackage_tab(self):
        """Build and return the GeoPackage selection tab widget."""
        layout = QVBoxLayout()

        # GPKG selector row
        select_row = QHBoxLayout()
        select_btn = QPushButton("Select GeoPackage…")
        select_btn.clicked.connect(self.on_select_gpkg_clicked)
        select_row.addWidget(select_btn)

        self.gpkg_path_label = QLabel("No GeoPackage selected.")
        self.gpkg_path_label.setWordWrap(True)
        select_row.addWidget(self.gpkg_path_label, 1)
        layout.addLayout(select_row)

        # Registered vocabularies list (read-only — import is in the Vocabulary tab)
        layout.addWidget(QLabel("<b>Vocabularies in this GeoPackage</b>"))
        self.vocab_list_widget = QListWidget()
        self.vocab_list_widget.setMaximumHeight(120)
        self.vocab_list_widget.setEnabled(False)
        layout.addWidget(self.vocab_list_widget)

        self.status_label = QLabel("Select a GeoPackage to begin.")
        layout.addWidget(self.status_label)

        layout.addStretch()
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    # ── GPKG selection ─────────────────────────────────────────────────────────

    def on_select_gpkg_clicked(self):
        """Open a file dialog to pick a GeoPackage."""
        path, _ = QFileDialog.getOpenFileName(
            None, "Select GeoPackage", "",
            "GeoPackage Files (*.gpkg);;All Files (*)"
        )
        if path:
            self.load_gpkg(path)

    def load_gpkg(self, path):
        """
        Set the active GeoPackage, initialise the config table, and refresh
        all tabs.  Called both from the file dialog and from project-restore.
        """
        if not os.path.exists(path):
            if self.status_label:
                self.status_label.setText(f"❌ File not found: {path}")
            return

        self.plugin.active_gpkg_path = path
        ensure_config_table(path)
        self.refresh_vocab_list()

        # Persist path in the QGIS project file for restore on next open
        from qgis.core import QgsProject
        QgsProject.instance().writeEntry("qskos", "active_gpkg", path)

        # Notify other tabs
        self.plugin.vocabulary_manager.on_gpkg_selected()
        self.plugin.layer_manager.refresh_layer_combos()

        short = os.path.basename(path)
        if self.gpkg_path_label:
            self.gpkg_path_label.setText(path)
        n = self.vocab_list_widget.count() if self.vocab_list_widget else 0
        if self.status_label:
            self.status_label.setText(
                f"✅ {short} — {n} vocabular{'y' if n == 1 else 'ies'} found."
            )

    # ── Vocab list refresh ─────────────────────────────────────────────────────

    def refresh_vocab_list(self):
        """Repopulate the vocabulary list from the active GPKG config table."""
        if self.vocab_list_widget is None:
            return
        self.vocab_list_widget.clear()

        if not self.plugin.active_gpkg_path:
            self.vocab_list_widget.setEnabled(False)
            return

        entries = get_vocab_entries(self.plugin.active_gpkg_path)
        for entry in entries:
            lang = entry.get("language") or "?"
            text = f"{entry['layer_name']}  [{lang}]  —  {entry['scheme_uri']}"
            self.vocab_list_widget.addItem(QListWidgetItem(text))

        self.vocab_list_widget.setEnabled(True)

        # Update status count
        n = self.vocab_list_widget.count()
        if self.status_label and self.plugin.active_gpkg_path:
            short = os.path.basename(self.plugin.active_gpkg_path)
            self.status_label.setText(
                f"✅ {short} — {n} vocabular{'y' if n == 1 else 'ies'} found."
            )
