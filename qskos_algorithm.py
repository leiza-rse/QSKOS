from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingOutputVectorLayer
)
from qgis import processing

class qskosAlgorithm(QgsProcessingAlgorithm):
    """Dummy algorithm to satisfy Processing framework until UI is ready."""

    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def createInstance(self):
        return qskosAlgorithm()

    def name(self):
        return 'qskos_algorithm'

    def displayName(self):
        return 'qskos Algorithm'

    def group(self):
        return 'qskos'

    def groupId(self):
        return 'qskos'

    def shortHelpString(self):
        return "This is a placeholder."

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString(
                self.INPUT,
                'Input parameter'
            )
        )

        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT,
                'Output layer'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # This is a stub. The real work is done in the main plugin UI.
        return {self.OUTPUT: None}