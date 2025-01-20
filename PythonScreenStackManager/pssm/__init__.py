"""Main handler for PSSM. Also takes care of ensuring imports are ordered correctly."""
import concurrent.futures

from .screen import PSSMScreen, const
from .styles import Style
from . import decorators

from ..elements import baseelements
from ..tools import Singleton

baseelements.Screen = PSSMScreen
decorators.Element = baseelements.Element
decorators.Style = Style

def get_screen():
    "Returns the screen instance"
    return PSSMScreen.get_screen()

def _reset():
    "Resets pssm"
    if hasattr(PSSMScreen,"_instance"):
        assert not PSSMScreen._instance.printing, "Resetting not allowed during printing"

    _reset_elt_class(baseelements.Element)
    ##Don't forget to reset Style stuff too.
    Style._color_shorthands = {}
    if hasattr(PSSMScreen,"_instance"):
        del PSSMScreen._instance
    PSSMScreen.generatorPool = concurrent.futures.ThreadPoolExecutor(None,const.GENERATOR_THREADPOOL)
    return

def _reset_elt_class(elt_cls: type[baseelements.Element]):
    
    for cls in elt_cls.__subclasses__():
        _reset_elt_class(cls)
        idattr = f"_{cls}__last_id"
        if hasattr(cls, idattr):
            setattr(cls, idattr, -1)
        
        if cls in Singleton._instances:
            Singleton._instances.pop(cls)