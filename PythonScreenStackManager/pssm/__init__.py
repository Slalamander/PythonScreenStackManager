"""Main handler for PSSM. Also takes care of ensuring imports are ordered correctly."""
import sys

from .screen import PSSMScreen
from .styles import Style
from . import util

from ..elements import baseelements
from ..tools import Singleton

baseelements.Screen = PSSMScreen
util.Element = baseelements.Element
util.Style = Style

def get_screen():
    "Returns the screen instance"
    return PSSMScreen.get_screen()

def _reset():
    "Resets pssm"

    assert not PSSMScreen._instance.printing, "Resetting not allowed during printing"

    _reset_elt_class(baseelements.Element)
    ##Don't forget to reset Style stuff too.
    del PSSMScreen._instance
    return

def _reset_elt_class(elt_cls: type[baseelements.Element]):
    
    for cls in elt_cls.__subclasses__():
        _reset_elt_class(cls)
        idattr = f"_{cls}__last_id"
        if hasattr(cls, idattr):
            setattr(cls, idattr, -1)
        
        if cls in Singleton._instances:
            Singleton._instances.pop(cls)