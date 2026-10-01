from importlib import import_module
import sys
sys.modules[__name__] = import_module('.ui.main_window', __package__)
