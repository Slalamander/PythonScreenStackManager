
from collections import namedtuple
from ..constants import FEATURES

_attr_list = [y for x, y in FEATURES.__dict__.items() if isinstance(y,str) and not x.startswith("_")]

_DeviceTuple = namedtuple("__DeviceTuple", _attr_list, defaults=(False,)* len(_attr_list))

CANVASNAME = "pssm-canvas-widget"

class DeviceFeatures(_DeviceTuple, FEATURES):
    """Class for indicating which features the device has. 
    
    Pass all the features using the constants from the `FEATURES` class.
    Do not interface with this class directly, but use `device.has_feature(FEATURES.FEATURE_{})` instead.
    """

    def __new__(cls, *features: str, **kwargs):
        for a in features:
            kwargs[a] = True
        return _DeviceTuple.__new__(cls, **kwargs)
    





