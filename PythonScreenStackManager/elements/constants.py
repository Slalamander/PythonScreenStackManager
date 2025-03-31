"""
Constants and type hints for the PSSM element library
Seperate file to decrease clutter
"""
from typing import TypedDict, Literal, Optional, Union
from pathlib import Path
import logging

from ..pssm_types import *
from ..constants import INKBOARD, PATH_TO_PSSM, \
    SHORTHAND_FONTS, SHORTHAND_ICONS, ROOT_STYLE_SUFFIX

logger = logging.getLogger(__name__)

from ..constants import RAISE

#region general constants
CURSOR_CHAR: str  = "|"

##May need to move this to types?
ALLOWED_BADGE_SETTINGS : tuple = ("background_color", "icon_color", "location", "relSize", "offset")
"Settings allowed for badges"
#endregion

#region configurable constants
DEFAULT_MENU_HEADER_COLOR : ColorType =  "header" + ROOT_STYLE_SUFFIX
"Default color for the header part of menu popups"

DEFAULT_MENU_BUTTON_COLOR : ColorType = "grey11"
"Default color for menu buttons"

DEFAULT_FOREGROUND_COLOR : ColorType = "foreground" + ROOT_STYLE_SUFFIX #"black"
"Default color for foreground parts of elements (e.g. text)"

DEFAULT_ACCENT_COLOR : ColorType = "accent" + ROOT_STYLE_SUFFIX #"gray"
"Default color for (Tile) accents"

DEFAULT_BACKGROUND_COLOR : ColorType = "background" + ROOT_STYLE_SUFFIX #"white"
"Default color for backgrounds, Taken as the color of an empty screen."

DEFAULT_ACTIVE_COLOR : ColorType = "active" + ROOT_STYLE_SUFFIX

DEFAULT_INACTIVE_COLOR : ColorType = "inactive" + ROOT_STYLE_SUFFIX

class DEFAULTCOLORS:
    FOREGROUND = DEFAULT_FOREGROUND_COLOR
    BACKGROUND = DEFAULT_BACKGROUND_COLOR
    ACCENT = DEFAULT_ACCENT_COLOR

    ACTIVE = DEFAULT_ACTIVE_COLOR
    INACTIVE = DEFAULT_INACTIVE_COLOR

    HEADER = DEFAULT_MENU_HEADER_COLOR

DEFAULT_BLUR_POPUP_BACKGROUND : bool = True
"Default setting to indicate whether to blur the background when showing a popup"

DEFAULT_FONT = SHORTHAND_FONTS["default"]
"The default font"

DEFAULT_FONT_BOLD: str  = SHORTHAND_FONTS['default-bold']
"Default bold font"

DEFAULT_FONT_CLOCK : str = "clock" #SHORTHAND_FONTS['clock']
"Default font for digital clocks"

DEFAULT_FONT_HEADER : str = 'header'

DEFAULT_FONT_SIZE: str  = "H*0.036"
"Default size used for fonts"

DEFAULT_ICON : str  = "mdi:sticker-outline"
"Default icon to use when none is defined"

MISSING_ICON : str  = "mdi:sticker-remove-outline"
"Icon to use when an icon/image is specified that cannot be found"

MISSING_PICTURE_ICON : str = "mdi:file-image-remove"

SHORTHAND_ICONS["default"] = DEFAULT_ICON
SHORTHAND_ICONS["missing"] = MISSING_ICON

DEFAULT_BADGE_LOCATION : BadgeLocationType = "LR"
"Default location for badges"

DEFAULT_BATTERY_STYLE : BatteryIconMapping = BatteryIconMapping(default={},full={},charging={},discharging={})
"The default style for device battery icons"

DEFAULT_NETWORK_STYLE : Literal["lines","signal"] = "lines"
"Default style for device network icons"
#endregion
