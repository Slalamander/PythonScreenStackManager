"""
Tool library for pssm. 
Provides some helper functions for PIL and coloring, asyncio  and some general functions.
"""

import logging
import asyncio
import re as regex

from copy import deepcopy
from typing import *
from math import cos, sin, floor
from  pathlib import Path
from abc import ABCMeta
from types import SimpleNamespace, MappingProxyType
from abc import abstractmethod

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops
from PIL.ImageColor import getrgb as PILgetrgb, getcolor as PILgetcolor

import mdi_pil as mdi
from mdi_pil import ALLOWED_MDI_IDENTIFIERS, MDI_WEATHER_ICONS as MDI_WEATHER_CONDITION_ICONS

from . import constants as const
from .constants import PATH_TO_PSSM


from .pssm_types import *

if TYPE_CHECKING:
    from . import elements

logger = logging.getLogger(__name__)

# ######################## - Helper Classes - ####################################

class DummyTask:
    """
    Provides a dummy to mimic an asyncio task object when needed to make one before starting the event loop. For use in logic statements
    """
    
    def done(self) -> bool:
        """Returns True to mimic the task being done"""
        return True
    
    def cancelled(self) -> bool:
        """Returns False since the dummy task cannot be cancelled"""
        return False
    
    def cancel(self) -> None:
        """Does nothing but may be useful for logic purposes"""
        return
    
    def result(self) -> None:
        """Returns nothing since there is no result"""
        return

class Singleton(ABCMeta):
    """
    Use as metaclass (class Classtype(metaclass=Singleton)).
    Ensures only a single instance of this class can exist, without throwing actual errors. Instead, it simply returns the first define instance.
    """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        # else:
        #     raise Exception("Double instance")
        return cls._instances[cls]

class customproperty(property):
    "Base class for making custom property decorators."

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, value)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__)



# ########################## - OTHERS - ######################################
def returnFalse(*args, **kwargs): return False

def function_checker(func: Union[Callable[...,None], bool, None], default: Callable[..., None]=returnFalse) ->Union[Literal[False], Callable[..., None]]:
    """
    Checks if a function supplied for an interaction function is valid. Returns default if set to None

    Parameters
    ----------
    func : Union[Callable[...,None], bool, None]
        the function to check. If it is None, the default function is returned.
    default : Callable[..., None], optional
        default function to return if func is None, by default returnFalse

    Returns
    -------
    False, Callable
        The returned function, either the default function or supplied function.
        If the argument supplied under `func` is a boolean, `False` is returned.
    """    

    if callable(func):
        return func
    elif func == None:
        return default
    elif type(func) == bool:
        if func:
            logger.warning(f"interaction booleans can only be False, setting to False")
    return False

def update_nested_dict(update_dict: dict, old_dict: dict) -> dict:
    """Updates the old dict in a nested manner.
    
    The old_dict is copied and will not be overwritten. Not yet present keys will be added.
    Any values in the update_dict that are not dicts will directly overwrite the value in the old_dict, regardless of whether it is a dict or not.
    
    Parameters
    ----------
    update_dict : dict
        The dict with key, value pairs to update
    old_dict : dict
        The dict to update
    """

    new_dict = old_dict.copy()

    for key, value in update_dict.items():

        if (key not in old_dict or 
            not isinstance(value, (dict,MappingProxyType)) or
            not isinstance(old_dict[key], (dict,MappingProxyType))):
            new_dict[key] = value
            continue

        new_value = update_nested_dict(value, old_dict[key])
        new_dict[key] = new_value
        
    return new_dict


class TypedDictType(TypedDict):
    pass

def TypedDict_checker(check_dict: dict, typeddict: TypedDictType) -> frozenset:
    """
    Checks if all required keys in typeddict are present in check_dict

    Parameters
    ----------
    check_dict : dict
        the dict to check
    typeddict : TypedDict
        Type of the check_dict (necessary since TypedDict objects have no reference to the TypedDict they reference)
    
    Returns
    -------
    frozenset
        Set with the required keys that are missing from check_dict. Empty if none are missing (so you can evaluate by checking for `not frozenset` (Which is true if the set is empty)
    """

    check_keys = set(check_dict.keys())
    req_keys = typeddict.__required_keys__

    ##This is the same as req_keys.difference(check_keys), and it only returns keys present in req_keys and in check_keys, not the other way around
    return req_keys - check_keys

def wrap_to_coroutine(func: Callable, *args, **kwargs) -> Awaitable:
    """
    Wraps a given function into a coroutine, if it isn't one yet. Returns an object that can be awaited on.
    If passed something that is not callable, it will return asyncio.sleep(0) in order to not break stuff. But it's better to filter these cases out.

    Parameters
    ----------
    func : Callable
        The function to wrap into a coroutine
    *args :
        Positional arguments to pass into the function call.
    **kwargs :
        Keyword arguments to pass into the function call.
        
    Returns
    -------
    Awaitable
        Either the coroutine function if func already was one, or a normal function wrapped into asyncio.to_thread(...)
    """
    
    if not callable(func):
        logger.warning(f"{func} is not a callable value. It's better to filter these cases out.")
        return asyncio.sleep(0)
    
    if asyncio.iscoroutinefunction(func):
        return func(*args,**kwargs)
    else:
        return asyncio.to_thread(func, *args, **kwargs)

def wrap_to_tap_action(func : Callable, *call_args, **call_kwargs) -> Callable:
    """
    Wraps the given function into a function that can be used as a tap_action, without the passed element and coordinates conflicting with the allowed arguments.
    Any optional keyword arguments passed to the wrapped function are also passed to the original function (so working with tap_action_data and tap_action_map is possible.)
    

    Parameters
    ----------
    func : Callable
        The function to wrap

    *call_args : any positional arguments that will be passed to the function each time it is called
    **call_kwargs : any keyword arguments that will be passed to the function each time it is called

    Returns
    -------
    Callable[...]
        The wrapped function that can be used as a tap_action. Takes any values (so also `Element` and `(x,y)`) but never passes them to the original function.
        The original docstring of the function is copied, and the function signature is changed to reflect it being wrapped.
    """    

    async def async_tap_action_wrapper(*args, **kwargs):
        return await func(*call_args, **call_kwargs, **kwargs)

    def tap_action_wrapper(*args, **kwargs):
        return func(*call_args, **call_kwargs, **kwargs)
    
    if asyncio.iscoroutinefunction(func):
        wrapper = async_tap_action_wrapper
    else:
        wrapper = tap_action_wrapper

    wrapper.__doc__ = func.__doc__
    wrapper.__qualname__ = f"tap_action_wrapper.{func.__qualname__}"
    return wrapper

def _block_run_coroutine(coro : Coroutine, loop : asyncio.BaseEventLoop) -> Any:
    """
    Non async function that can block non async functions until the provided coro finishes.
    Use with care, or preferably do not use it at all as it has a big tendency to block, and freeze, the event loop.
    
    Parameters
    ----------
    coro : asyncio.coroutine
        Coroutine to wait to finish before returning
    loop : asyncio.BaseEventLoop
        The event loop to run the coroutine in. If None, creates a new event loop.
    
    Returns
    ----------
    Any :
        The result of the awaited coroutine.
    """

    if loop == None:
        loop = asyncio.get_running_loop()

    logger.trace(f"Blocking till coroutine {coro} finishes")

    f = asyncio.run_coroutine_threadsafe(coro, loop)
    res = f.result()
    w = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
    w = w.result()
    logger.trace(f"{coro} is finished.")
    return res 


def insert_string(string, char, pos):
    """ Returns a string with the characther insterted at said position """
    return string[:pos] + char + string[pos:]

##Don't think anything above days is necessary tbh
##This one works, although everything needs to be in order. Eh, generally I'd advise to use a single unit anyways.
##Don't use m anyways since it's the symbol for meters. Just use min
time_patterns = {
    "hours": r'(?P<hours>[\d.]+)\s*(?:h|hrs?|hours?)',
    "minutes": r'(?P<minutes>[\d.]+)\s*(?:min|(minutes?))',
    "seconds": r'(?P<seconds>[\d.]+)\s*(?:s|secs?|seconds?)',
    "milliseconds": r'(?P<milliseconds>[\d.]+)\s*(?:ms|milliseconds?)',
}
"Regex patterns to parse duration strings."

second_multipliers = {"milliseconds": (10**-3), "seconds": 1, "minutes": 60, "hours": 60*60, "days": 60*60*24}

pattern = ""
for ptn in time_patterns.values():
    pattern = f"{pattern}({ptn})?"

duration_regex = regex.compile(pattern)

duration_dict_type = TypedDict("duration_dict_type", {"hours": float, "minutes": float, "seconds": float, "milliseconds": float})

##Also hacked together using tears and pain since I don't know regex and my ADHD really does not like it.
def match_duration_string(string : str) -> duration_dict_type:
    """
    Uses regex to match a duration string into the different time units present in it.
    Strings must be ordered from largest unit to smallest unit (so hour -> minute -> second -> millisecond).
    For best/most reliable results, use a single unit.
    Hacked together using answers from here: https://stackoverflow.com/questions/4628122/how-to-construct-a-timedelta-object-from-a-simple-string
    
    
    Example: match_duration_string(string = 2h12min) -> {'hours': 2, 'minutes': 12}

    Matches
    ----------
    hours: h, hr(s), hour(s) \n
    minutes: min, minute(s) \n
    seconds: s, sec(s), second(s) \n
    milliseconds: ms, millisecond(s) \n

    Parameters
    ----------
    string : str
        Duration string to match

    Returns
    -------
    duration_dict_type[str,float]
        dict with the found units and their amount. (hours, minutes, seconds, milliseconds). Keys should match keyword arguments for timedeltas.
    """

    if ' ' in string:
        ##Idk how to make the regex take care of whitespaces so ill just do this ¯\_(ツ)_/¯
        string = string.replace(' ', '')
    parts = duration_regex.match(string)
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = float(param)
    logger.debug(f"Duration string {string} matched to {time_params}")
    return time_params

def parse_duration_string(string : Union[str, int, float]) -> float:
    """
    Converts duration string (1min, 2h etc) into the amount of seconds in it. floats and integers are returned as is.
    Strings must be ordered from largest unit to smallest unit (so hour -> minute -> second -> millisecond).
    For best/most reliable results, use a single unit.
    
    Example: parse_duration_string(string = 2min3s) -> 123.0

    Matches
    ----------
    hours: h, hr(s), hour(s) \n
    minutes: min, minute(s) \n
    seconds: s, sec(s), second(s) \n
    milliseconds: ms, millisecond(s) \n

    Parameters
    ----------
    string : Union[str, int, float]
        The duration string to convert. Also accepts floats and integers for convenience.

    Returns
    -------
    str
        The time the string represents, in seconds
    """
    if isinstance(string,(int,float)):
        return float(string)

    match_dict = match_duration_string(string)
    if not match_dict:
        msg = f"Could not parse duration {string} into time values. Please check if you used the right notations and everything is in order from largest to smallest."
        logger.exception(ValueError(msg))
        return
    secs = 0
    for unit, t in match_dict.items():
        mult = second_multipliers[unit]
        secs = secs + t*mult
    
    return secs

def coords_in_area(click_x : int, click_y : int, area : PSSMarea) -> bool:
    """
    Returns a boolean indicating if the click was in the given area

    Parameters
    ----------
    click_x : int
        The x coordinate of the click
    click_y : int
        The y coordinate of the click
    area : PSSMarea
        The area to check (of shape : [(x, y), (w, h)])

    Returns
    -------
    bool
        True if the click was within the area, otherwise False
    """

    [(x, y), (w, h)] = area
    if click_x >= x and click_x < x+w and click_y >= y and click_y < y+h:
        return True
    else:
        return False


def get_rectangles_intersection(area1 : PSSMarea, area2 : PSSMarea) -> Union[PSSMarea,None]:
    """
    Gets the area intersecting two rectangles. Returns False

    Parameters
    ----------
    area1 : PSSMarea
        First area, as [(x,y),(w,h)]
    area2 : PSSMarea
        Second area, as [(x,y),(w,h)]

    Returns
    -------
    Union[PSSMarea,None]
        The intersecting area. None if there is no intersection.
    """    
    (x1, y1), (w1, h1) = area1
    (x2, y2), (w2, h2) = area2
    x0a = max(x1, x2)        # Top left
    x0b = min(x1+w1, x2+w2)  # Bottom right
    y0a = max(y1, y2)        # Top left
    y0b = min(y1+h1, y2+h2)  # Bottom right
    w0 = x0b-x0a
    h0 = y0b-y0a
    if w0 > 0 and h0 > 0:
        return [(x0a, y0a), (w0, h0)]
    else:
        return None

def rotation_matrix(coordinates:list[tuple[int,int]], angle : int, center: tuple[int,int] = (0,0)) -> list[tuple[int,int]]:
    """
    Applies a rotation matrix to the provided coordinates
        args:
            coordinates: list of (x,y) tuples to apply to transformation to
            angle: rotation angle in radians
    """
    v = []
    for (xo,yo) in coordinates:
        (x,y) = (xo-center[0],yo-center[1])
        xp = int(x*cos(angle) - y*sin(angle)) + center[0]
        yp = int(x*sin(angle) + y*cos(angle)) + center[1]
        v.append((xp,yp))
    return v

def intersect_element_area(elt : "Element", intersect_area : PSSMarea) -> Image.Image:
    """
    Returns a PIL image of the the interesection of the Element image and
    the rectangle coordinated given as parameter.
    (Honors invertion)

    Parameters
    ----------
    elt : Element
        a PSSM Element
    intersect_area : PSSMarea
        The area to intersect it with

    Returns
    -------
    Image.Image
        The image with the intersection applied
    """    

    [(x, y), (w, h)] = elt.area
    [(x1, y1), (w1, h1)] = intersect_area
    img = elt.imgData.copy()

    left = + x1 - x
    upper = + y1 - y
    right = left + w1
    lower = upper + h1

    img_cropped = img.crop(box=(left, upper, right, lower))
    
    if elt.isInverted:
        return ImageOps.invert(img_cropped)
    else:
        return img_cropped

def is_valid_dimension(dimStr:PSSMdimension, variables : list[str] =[]) -> Union[bool,Exception]:
    """
    Checks if the given dimensional string is a valid pssm dimension string i.e. can be converted into an integer or float when for pixel values when needed. 
    Works recursively, i.e. putting in a list of dimensions will test all of them (until an invalid one is found)
    Returns an exception if it is not valid.

    Parameters
    ----------
    dimStr : PSSMdimension
        The dimension to test. Generally a string, but also accepts integers and float.
    variables : list[str], optional
        list of variables (aside from the usual ones) that can be present in this dimensional string, by default []

    Returns
    -------
    Union[bool,Exception]
        True if it is a valid PSSM dimension. Otherwise, returns an exception with info on why it is invalid.
    """
    ##This function should be updated to raise the errors. Any caller should aptly handle them I think.

    ##set these to 1, since the values do not matter here
    if isinstance(dimStr,(tuple,list)):
        for dim in dimStr:
            if isinstance(v:=is_valid_dimension(dim,variables), Exception):
                return v
        return True
    
    if isinstance(dimStr,(int,float)):
        return True
    
    # p, P = 1, 1 #Pixel calculations are allowed too it seems 
    if "?" in dimStr:
        if dimStr[0] == "?":
            # dimStr[0] = "Q"
            dimStr = dimStr.replace("?","Q")
        else:
            return SyntaxError(f"{dimStr} is not a valid positional string. Questionmarks (?), if present, must always be the first character.")
    varDict = {"W":1,"H":1,"w":1, "h":1,"P":1,"p":1, "Q":1}
    for var in variables:
        if len(var) > 1: 
            logger.warning(f"Dimensional variables are best kept at single letters. {var} is longer")
        varDict[var] = 1
    try:
        res = eval(dimStr,varDict)      #@IgnoreExceptions
    except NameError as exce:
        return NameError(f"{exce} in dimensional string {dimStr}. Valid non numbers are {varDict.keys()}")  #@IgnoreExceptions
    
    except SyntaxError as exce:
        return SyntaxError(f"{dimStr} can not be evaluated as a python operation: {exce}")
    else:
        if not isinstance(res,(int,float)):
            return TypeError(f"{dimStr} Result is not an integer or float. Returned {res}")
        
    return True

def convert_XArgs_to_PX(xPosition, objw, textw, myElt=None) -> int:
    """
    Converts xPosition string arguments to numerical values
    Accepted inputs: "left", "center", "right", an inteteger value, or "w/2"
    """
    xPosition = xPosition.lower()
    if xPosition == "left":
        x = 0
    elif xPosition == "center":
        x = int(0.5*objw-0.5*textw)
    elif xPosition == "right":
        x = int(objw-textw)
    else:
        converted = myElt._convert_dimension(xPosition)
        x = int(converted)
    return x

def convert_YArgs_to_PX(yPosition, objh, texth, myElt=None):
    """
    Converts yPosition string arguments to numerical values
    """
    yPosition = yPosition.lower()
    if yPosition == "top":
        y = 0
    elif yPosition == "center":
        y = int(0.5*objh-0.5*texth)
    elif yPosition == "bottom":
        y = int(objh-texth)
    else:
        converted = myElt._convert_dimension(yPosition)
        y = int(converted)
    return y

def parse_known_image_file(file):
    """
    Finds the path to a image file if its argument is one of pssm images. Else returns the path starting from the default icon folder.
    """

    if isinstance(file, (Path, Image.Image)):
        return file

    if file in const.SHORTHAND_ICONS:
        return const.SHORTHAND_ICONS[file]
    else:
        if file[0:4] in ALLOWED_MDI_IDENTIFIERS:
            return file
        elif PATH_TO_PSSM.__str__() in file:
            ##This should catch special icons like meteocons, since those are in a folder within pssm, not the icon folder in the main program
            #For now keep it like this, but this would mean folders within the icon folder aren't possible
            ##Maybe make it possible to not parse the file?
            return file
        else:
            return const.CUSTOM_FOLDERS["icon_folder"] / file

def parse_known_fonts(font:str):
    """
    Finds the path to a image file if its argument is one of pssm images.
    """
    if isinstance(font,Path):
        return font
    if font.lower() in const.SHORTHAND_FONTS:
        return const.SHORTHAND_FONTS[font.lower()]
    # elif PATH_TO_PSSM / "fonts" in font:
    #     return font
    else:
        if "/" not in font:
            print(f"Returning custom font {font}")
            return const.CUSTOM_FOLDERS["font_folder"] / font
        else:
            return font

def is_valid_Color(color : ColorType) -> bool:
    """
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

    if color == None:
        return True
    
    if isinstance(color,int):
        if color < 0 or color > 255:
            logger.warning(f"Integer colors must be between 0 and 255. {color} lies outside that.")
            return False
        else:
            return True
        
    if isinstance(color,(list,tuple)):
        if len(color) > 4:
            logger.error(f"Supported colorModes are L, LA, RGB and RGBA. This means a list of color values can contain at most 4 values. {color} has {len(color)} values.")
            return True
        else:
            for col in color:
                if col < 0 or col > 255:
                    logger.warning(f"Integer colors must be between 0 and 255. {color} has at least one value exceeding that.")
                    return False
            return True
        
    if isinstance(color,str):
        if color in const.PSSM_COLORS:
            return True
        else:
            try:
                PILgetrgb(color) #@IgnoreExceptions
            except ValueError:
                return False
            else:
                return True
            
    ##Code should not get here but just in case
    return False

def get_Color(color : ColorType, colorMode:str) -> Union[tuple]:
    """
    _summary_

    Parameters
    ----------
    color : ColorType
        The color to convert
    colorMode : str
        The mode to convert the color into. Generally only use RGB(A) and L(A)

    Returns
    -------
    Union[tuple]
        The converted color value, as a tuple

    Raises
    ------
    TypeError
        Raised if the color could not be converted
    """    

    if color == None:
        colorList = [0]*len(colorMode)
        return tuple(colorList)
    if isinstance(color,int):
        if color < 0:
            color = 0
        elif color > 255:
            color = 255
        
        colorList = [color]*len(colorMode)
        if "A" in colorMode:
            colorList[-1] = 255
        return tuple(colorList)
    
    if isinstance(color,(list,tuple)):
        if len(color) == len(colorMode):
            return tuple(color)
        else:
            color = tuple(color)
            colorList = [0]*len(colorMode)

            ##This line plus the alpha channel at the end should take care of BW colors
            if len(color) in [1,2]:
                colorList[0:len(colorMode)] = [color[0]] * len(colorMode)
            else:
                ##Means color is RGB or RGBA
                if "RGB" in colorMode:
                    colorList[0:3] = color[0:3]
                else:
                    r, g, b = color[0], color[1], color[2]
                    colorList[0] = int( 0.2989 * r + 0.5870 * g + 0.1140 * b)
            if "A" in colorMode:
                ##Setting the alpha channel to be non transparent if not specified, or to the predefined value
                colorList[-1] = color[-1] if len(color) in [2,4] else 255
            
            return tuple(colorList)
    
    if isinstance(color, str):
        if color in const.PSSM_COLORS:
            logger.debug(f"Parsing pssm color: {color}")
            if colorMode == "RGBA":
                return const.PSSM_COLORS[color]
            else:
                return get_Color(const.PSSM_COLORS[color],colorMode)
        
        try:
            colorTup = PILgetcolor(color,colorMode)
        except ValueError:
            logger.error(f"Could not recognise {color} as a valid color.")
            raise
        else:
            if isinstance(colorTup,int): 
                colorTup = tuple([colorTup])
            return colorTup

    #Code should not get here (And can't, apparently), but leaving it just in case.
    msg = f"Something went wrong converting {color} to a color value, returning 0 (black)"
    logger.error(TypeError(msg))
    raise TypeError(msg)
    return 0

def invert_Color(color : ColorType, colorMode):
    "Inverts a color. Does not perform checks for validity."
    
    ##Convert the color into a tuple
    color = get_Color(color,colorMode)
    invCol = list(map(lambda c: 255 - c, color))
    if "A" in colorMode:
        invCol[-1] = color[-1]
    
    return tuple(invCol)

def contrast_color(color : ColorType, colorMode) -> tuple:
    """
    Automatically returns a contrasting color.
    By default, this is the inverse color,  however a check if performed to see if a color is close to gray, in which case black is returned, in the tuple corresponding to colormode.

    Parameters
    ----------
    color : ColorType
        The color to contrast
    colorMode : _type_
        The mode the color is needed in.

    Returns
    -------
    tuple
        The tuple color value.
    """

    col_tuple = get_Color(color, colorMode=colorMode)

    if "A" in colorMode:
        check_cols = col_tuple[:-1]
    else:
        check_cols = col_tuple

    checks = [100<x<200 for x in check_cols]
    if all(checks):
        return get_Color("black", colorMode=colorMode)
    else:
        return invert_Color(color,colorMode)

def invert_Image(img : Image.Image) -> Image.Image:
    "Invert the provided image. Also supports inverting of images with alpha channels (transparancy layer is not inverted)"
    img = img.copy()
    if "A" in img.mode:
        alpha = img.getchannel("A")
        img = ImageChops.invert(img)
        img.putalpha(alpha)
    else:
        img = ImageOps.invert(img)
    return img

def fit_Image(img : Image.Image, new_size : tuple[int,int],  method : Literal["contain", "cover", "fit", "pad", "resize", "crop"], method_arguments : dict = {}, force_size : bool = False) -> Image.Image:
    """
    Fits an image using the provided method.

    Parameters
    ----------
    img : Image.Image
        The image instance to fit
    new_size : tuple[int,int]
        The size to fit the new image to.
    method : Literal[&quot;contain&quot;, &quot;cover&quot;, &quot;fit&quot;, &quot;pad&quot;, &quot;resize&quot;, &quot;crop&quot;]
        The way to fit the picture to the new size. 
        Cover and Contain are the base methods, and will always work (i.e. won't break no matter what is set in method_arguments)
        All other functions do work without setting the method_arguments, but can break when setting options for that.
        When using crop, the image will be resized to the alloted area if it is not the correct size
    method_arguments : dict, optional
        Optional arguments to put as keywords into the fitting function, by default {}
        When using crop or resize, the box argument takes string values, aking to dimensional strings. In this case, `'w'` and `'h'` evaluate to the new width and height given in new_size. `'W'` and `'H'` evaluate to the width and height of the original img. \n
        For resize, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize \n
        For crop, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.crop \n
        For the other methods, see: https://pillow.readthedocs.io/en/stable/reference/ImageOps.html \n
    force_size : bool, optional
        Force the returned image to be equal to new_size. This means, if it does not match the new_size at the end, a final call to ImageOps.fit is made. By default False

    Returns
    -------
    Image.Image
        The fitted image
    """

    if method in {"resize", "crop"}:
        ##Allow for resampling and box argument
        ##box argument: allow dimensional resize, BUT w,h are the width, height of the image
        (old_w, old_h) = img.size
        (w,h) = new_size

        if method == "crop":
            if "box" not in method_arguments:
                kwargs = {"box": ["0.5*(W-w)", "0.5*(H-h)", "0.5*(W+w)", "0.5*(H+h)"]}
            else:
                kwargs = {"box": method_arguments["box"]}
        else:
            kwargs = method_arguments
        
        if "box" in kwargs and isinstance(kwargs["box"], (tuple,list)):
            if method == "crop":
                box = ["0.5*(W-w)", "0.5*(H-h)", "0.5*(W+w)", "0.5*(H+h)"]
                if old_w < w:
                    box[0] = 0
                    box[2] = old_w
                if old_h < h:
                    box[1] = 0
                    box[3] = old_h
            else:
                box = [0,0,old_w, old_h]
            log_msg = "Resize box arguments must be larger than or equal to zero and no greater than the image width/height"
            for i, box_kw in enumerate(kwargs["box"]):
                if isinstance(box_kw, str):
                    box_kw = int(
                                eval(box_kw, {"W": old_w, "H": old_h, "w": new_size[0], "h": new_size[1]}))

                if box_kw < 0 and i in [0,1]:
                    logger.warning(log_msg)
                    box_kw = 0
                elif box_kw > old_w and i in [0,2]:
                    logger.warning(log_msg)
                    box_kw = box[i]
                elif box_kw > old_h and i in [1,3]:
                    box_kw = box[i]
                ##Not even sure if the box [0] < [2] and stuff? You can make a box regardless as long as this holds I believe
                box[i] = box_kw
            kwargs["box"] = tuple(box)

        if method == "resize":
            img = img.resize(new_size, **kwargs) ##Result is new_size
        else:
            ##Does not result in new_size per say, so it is automatically resized.
            img = img.crop(box=kwargs["box"])
            if img.size != new_size:
                img = img.resize(new_size)

    elif method in {"contain", "pad"}:
        if method == "contain":
            kwargs = {"color": method_arguments.get("color", None)}
            if "method" in method_arguments:
                kwargs["method"] = method_arguments["method"]
        else:
            kwargs = method_arguments

        ##Need to have an alpha channel for padding, in case the background color is None
        if "A" not in img.mode and kwargs.get("color", None) == None:
            if img.mode in ["L", "P"]:
                new_mode = "LA"
            else:
                new_mode = "RGBA"
            img = img.convert(new_mode)

        ##Centering does not need to be sized since it is between 0 and 1 i.e. already relative size
        img = ImageOps.pad(img, new_size, **kwargs) ##Result is new_size
    
    elif method in {"fit", "cover"}:
        
        ##Technically allows for more options as well when using cover but obviously does not matter cause advanced usage
        if method == "cover":
            kwargs = {}
            if "method" in method_arguments:
                kwargs["method"] = method_arguments["method"]
        else:
            kwargs = method_arguments
    
        img = ImageOps.fit(img, new_size, **kwargs)
    else:
        ##Just in case, a default option to ensure it's always correctly sized
        img = ImageOps.fit(img, new_size)
    
    if force_size and img.size != new_size:
        img = ImageOps.fit(img,new_size)

    return img

async def open_image_file_threadsafe(image_path : Union[str,Path]) -> Image.Image:
    """
    Opens an image file without blocking the event loop (I think).
    Does NOT use the `parse_known_image_file` tool.

    Parameters
    ----------
    image_path : Union[str,Path]
        The path to the image to be opened.

    Returns
    -------
    Image.Image
        the opened image
    """
    img = await asyncio.to_thread(Image.open,image_path)
    return img.copy()


    # return img

def parse_weather_icon(condition,night:bool=False,conditionDict:dict=MDI_WEATHER_CONDITION_ICONS, prefix:str="mdi:weather-", suffix:Union[str,Path]=""):
    ##See here https://developers.home-assistant.io/docs/core/entity/weather#recommended-values-for-state-and-condition
    """
    Returns name of an icon corresponding to the given condition from the condition dict. Defaults to mdi icons.
    args:
        condition (str): the weather condition to look for. Default or None will always return the default icon
        night (bool): Will look for the condition in the icons under the night key of the conditionDict. If not found in there, will look in the daytime conditions, otherwise go to default.
        conditionDict (dict): a dict linking conditions to their icons. Must have {default: icon, day: {condition: icon, }, night: {condition: icon}}
        prefix (str): prefix to apply to any string being returned
        suffix (str): suffix to apply to any string being returned
    """


    ##Maybe add a check to see if it returns a valid mdi icon
    if not (conditionDict.get("default",False) or conditionDict.get("day",False) or conditionDict.get("night",False)):
        logger.error(f"A condition dict must have keys default, day and night")
        raise KeyError
    
    if condition in {"default", None}:
        icon_id = conditionDict["default"]

    elif night:
        icon_id = conditionDict["night"].get(condition,conditionDict["day"].get(condition,"default"))
    else:
        icon_id = conditionDict["day"].get(condition,"default")
    
    if icon_id == "default":
        logger.warning(f"Could not find weather condition {condition} in the condition day keys, returning default value")
        icon_id = conditionDict["default"]

    if prefix == None:
        prefix = ""
    
    if suffix == None:
        suffix = ""
    if isinstance(prefix, Path):
        return prefix / f"{icon_id}{suffix}"
    else:
        return f"{prefix}{icon_id}{suffix}"

def save_testImage(PIL_img : Image.Image, filename :str = "test.png", loglevel : Union[str,int] = "INFO"):
    "Saves a pillow image to the test folder. Optionally specify filename and loglevel."
    folder = "./test/"
    filepath = folder + filename
    if isinstance(loglevel,str):
        loglevel = getattr(logging,loglevel)

    PIL_img.save(filepath)
    logger.log(loglevel,f"Saved testimage to {filepath}")

class DrawShapes:
    """
    Provides functions to quickly draw certain shapes by using Pillows ImageDraw library. 
    Except for draw_advanced, all functions have default values for the shape, except the fill parameter, which is determined by the element.
    All functions have a boolean paste value, which will draw the shape and paste the provided image on top of it. If False, it will return the drawn on image without pasting, which may save time if the original image was just an alpha channel, or if the original image needs to be resized for example.
    The ImageDraw object is also returned, but be mindful that this may be of a greater size than the original image, to provide a decent quality of the drawn shapes.
    The size of that object can be gotten by accessing (ImageDraw).im.size.
    """
    MINRESOLUTION = 480
    "The minimum resolution (smallest dimension) of the image when drawing shapes. Prevents pixelly shapes, especially if they're small. "

    shapeTypes = Literal["circle", "square", "rounded_square", "rounded_rectangle", "octagon", "hexagon","ADVANCED"]
    "All the implemented shape functions."

    @classmethod
    def get_draw_function(cls, shape : shapeTypes) -> Callable[[Image.Image, dict, bool, list[str]],tuple[Image.Image, ImageDraw.ImageDraw]]:
        """
        Helper function to return the draw function from string.

        Parameters
        ----------
        shape : "circle", "square", "rounded_square", "rounded_rectangle", "octagon", "hexagon","ADVANCED"
            string indicating what shape to draw

        Returns
        -------
        Callable[[Image.Image, dict, bool, list[str]],tuple[Image.Image, ImageDraw.ImageDraw]]
            The function that draws the shape. Returns 
        """

        if shape == "circle":
            return cls.draw_circle
        elif shape == "square":
            return cls.draw_square
        elif shape == "rounded_square":
            return cls.draw_rounded_square
        elif shape == "rounded_rectangle":
            return cls.draw_rounded_rectangle
        elif shape == "hexagon":
            return cls.draw_hexagon
        elif shape == "octagon":
            return cls.draw_octagon
        elif shape == "ADVANCED":
            return cls.draw_advanced
        else:
            msg = f"{shape} is not recognised as a valid draw shape"
            logger.error(ValueError(msg))

    @classmethod
    def get_relative_size(cls, shape : shapeTypes) -> float:
        """
        Helper function to return a relative size for (mdi) icons (compared to the default size that would be used)
        Keep in mind, when using the advanced drawing shape, you need to determine the size yourself (the returned value is 1)
        
        Parameters
        ----------
        shape : "circle", "square", "rounded_square", "rounded_rectangle", "octagon", "hexagon","ADVANCED"
            string indicating what will be drawn

        Returns
        -------
        float
            Value between 0 and 1 indicating the relative size
        """

        if shape == "circle":
            return 0.71
        elif shape == "square":
            return 0.825
        elif shape == "rounded_square":
            return 0.8
        elif shape == "rounded_rectangle":
            return 0.825
        elif shape == "hexagon":
            return 0.65
        elif shape == "octagon":
            return 0.65
        elif shape == "ADVANCED":
            return 1
        else:
            msg = f"{shape} is not recognised as a valid draw shape"
            logger.error(ValueError(msg))  

    @classmethod
    def rescale(cls, dimension : Union[int,float,list[int], tuple[int]], factor : float) -> Union[int,list,tuple]:
        """
        rescales the provided dimension. For iterables, it will iterate through all elements and scale integers and floats.

        Parameters
        ----------
        dimension : Union[int,float,list[int], tuple[int]]
            The dimension(s) to scale. Can handle strings, which are just returned as themselves.
        factor : float
            The factor with which to scale the dimension (as dim*factor)
        """
        if isinstance(dimension,(float,int)):
            return int(dimension*factor)
        elif isinstance(dimension,str):
            return dimension
        elif isinstance(dimension,(list,tuple)):
            dim_list = []
            for dim in dimension:
                dim_list.append(cls.rescale(dim,factor))
            dimType = type(dimension)
            return dimType(dim_list)

    @classmethod
    def get_mask(cls, img : Image.Image, min_resolution=MINRESOLUTION) -> tuple[Image.Image, float]:
        """
        Makes a mask image with a set resolution to draw on and paste onto the original image.
        args:
            min_resolution (int): minimum resolution of the mask. Defaults to drawShapes.MINRESOLUTION
        """
        if not isinstance(min_resolution,int):
            raise TypeError("Resolution must be of integer type")

        mask = Image.new(img.mode, img.size)
        if min(min_resolution,mask.width,mask.height) != min_resolution:
            mask = ImageOps.cover(mask, size=(min_resolution,min_resolution))
        scale = mask.width/img.width
        return (mask, scale)

    @classmethod
    def paste(cls, img: Image.Image, mask: Image.Image, is_background: bool = False):
        """Pastes the mask onto the original img, or vice_versa

        Parameters
        ----------
        img : Image.Image
            The original image
        mask : Image.Image
            The mask (drawn on) image with the shape
        is_background : bool, optional
            Whether to consider the mask as the background image, by default False

        Returns
        -------
        Image.Image
            The image after pasting
        """

        if is_background:
            top_img = img
            bottom_img = mask
        else:
            top_img = mask
            bottom_img = img
        
        if img.mode == "RGBA":
            bottom_img.alpha_composite(top_img)
        else:
            bottom_img.paste(top_img, mask=top_img.getchannel("A"))
        
        return bottom_img

    @classmethod
    def draw_circle(cls, img : Image.Image, drawArgs : dict = {}, paste: bool = True, is_background: bool = False, rescale : list[str]=["xy", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws a circle onto the center of the given image by calling ImageDraw.pieslice.
        """        
        color_keys = ["fill","outline"]
        (mask, scale) = cls.get_mask(img)

        if img.width != img.height:
            r = min(mask.width,mask.height)/2
            r = int(r-1)
            Or = (int(mask.width/2), int(mask.height/2))

            xy = [(Or[0]-r,Or[1]-r), (Or[0]+r, Or[1]+r)]
        else:
            xy = [(0,0), (mask.width-1,mask.height-1)]

        defaultArgs = {"xy": xy, "start":0,"end": 360}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value
        
        logger.debug(f"Drawing pieslice with arguments {args}")
        drawImg = ImageDraw.Draw(mask)
        drawImg.pieslice(**args)
        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        
        if paste:
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)
    
    @classmethod
    def draw_square(cls, img : Image.Image, drawArgs : dict = {}, paste=True, is_background: bool = False, rescale : list[str]=["xy", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws a square onto the center of the given image by calling ImageDraw.rectangle
        """

        color_keys = ["fill","outline"]
        (mask, scale) = cls.get_mask(img)
        if mask.width == mask.height:
            coords = [(0,0), (mask.width,mask.height)]
        else:
            side = min(mask.width,mask.height)/2 ##Not actually a side but half of it but hey
            mid = (mask.width/2,mask.height/2)
            coords = [
                (floor(mid[0]-side), floor(mid[1]-side)),
                (floor(mid[0]+side), floor(mid[1]+side))]

        defaultArgs = {"xy":coords}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value
        
        logger.debug(f"Drawing square with arguments {args}")

        drawImg = ImageDraw.Draw(mask)
        drawImg.rectangle(**args)

        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)
    
    @classmethod
    def draw_rounded_rectangle(cls, img : Image.Image, drawArgs : dict = {}, paste : bool = True, is_background: bool = False, rescale : list[str]=["xy", "radius", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws a square with rounded corners onto the given image.
        drawArgs : dict with parameters to pass to the drawing.
            Default values for:
                xy (list[tuple,tuple]): the [(x,y),(x,y)] bounding box coordinates
                radius (int): radius of the corners, defaults to a quarter of the smallest dimension. 
        paste : paste drawing on the original image, or return the drawing without pasting
        scale : scale any arguments in this list that are in drawArgs
        """
        color_keys = ["fill","outline"]

        (mask, scale) = cls.get_mask(img)
        radius = min(mask.width,mask.height)/4
        defaultArgs = {"xy":[(0,0), (mask.width,mask.height)], "radius": radius}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value
        
        logger.debug(f"Drawing rounded rectangle with arguments {args}")

        drawImg = ImageDraw.Draw(mask)
        drawImg.rounded_rectangle(**args)

        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:   ##Maybe rename paste to is_background or something. And keep pasting capabilities
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)
    
    @classmethod
    def draw_rounded_square(cls, img : Image.Image, drawArgs : dict = {}, paste: bool = True, is_background: bool = False, rescale : list[str]=["xy", "radius", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws a square with rounded corners onto the given image. Default size is the entire image
        """   

        color_keys = ["fill","outline"]
        (mask, scale) = cls.get_mask(img)   
        if mask.width == mask.height:
            coords = [(0,0), (mask.width,mask.height)]
        else:
            side = min(mask.width,mask.height)/2 ##Not actually a side but half of it but hey
            mid = (mask.width/2,mask.height/2)
            coords = [
                (floor(mid[0]-side), floor(mid[1]-side)),
                (floor(mid[0]+side), floor(mid[1]+side))]
        radius = min(mask.width,mask.height)/4

        defaultArgs = {"xy":coords, "radius":radius}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value
        
        logger.debug(f"Drawing rounded square with arguments {args}")
        drawImg = ImageDraw.Draw(mask)
        drawImg.rounded_rectangle(**args)

        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)
    
    @classmethod
    def draw_regular_polygon(cls, img : Image.Image, drawArgs : dict = {}, paste: bool = True, is_background: bool = False, rescale : list[str]=["bounding_circle", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws a regular polygon onto the given image by calling ImageDraw.regular_polygon
        """
        if "n_sides" not in drawArgs:
            raise KeyError("Calling draw_regular_polygon requires 'n_sides' to be defined in the drawArgs dict.")

        color_keys = ["fill","outline"]
        (mask, scale) = cls.get_mask(img)
        radius = min(mask.width,mask.height)/2
        coords = (floor(mask.width/2), floor(mask.height/2), floor(radius))

        defaultArgs = {"bounding_circle":coords}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value
        
        logger.debug(f"Drawing octagon with arguments {args}")

        drawImg = ImageDraw.Draw(mask)
        drawImg.regular_polygon(**args)
        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:
            if img.mode == "RGBA":
                mask.alpha_composite(img)
            else:
                mask.paste(img,mask=img.getchannel("A"))
            return (mask, drawImg)
        else:
            return(mask, drawImg)
    
    @classmethod
    def draw_octagon(cls, img : Image.Image, drawArgs : dict = {}, paste: bool = True, is_background: bool = False, rescale : list[str]=["bounding_circle", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws an octogon onto the given image by calling ImageDraw.regular_polygon with n_sides = 8
        """

        color_keys = ["fill","outline"]
        defaultArgs = {"n_sides":8}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value

        (mask,drawImg) = cls.draw_regular_polygon(img,args, paste=False)
        scale = mask.width/img.width

        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)

    @classmethod
    def draw_hexagon(cls, img : Image.Image, drawArgs : dict = {},paste: bool = True, is_background: bool = False, rescale : list[str]=["bounding_circle", "width"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws an octogon onto the given image by calling ImageDraw.regular_polygon with n_sides = 8
        """
        color_keys = ["fill","outline"]
        defaultArgs = {"n_sides":6}
        args = defaultArgs
        for key,value in drawArgs.items():
            if key in rescale:
                value = cls.rescale(value,scale)
            if key in color_keys:
                value = get_Color(value,img.mode)
            args[key] = value

        (mask,drawImg) = cls.draw_regular_polygon(img,args, paste=False)
        scale = mask.width/img.width

        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
        if paste:
            img = cls.paste(img,mask, is_background)
            return (img, drawImg)
        else:
            return(mask, drawImg)

    @classmethod
    def draw_advanced(cls, img : Image.Image, method : str, drawArgs : dict, paste: bool = True, is_background: bool = False, use_mask=True, rescale : list[str]=[]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """
        Draws any method from ImageDraw onto image. Returns the ImageDraw object gotten from ImageDraw.Draw(img).
        Not all color strings work here, only those native to PIL.
        Arguments:
            img: Pillow image to draw on
            drawType (str): the method to call for drawing. See https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html#methods
            drawArgs (dict): Dict containing keyword arguments and values to pass to the draw method.
            paste (bool): Paste the drawn shape onto the original image? (Applicable if use_mask is true)
            use_mask (bool): Use a mask to ensure a decent shape resolution. Resolution applied is drawShapes.MINRESOLUTION. Keep in mind drawArgs are not changed, so any numeric values may need tweaking.
        """
        if not use_mask:
            drawImg = ImageDraw.Draw(img)
            drawFunc = getattr(drawImg,method)
            logger.debug(f"Advanced drawing type returned method {drawFunc}.")
            for arg in rescale:
                if arg in drawArgs:
                    value = cls.rescale(value,scale)
                    drawArgs[arg] = value

            drawFunc(**drawArgs)
            return (img,drawImg)
        else:
            (mask, scale) = cls.get_mask(img)
            drawImg = ImageDraw.Draw(mask)
            drawFunc = getattr(drawImg,method)
            logger.debug(f"Advanced drawing type returned method {drawFunc}.")
            for arg in rescale:
                if arg in drawArgs:
                    value = cls.rescale(value,scale)
                    drawArgs[arg] = value
                    
            drawFunc(**drawArgs)
            mask = mask.resize(img.size, Image.Resampling.LANCZOS)
            if paste:
                img = cls.paste(img,mask, is_background)
                return (img, drawImg)
            else:
                return (mask,drawImg)
            
