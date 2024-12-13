"""
Module containing the elements that can be used to build a UI for a PSSM screen.
Elements should only be defined after defining the screen instance, which can best be done via `set_screen_instance` in the base module. 
For the basics, see `Element`
"""

import inspect
import sys 

from .baseelements import * 
from .compoundelements import *
from .menuelements import *

from .deviceelements import *
from .layoutelements import *

a = []
for name, cls in inspect.getmembers(sys.modules[__name__], inspect.isclass):
    if __name__ in cls.__module__  and issubclass(cls,Element) and not inspect.isabstract(cls) and name[0] != "_": 
    # if (__name__ in cls.__module__  and issubclass(cls,Element)) or __name__ == "parse_layout_string": ##Use this when generating docs
        a.append(name)

__all__ = a

##Prints the list of registered color properties
_all_color_properties = list(colorproperty._found_properties)

__pdoc__ = {
    ##So apparently providing elements yields an error for some dumb reason, 
    ## since at some point an attribute name is passed as an object and not a string, but the error tells me nothing as to where that problem even lies
    "baseelements": False,
    "compoundelements": False,
    "menuelements": True,
    "deviceelements": True,
    "layoutelements": True,
    "inputelements": False,

    "Element": True,
    "_ElementSelect": True,
    "_TileBase": True,
    "_BaseSlider": False,
    "_BoolElement": False,
    "_IntervalUpdate": False,
    "parse_layout_string": True,
    "constants": True
    }