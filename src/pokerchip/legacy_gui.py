from importlib import import_module
import sys
sys.modules[__name__] = import_module('.ui.review_base', __package__)
