from importlib import import_module
import sys
sys.modules[__name__] = import_module('.application.demo', __package__)
