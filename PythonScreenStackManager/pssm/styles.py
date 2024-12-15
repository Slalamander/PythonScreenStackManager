
import logging
from typing import TYPE_CHECKING
from typing import Generic, Callable, Any

from .. import tools
from ..pssm_types import *
from ..constants import SHORTHAND_FONTS, SHORTHAND_ICONS, PSSM_COLORS


if TYPE_CHECKING:
    from ..elements import Element
    from .screen import PSSMScreen

logger = logging.getLogger(__name__)

SHORTHAND_COLORS = PSSM_COLORS.copy()

def add_colors(**kwargs: ColorType):
    for col_name, color in kwargs.items():
        if col_name in SHORTHAND_COLORS:
            logger.error(f"{col_name} is already registered as a shorthand color")
            continue
        if not tools.is_valid_Color(color):
            logger.error(f"color {color} with shorthand {col_name} is not a valid color value")
            continue
        SHORTHAND_COLORS[col_name] = color



class Style:
    """Handles styling and theming of Elements
    _summary_

    Returns
    -------
    _type_
        _description_
    """

    screen: "PSSMScreen"

    @classmethod
    def get_color(cls, value: ColorType, colormode: str = "screen-image"):
        if colormode == "screen-image":
            colormode = cls.screen.imgMode
        elif colormode == "screen":
            colormode = cls.screen.colorMode
        
        if isinstance(value,str) and value.lower() in SHORTHAND_COLORS:
            return SHORTHAND_COLORS[value.lower()]
        else:
            try:
                return tools.get_Color(value,colormode)
            except (ValueError,TypeError):
                return "black"
            
    @classmethod
    def contrast_color(cls, value, mode):
        if isinstance(value,str) and value.lower() in SHORTHAND_COLORS:
            value = SHORTHAND_COLORS[value.lower()]
        
        return tools.contrast_color(value, mode)
            
    @classmethod
    def is_valid_color(cls, value: ColorType) -> bool:
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
        if isinstance(value,str) and value.lower() in SHORTHAND_COLORS:
            return True
        else:
            return tools.is_valid_Color(value)
        return

    ##Setting up a color property:
    ##pass as style (identifier)-color-subclass-class


