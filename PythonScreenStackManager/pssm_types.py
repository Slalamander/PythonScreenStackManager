"""
Various type hints for use with pssm.
"""
from typing import TYPE_CHECKING, \
                Union, TypeVar, Literal, Optional, TypedDict, Callable, AnyStr, Any, Generic, NamedTuple
import functools

from mdi_pil import mdiType

from . import constants as const

if TYPE_CHECKING:
    from .pssm.screen import PSSMScreen
    from .elements.baseelements import Element
    from .devices import PSSMdevice


#region General
ColorType = Union[str,int,list,
            tuple[TypeVar('L'),TypeVar('A')], ##LA type
            tuple[TypeVar('R'),TypeVar('G'),TypeVar('B')], ##RGB type
            tuple[TypeVar('R'),TypeVar('G'),TypeVar('B'),TypeVar('A')] ##RGBA type
            ]
"Types for valid colors in the supported color modes. Very broad, generally call tools.is_valid_color for actual validation."

PSSMdimension =  Union[str,int,float,tuple[TypeVar("PSSMdimension")],list[TypeVar("PSSMdimension")]]
"Possible types for dimensions. Accepts tuples and lists with dimension types as well."

xType = TypeVar('x', bound=int)
yType = TypeVar('y', bound=int)
wType = TypeVar('w', bound=int)
hType = TypeVar('h', bound=int)

PSSMarea = tuple[tuple[TypeVar('x', bound=int),TypeVar('y', bound=int)],
                tuple[TypeVar('w', bound=int) ,TypeVar('h', bound=int)]]
"Type hint for pssm areas"

PSSMlayout = list[list[Union[TypeVar('PSSMdimension'),tuple[TypeVar('Element'),TypeVar('PSSMdimension')]]]] #tuple[int,int]]
"Layout typing. First entry of a row is ALWAYS a string with the rows height, and it then allows for unlimited tuples to be added with (Element, 'element_width')"

PSSMLayoutString = TypeVar('LayoutString')
"""
Strings that can be used to parse various elements into a tile using the `elements.parse_layout_string` function.
A string is made up of the name of the elements, which can be separated by a ',' to denoted elements in a row, and ';' to indicate a new row.
Enclosing elements between square brackets 'element0,[element1;element2]' will cause them to be put into a subelement. So in that example, element1 is put above element2, and that layout is put in next to element0.
"""

CoordType = tuple[TypeVar('x', bound=int), TypeVar('y', bound=int)]
"Type hint for returned coordinates"

class TouchEvent(NamedTuple):
    "Events used to pass touches to the screen, use for devices"
    x: int
    y: int
    touch_type: Literal[const.TOUCH_PRESS, const.TOUCH_RELEASE]


class InteractEvent(NamedTuple):
    "This event is passed to functions when dispatched from a screen interaction. "

    x: int
    "x coordinate of the interaction"

    y: int
    "y coordinate of the interaction"

    action: str
    "Type of interaction function that was registered. I.e. 'tap', 'hold' or 'hold_release'"


InteractionFunctionType = Union[str,Callable[["Element",InteractEvent,Any],Any],None]
"Type hint for interaction functions, like tap_action"

DurationType = TypeVar("duration", float, int, str)
"""
Durational strings to denote time intervals. E.g. 2h, 50min etc.
"""

RotationValues = Literal["UR", "CW", "UD", "CCW"]
"""
Allowed values for the rotation. Abbreviations come from allowed values used for FBink for the ereader implementation of PSSM. \n
values:\n
    UR: 'upright' [0°] \n
    CW: 'clockwise' [90°] \n
    UD: 'upsidedown' [180°] \n
    CCW: 'counterclockwise' [270°] \n
"""

textAlignmentType = tuple[TypeVar('horizontal'), TypeVar('vertical')]
"Text alignment type hint"

TouchActionType = Literal["tap", "hold", "hold_release"]

class ScreenInit(TypedDict):
    "Type hint for the get_screen function, has all the arguments possible to initiate a screen instance."

    device : "PSSMdevice"
    "Platform from which to import the device"

    on_interact: Optional[Callable[[dict, 'PSSMScreen', CoordType], None]]
    "Function to call when the screen in interacted with"

    on_interact_data: dict
    "Dict to pass as keyword arguments to the on_interact function"

    background: Union[str, ColorType, None]
    "Main background of the screen. Can be a color, or an image. If None, the default device background is assumed."

    isInverted: bool
    "Whether the whole screen is to be inverted"

    poll_interval: Union[float,DurationType, int]
    "The amount of time in between polling different attributes, like the Network status."

    close_popup_time: Union[float,DurationType, int]
    "Amount of seconds or a time string for the default time to close popups in"

    backlight_behaviour:  Optional[Literal["Manual", "On Interact", "Always"]]
    "Behaviour of the backlight, if the device has one. "

    backlight_time_on: Union[float,DurationType, int]
    "Time interval to keep the backlight on when calling the temporary backlight function, or when the behaviour is set to On Interact"


class interact_actionDict(TypedDict):
    action : str
    "The shorthand for the action to perform"

    element_id : str
    "Element id to get the action from"

    data : dict[str,Any]
    "Keyword arguments and their values to pass to the element"

    map : dict[str,str]
    "Keyword arguments and the element attribute to get the keyword value from" 

#endregion

#region Element Types
BadgeLocationType = Literal["UR", "LR", "UL", "LL"]
"""
Allowed values for badge locations.
Values:\n
    UR: Upper Right\n
    LR: Lower Right\n
    UL: Upper Left\n
    LL: Lower Left\n
"""

class BatteryIconSettings(TypedDict):
    fillIcon: Optional[mdiType]
    color: Union[str,tuple[int, int, int, int]]
    size: int
    style: Literal['filled', 'bars']
    orientation: Literal['ver', 'vertical', 'hor', 'horizontal']
    fillRotation: int

class BatteryIconMapping(TypedDict):
    "Mapping dict for the battery icon"

    default : BatteryIconSettings
    "Default settings for the battery. Applied to each icon, but can be overwritten by the actual state."

    full : BatteryIconSettings
    "Icon settings for when the battery is full"

    charging: BatteryIconSettings
    "Icon settings for when the battery is charging"

    discharging : BatteryIconSettings
    "Icon settings for when the battery is discharging"

T = TypeVar('T', bound=property)

class classproperty(Generic[T]):
    "Used to avoid the deprecation warning (and the extra writing) needed to set class properties"
    
    def __init__(self, method: Callable[..., "T"]):
        self.method = method
        functools.update_wrapper(self, wrapped=method) # type: ignore

    def __get__(self, obj, cls=None) -> "T":
        if cls is None:
            cls = type(obj)
        return self.method(cls)

