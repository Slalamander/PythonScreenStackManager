
import logging
from typing import TYPE_CHECKING

from .. import tools
from ..pssm_types import *
from ..constants import PSSM_COLORS


if TYPE_CHECKING:
    from ..elements import Element
    from .screen import PSSMScreen

logger = logging.getLogger(__name__)

SHORTHAND_COLORS = PSSM_COLORS.copy()

__invalidcolor = object()

##linking to a style: any string starting and ending with a ':' (think about using that one, yaml does start complaining about nested mappings with it unless explicitly setting it to a string)
##i.e. ':style:' would apply the default style value said property
##Maybe also allow style identifiers like ':success:' etc like ttkbootstrap does
## ':style:[ELEMENTCLASS]:[STYLEPROPERTY]' and use mro's to cascade down
##Could even intercept the default values from the __init__'s to automatically create the defaults?
##Maybe; also give elements a styleDefaults property e.g. that can be used to set up the defaults.
##Also add an export function to create style.json/style.yaml

class Style:
    """Handles styling and theming of Elements
    _summary_

    Returns
    -------
    _type_
        _description_
    """

    screen: "PSSMScreen"
    _color_shorthands: dict[str,ColorType] = {}

    @classproperty
    def shorthand_colors(cls):
        return SHORTHAND_COLORS | cls._color_shorthands
    
    @classproperty
    def NOTACOLOR(cls):
        """Unique value that can be used to test colors without relying on booleans
        

        Example
        ---------

        .. code-block::

            is_valid_color(colors.get("my_color",NOTACOLOR))
            
        Will always return ``False``, whereas for example ``None`` is a valid color value.
        """
        return __invalidcolor

    @classmethod
    def get_color(cls, value: ColorType, colormode: str = "screen-image"):
        if colormode == "screen-image":
            colormode = cls.screen.imgMode
        elif colormode == "screen":
            colormode = cls.screen.colorMode
        
        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            return cls.shorthand_colors[value.lower()]
        else:
            try:
                return tools.get_Color(value,colormode)
            except (ValueError,TypeError):
                return "black"
            
    @classmethod
    def contrast_color(cls, value, mode):
        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            value = cls.shorthand_colors[value.lower()]
        
        return tools.contrast_color(value, mode)
            
    @classmethod
    def is_valid_color(cls, value: ColorType, element : "Element" = None) -> bool:
        """Returns whether the provided value is a valid value for a color property

        Tests if the supplied color is valid (i.e. can be processed by get_Color). 
        Returns True if color is valid, otherwise False. Does not raise errors.

        Parameters
        ----------
        color : ColorType
            color to test


        Returns
        -------
        bool
            Whether the color is valid
        """
        if element and isinstance(value,str):
            if element.parentLayout == None and not element in element.screen.stack:
                return True
            elif value in getattr(element.parentLayout,"_color_shorthands",{}):
                return True

        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            return True
        else:
            return tools.is_valid_Color(value)
        return

    @classmethod
    def add_color_shorthand(cls, **kwargs: ColorType):
        shorthands = cls.shorthand_colors
        for col_name, color in kwargs.items():
            if col_name in shorthands:
                logger.error(f"{col_name} is already registered as a shorthand color")
                continue
            if not tools.is_valid_Color(color):
                logger.error(f"color {color} with shorthand {col_name} is not a valid color value")
                continue
            cls._color_shorthands[col_name] = color
    ##Setting up a color property:
    ##pass as style (identifier)-color-subclass-class


