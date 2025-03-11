from .analyzer import ResultsAnalyzer
from .visualizer import ResultsVisualizer
from .injecter import FaultInjecter
from .parser import ResultsParser
from .sql_converter import ResultsDBConverter
from .utils.candaguardia import CanDaGuardia
from .benchmark_classifier import BenchmarkClassifierInterface

__all__ = [
    'ResultsAnalyzer',
    'ResultsVisualizer', 
    'FaultInjecter',
    'ResultsParser',
    'ResultsDBConverter',
    'CanDaGuardia',
    'BenchmarkClassifierInterface'
]

# Package metadata
__version__ = '0.1.0'
__author__ = 'Simone Tollardo'
__email__ = 'tollsimy.dev@protonmail.com'
