from importlib import import_module
import sys
sys.modules[__name__] = import_module('.core.migration', __package__)
