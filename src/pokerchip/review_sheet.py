from importlib import import_module
import sys
sys.modules[__name__] = import_module('.application.review_sheet', __package__)
