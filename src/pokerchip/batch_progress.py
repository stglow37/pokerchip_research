from importlib import import_module
import sys
sys.modules[__name__] = import_module('.application.batch_progress', __package__)
