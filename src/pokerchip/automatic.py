from importlib import import_module
import sys
sys.modules[__name__] = import_module('.application.automatic', __package__)
