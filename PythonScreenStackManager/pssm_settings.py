"""
Reads out settings for the screen from the config file and possible the inkBoard config.
Provides a config object that can be used to save the settings.
"""

from pathlib import Path
import json
from typing import TypedDict, Literal, Union, Any, TYPE_CHECKING
from types import MappingProxyType
import logging

from .constants import INKBOARD
if TYPE_CHECKING:
    from .pssm_types import DurationType, RotationValues

logger = logging.getLogger(__name__)

PSSM_DIR = Path(__file__).parent

_configfile = Path("settings.json").resolve()

_screen_defaults = {"rotation": "UR", 
                    "refresh_interval": "15min",
                    "poll_interval": 30,
                    "close_popup_time": 60}

_device_defaults = {"backlight_behaviour" : "manual",
                    "backlight_time_on": 30,
                    "backlight_default_transition": 0,
                    "backlight_default_brightness": 100}

_sett_map = {'screen': {"rotation" : 'rotation', 
                                },
            'device' : {'backlight_behaviour': 'backlight.behaviour',
                        'backlight_time_on': 'backlight.default_time_on',
                        'backlight_default_transition': 'backlight.defaultTransition',
                        'backlight_default_brightness': 'backlight.defaultBrightness'}
                    }

class screen_settings(TypedDict):
    rotation : 'RotationValues'
    """
    Screen rotation. Corresponds as follows: \n
    values:\n
        UR: 'upright' [0°] \n
        CW: 'clockwise' [90°] \n
        UD: 'upsidedown' [180°] \n
        CCW: 'counterclockwise' [270°] \n
    """

    refresh_interval: Union['DurationType',int, float]
    "The amount of time in between full screen refreshes. Set to 0 for no refreshing"

    poll_interval: Union['DurationType',int, float]
    "The amount of time in between polling different attributes, like the Network status."

    close_popup_time: Union[float,'DurationType', int]
    "Amount of seconds or a time string for the default time to close popups in"


class device_settings(TypedDict):
    backlight_behaviour : Literal["Manual", "On Interact", "Always"]
    backlight_time_on : int
    backlight_default_transition : float
    backlight_default_brightness : int

##This became a typehint class for type hinting because apparently deriving from TypedDicts just means __getitem__ breaks yay
##Nor does it let you set default values
class settings_type(TypedDict):
    "This is a typehint for the settings object, do not actually use it for anything else."
    screen: screen_settings
    device: device_settings

    @property
    def file(self) -> Path:
        "The file containing the settings"
        return None

    @property
    def attribute_map(self) -> "settings_type":
        "Dict mapping settings to screen/device attributes"
        return MappingProxyType(_sett_map)

    def save(self):
        "Saves pssm settings to settings.json"
        pass

    def add_device_setting(self, key : str, map_attribute : str, default):
        """
        Adds a setting to the device key of settings, for settings that are needed for specific platforms/devices

        Parameters
        ----------
        key : str
            the key of the setting
        map_attribute : str
            The device attribute this setting corresponds to. DOES NOT need device in front of it, so e.g. 'backlight.behaviour' is a valid setting
        default : _type_
            the default value to give the setting
        """
        pass

_settings_keys = settings_type(**{"screen" : _screen_defaults, "device" : _device_defaults})

if _configfile.exists():
    with open(_configfile, 'r') as f:
        try:
            __data = json.loads(f.read())
        except json.decoder.JSONDecodeError:
            __data = {}
    f.close()
else:
    __data = {}

for k, default_dict in _settings_keys.items():
    if k not in __data:
        __data[k] = default_dict
    else:
        for sett, default_val in default_dict.items():
            __data[k].setdefault(sett,default_val)

_data : settings_type = __data.copy()
##Also add a function for add_device_setting and save_settings

# if INKBOARD:

#     from inkBoard.core import config
    
#     d = dict(config.configuration)
#     for key in _data["screen"]:
#         if getattr(config.screen,key,False):
#         # if key in config.screen:
#             _data["screen"][key] = config.screen[key]

#     for key in _data["device"]:
#         if getattr(config.device,key,False):
#             _data["device"][key] = config.device[key]

class __settings():
    "Helper class for settings. Mainly implements functions to easily save them."

    @property
    def file(self) -> Path:
        "The file containing the settings"
        return _configfile

    @property
    def attribute_map(self) -> settings_type:
        "Dict mapping settings to screen/device attributes"
        return MappingProxyType(_sett_map)

    def __init__(self) -> settings_type:
        pass

    def __getitem__(self, key: Any) -> settings_type:
        return _data[key]

    def save(self):
        "Saves pssm settings to settings.json"
        with open(self.file, 'w') as f:
            try:
                d = dict(_data)
                f.write(json.dumps(d))
                logger.info(f"Settings saved to {_configfile}")
            except Exception as e:
                logger.exception("Settings dict is not of the correct type (There may be a mappingproxy in there)")
        return

    def add_device_setting(self, key : str, map_attribute : str, default):
        """
        Adds a setting to the device key of settings, for settings that are needed for specific platforms/devices

        Parameters
        ----------
        key : str
            the key of the setting
        map_attribute : str
            The device attribute this setting corresponds to. DOES NOT need device in front of it, so e.g. 'backlight.behaviour' is a valid setting
        default : _type_
            the default value to give the setting
        """
        _data["device"].setdefault(key,default)
        _sett_map["device"][key] = map_attribute

SETTINGS : Union[settings_type] = __settings()
"""
Settings constant for PSSM. Can be changed during runtime. 
Call SETTINGS.save() to save the current settings for subsequent runs.
Any settings in here that are defined in the yaml config will be overwritten according to the yaml  config.
"""

