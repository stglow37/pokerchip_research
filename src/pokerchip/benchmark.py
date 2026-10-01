from importlib import import_module
import sys
sys.modules[__name__] = import_module('.analysis.benchmark', __package__)
