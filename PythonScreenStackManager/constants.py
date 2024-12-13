"""
Constants for PythonScreenStackManager
"""
import __main__
from typing import TypeVar, Union, TYPE_CHECKING
from pathlib import Path
import logging
from asyncio import CancelledError
import sys

if TYPE_CHECKING:
    from .pssm_types import *

logger = logging.getLogger(__name__)

PATH_TO_PSSM = Path(__file__).parent
"""Path to the PythonScreenStackManager module. Used for parsing of default files."""

DEFAULT_ICON_FOLDER = PATH_TO_PSSM / 'icons'
DEFAULT_FONT_FOLDER = PATH_TO_PSSM / 'fonts'

GENERATOR_THREADPOOL = "pssm-generator"

INKBOARD: bool = False
"""
True if PSSM is being imported from inkBoard, to guide some constants and styling.
"""

n1 = sys.argv[0]
entry_point = Path(n1).parts[-1]

if ("inkBoard" in __package__   ##For internal imports
    or "inkBoard" in __main__.__file__ or "inkBoard" in entry_point   ##General usage
    or (hasattr(__main__,"debugpy") and __main__.cli.options.target == "inkBoard")): ##Debugging (in VScode using debugpy at least)
    #or "inkBoard" in sys.modules ##Leaving this out for now as it would yield True for any point inkBoard is imported in.
    INKBOARD = True



RAISE = False

FuncExceptions = (TypeError, KeyError, IndexError, ValueError, OSError, RuntimeError)
"General exceptions to catch when calling functions like update. Usage  in try statements as `except FuncExceptions:`"

class CancelledExceptions(CancelledError):
    "Exceptions that should be able to catch cancelled futures where needed."
    pass

class FEATURES:
    "Names for device features. Use them as constants when checking for features."

    FEATURE_POWER = "FEATURE_POWER"
    "Power features indicate the device is able to turn the hardware off and reboot it"

    FEATURE_INTERACTIVE = "FEATURE_INTERACTIVE"
    "Interactive feature to indicate the device supports screen interaction"

    FEATURE_BACKLIGHT = "FEATURE_BACKLIGHT"
    "Backlight feature to indicate the device can control the screen's brightness (may be renamed)"

    FEATURE_NETWORK = "FEATURE_NETWORK"
    "Network feature to indicate the device has internet connectivity and is able to retrieve information on it"

    FEATURE_BATTERY = "FEATURE_BATTERY"
    "Battery feature to indicate the device has a battery and is able to report the charge level and state"

    FEATURE_RESIZE = "FEATURE_RESIZE"
    "Resize feature to indicate the device's screen size can change"

    FEATURE_ROTATION = "FEATURE_ROTATION"
    "Rotation feature to indicate the device can rotate during runtime."

    FEATURE_PRESS_RELEASE = "FEATURE_PRESS_RELEASE"
    "Feature to indicate the device is interactive and can report the coordinates of a press and the coordinates of a release"

FEATURE_ATTRIBUTES = {
    FEATURES.FEATURE_BACKLIGHT: "backlight",
    FEATURES.FEATURE_BATTERY: "battery",
    FEATURES.FEATURE_NETWORK: "network"
}
"Features and associated device attributes for them, if any."

TOUCH_PRESS = "TOUCH-PRESSED"
"Inidicates the touch event is an object pressing on the screen"

TOUCH_RELEASE = "TOUCH-RELEASED"
"Indicates the touch event is the object leaving the screen"

TOUCH_TAP = "TOUCH-TAP"
"Indicates a short touch event, for devices that do not support reporting both press and release events"

TOUCH_LONG = "TOUCH-LONG"
"Indicates a long touch, for devices that do not support reporting both press and release events. Dispatches to element's `hold_action`"

DEFAULT_DEBOUNCE_TIME = '1ms'
DEFAULT_HOLD_TIME = '0.5s'

DEFAULT_FEEDBACK_DURATION : float = 0.75
"Default duration to show element feedback"

DEFAULT_BACKGROUND : Union["ColorType",Path] = None
"Default screen background. Defaults to None (device defaultColor), or the standard inkBoard background image if inkBoard is running."

PSSM_COLORS : dict[str,tuple[int,int,int,int]] = {'None': None}
"""
Predefined shorthand colors that are not present in the PIL shorthands. 
16 shades of gray (Dare I make it 50?) Use as 'gray1'/'grey1'; Higher number means a lighter shade. Returns
Returned as an RGBA tuple.
Can be added to by simply adding a key (for additional libraries e.g.).
"""

##Adding shorthand colors would be pretty rad too imo
for i in range(16):
    s = int(i*255/15)
    PSSM_COLORS['gray' + str(i)] = (s, s, s, 255)
    PSSM_COLORS['grey' + str(i)] = (s, s, s, 255)

SHORTHAND_ICONS : dict = {
        'arrow': "mdi:arrow-right", 
        'back': "mdi:keyboard-return",
        'close': "mdi:close",
        'delete': "mdi:file-remove",
        "frontlight-down": "mdi:brightness-5",
        "frontlight-up": "mdi:brightness-7",
        "invert": "mdi:invert-colors",
        "reboot": "mdi:reload",
        "save": "mdi:content-save",
        "touch-off": "mdi:hand-back-right-off",
        "touch-on": "mdi:gesture-tap",
    }
"""
Some shorthands that have a default (mdi) icon, such that the entire path does not need be used each time.
"""

__pssm_font_folder = DEFAULT_FONT_FOLDER
fontType = TypeVar("Font")
SHORTHAND_FONTS : dict[fontType, Path] = {
    'quicksand' : __pssm_font_folder / "Quicksand-Regular.ttf",
    'quicksand-bold': __pssm_font_folder / "Quicksand-Bold.ttf",
    'notosans' : __pssm_font_folder / "NotoSans-Light.ttf",
    'notosans-regular': __pssm_font_folder / "NotoSans-Regular.ttf",
    'notosans-bold' : __pssm_font_folder / "NotoSans-Medium.ttf",
    'merriweather-regular': __pssm_font_folder / "Merriweather-Regular.ttf",
    'merriweather-bold': __pssm_font_folder / "Merriweather-Bold.ttf",
    'clock': __pssm_font_folder / "PoiretOne-Regular.ttf",
    'mdi': __pssm_font_folder / "materialdesignicons-webfont.ttf"
}
"Paths to some default implemented fonts. Also has shorthands for default, clock and header fonts. Allows for other libraries to add to it."

SHORTHAND_FONTS['default'] = SHORTHAND_FONTS['notosans']
SHORTHAND_FONTS['default-regular'] = SHORTHAND_FONTS['notosans-regular']
SHORTHAND_FONTS['default-bold'] = SHORTHAND_FONTS['notosans-bold']
SHORTHAND_FONTS["header"] = SHORTHAND_FONTS['default-bold']

##I believe like this it should work from the working directory, not the directory where pssm is installed

CUSTOM_FOLDERS = {"font_folder": Path("./fonts"), 
                "icon_folder": Path("./icons"), 
                "picture_folder": Path("./pictures")}

DEFAULT_DATE_FORMAT : str = None
"Default format for parsing dates"

DEFAULT_TIME_FORMAT : str = None
"Default format for parsing time"

MDI_WEATHER_DATA_ICONS : dict = {
                        "datetime" : None,
                        "cloud_coverage": "mdi:cloud-percent",
                        "humidity": "mdi:water-percent",
                        "apparent_temperature": "mdi:thermometer-lines",
                        "dew_point": "mdi:water-thermometer",
                        "precipitation": "mdi:water",
                        "pressure": "mdi:gauge",
                        "temperature": "mdi:thermometer",
                        "templow": "mdi:thermometer-chevron-down",
                        "wind_gust_speed": "mdi:weather-windy",
                        "wind_speed": "mdi:weather-windy",
                        "precipitation_probability": "mdi:water-percent-alert",
                        "uv_index": "mdi:sun-wireless",
                        "wind_bearing": "mdi:windsock"
                            }
"Dict with default icons to use for forecast data lines"

# OSK CONSTANTS
DEFAULT_KEYMAP_PATH_STANDARD = PATH_TO_PSSM / "config" / "default-keymap-en_us.json"
DEFAULT_KEYMAP_PATH_CAPS = PATH_TO_PSSM / "config" / "default-keymap-en_us_CAPS.json"
DEFAULT_KEYMAP_PATH_ALT = PATH_TO_PSSM / "config" / "default-keymap-en_us_ALT.json"

DEFAULT_KEYMAP_PATH = {
    'standard': DEFAULT_KEYMAP_PATH_STANDARD,
    'caps': DEFAULT_KEYMAP_PATH_CAPS,
    'alt': DEFAULT_KEYMAP_PATH_ALT
}

KTstandardChar = 0
KTcarriageReturn = 1
KTbackspace = 2
KTdelete = 3
KTcapsLock = 4
KTcontrol = 5
KTalt = 6

if INKBOARD:
    ##This implementation will be changed once styles have been implemented fully.

    from inkBoard.constants import RAISE as iBraise, INKBOARD_COLORS, INKBOARD_ICON

    ##Importing raise is fine, same as the colors. Just move out the config stuff. Should be fine to reference those via strings -> default time_format tho?
    RAISE = iBraise
    
    pass

    from inkBoard.core import config

    CUSTOM_FOLDERS = config.folders

    if config.inkBoard.date_format:
        DEFAULT_DATE_FORMAT = config.inkBoard["date_format"]

    if config.inkBoard.time_format:
        DEFAULT_TIME_FORMAT = config.inkBoard["time_format"]

    if config.screen.feedback_duration:
        DEFAULT_FEEDBACK_DURATION = config.screen["feedback_duration"]

    SHORTHAND_ICONS["inkboard"] = INKBOARD_ICON
    PSSM_COLORS.update(INKBOARD_COLORS)

    if "shorthand_colors" in config.styles: ##styles is a typeddict not a dataclass
        for color, value in config.styles["shorthand_colors"].items():
            if color in PSSM_COLORS:
                msg = f"{color} is already defined and cannot be overwritten. Please change the name of the color."
                err = KeyError(msg)
                logger.error(err)
                raise err
            else:
                if not isinstance(value, (tuple, list)) or len(value) != 4:
                    msg = f"{color} must be a list of 4 values"
                    err = TypeError(value)
                    logger.error(err)
                    raise err
                else:
                    PSSM_COLORS[color] = tuple(value)

