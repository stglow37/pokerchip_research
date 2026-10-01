from importlib import import_module
import sys
sys.modules[__name__] = import_module('..models.physics.ifr', __package__)
