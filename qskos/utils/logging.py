# logging.py
# qskos QGIS Plugin - Logging helper
# Thin wrapper over QGIS's QgsMessageLog so the plugin logs failures with
# context instead of swallowing them silently or using print().

from qgis.core import QgsMessageLog

TAG = "qskos"
LEVEL_INFO = 0
LEVEL_WARNING = 1
LEVEL_CRITICAL = 2


def log(message, level=LEVEL_INFO, tag=TAG):
    """Write a message to the QGIS message log."""
    QgsMessageLog.logMessage(str(message), tag, level)
