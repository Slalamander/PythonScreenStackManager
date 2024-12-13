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
        a.append(name)

__all__ = a

##Prints the list of registered color properties
_all_color_properties = list(colorproperty._found_properties)
