from qgis.core import QgsProcessingProvider
from .qskos_algorithm import qskosAlgorithm

class qskosProvider(QgsProcessingProvider):

    def __init__(self):
        super().__init__()

    def loadAlgorithms(self):
        """Loads all algorithms belonging to this provider."""
        self.addAlgorithm(qskosAlgorithm())

    def id(self):
        return "qskos"

    def name(self):
        return "qskos"

    def longName(self):
        return self.name()