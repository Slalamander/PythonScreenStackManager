"""
Constants and type hints for the PSSM element library
Seperate file to decrease clutter
"""
from typing import TypedDict, Literal, Optional, Union
from pathlib import Path
import logging

from ..pssm_types import *
from ..constants import INKBOARD, PATH_TO_PSSM, SHORTHAND_FONTS, SHORTHAND_ICONS

logger = logging.getLogger(__name__)

from ..constants import RAISE

#region general constants
CURSOR_CHAR: str  = "|"

##May need to move this to types?
ALLOWED_BADGE_SETTINGS : tuple = ("background_color", "icon_color", "location", "relSize", "offset")
"Settings allowed for badges"
#endregion

#region configurable constants
DEFAULT_MENU_HEADER_COLOR : ColorType =  "steelblue"
"Default color for the header part of menu popups"

DEFAULT_MENU_BUTTON_COLOR : ColorType = "grey11"
"Default color for menu buttons"

DEFAULT_FOREGROUND_COLOR : ColorType = "black"
"Default color for foreground parts of elements (e.g. text)"

DEFAULT_ACCENT_COLOR : ColorType = "gray"
"Default color for (Tile) accents"

DEFAULT_BACKGROUND_COLOR : ColorType = "white"
"Default color for backgrounds, Taken as the color of an empty screen."


DEFAULT_BLUR_POPUP_BACKGROUND : bool = True
"Default setting to indicate whether to blur the background when showing a popup"

DEFAULT_FONT = SHORTHAND_FONTS["default"]
"The default font"

DEFAULT_FONT_BOLD: str  = SHORTHAND_FONTS['default-bold']
"Default bold font"

DEFAULT_FONT_CLOCK : str = SHORTHAND_FONTS['clock']
"Default font for digital clocks"

DEFAULT_FONT_HEADER : str = SHORTHAND_FONTS['header']

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

##Should set these from device I think (i.e. lcd's with default background black I believe)
# if INKBOARD:
#     from inkBoard.core import config

#     cf = config.styles

#     if "battery_style" in cf:
#         DEFAULT_BATTERY_STYLE = BatteryIconMapping(**config.styles["battery_style"])

#     if "network_style" in cf:
#         DEFAULT_NETWORK_STYLE = cf["network_style"]
#     else:
#         DEFAULT_NETWORK_STYLE = "signal"

#     if "menu_header_color" in cf:
#         DEFAULT_MENU_HEADER_COLOR = cf["menu_header_color"]

#     if "menu_button_color" in cf:
#         DEFAULT_MENU_BUTTON_COLOR = cf["menu_button_color"]

#     if "foreground_color" in cf:
#         DEFAULT_FOREGROUND_COLOR = cf["foreground_color"]

#     if "background_color" in cf:
#         DEFAULT_BACKGROUND_COLOR = cf["background_color"]

#     if "blur_popup_background" in cf:
#         DEFAULT_BLUR_POPUP_BACKGROUND = cf["blur_popup_background"]

#     logger.warning("Don't forget to parse default custom fonts using the default custom folders")
#     ##Probably do that using Path variables
#     if "font" in cf:
#         DEFAULT_FONT = cf["font"]
#         SHORTHAND_FONTS["default"] = cf["font"]

#     if "font_bold" in cf:
#         DEFAULT_FONT_BOLD = cf["font_bold"]
#         SHORTHAND_FONTS["default-bold"] = cf["font_bold"]

#     if "font_clock" in cf:
#         DEFAULT_FONT_CLOCK = cf["font_clock"]
#         SHORTHAND_FONTS["clock"] = cf["font_clock"]

#     if "font_header" in cf:
#         DEFAULT_FONT_HEADER = cf["font_header"]
#         SHORTHAND_FONTS["header"] = cf["font_header"]

#     if "font_size" in cf:
#         DEFAULT_FONT_SIZE = cf["font_size"]

#     if "default_icon" in cf:
#         DEFAULT_ICON = cf["default_icon"]
#         SHORTHAND_ICONS["default"] = cf["default_icon"]

#     if "missing_icon" in cf:
#         MISSING_ICON = cf["missing_icon"]
#         SHORTHAND_ICONS["missing"] = cf["missing_icon"]

#     if "badge_location" in cf:
#         DEFAULT_BADGE_LOCATION = cf["badge_location"]

    