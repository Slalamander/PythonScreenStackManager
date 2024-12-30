"Base elements for PSSM. Not all of these are usable as it, but are supposed to be used as parent classes."

import asyncio
from datetime import datetime as dt, timedelta
from math import floor, ceil
import logging
import re
from itertools import cycle
from functools import partial
from typing import TYPE_CHECKING, Callable, Union, Optional, Literal, \
                    TypeVar, Any, TypedDict, Coroutine
from types import MappingProxyType
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps,\
                ImageFile
import mdi_pil as mdi
from mdi_pil import mdiType

from .. import constants as const
from ..constants import FuncExceptions, \
                DEFAULT_FEEDBACK_DURATION

from .constants import DEFAULT_FONT, \
    DEFAULT_FONT_SIZE, DEFAULT_BADGE_LOCATION, MISSING_PICTURE_ICON, MISSING_ICON, DEFAULT_ICON, \
    ALLOWED_BADGE_SETTINGS

from .constants import CoordType, ColorType, \
            DEFAULT_FOREGROUND_COLOR, DEFAULT_ACCENT_COLOR, DEFAULT_BACKGROUND_COLOR, DEFAULT_MENU_HEADER_COLOR, DEFAULT_FONT_HEADER, DEFAULT_BLUR_POPUP_BACKGROUND
from ..pssm_types import *

from .. import tools
from ..tools import DummyTask, DrawShapes

from ..pssm.styles import Style
from ..pssm.util import colorproperty, elementaction, elementactionwrapper

if TYPE_CHECKING:
    from ..pssm.screen import PSSMScreen as Screen
    
_LOGGER = logging.getLogger(__name__)

class DummyScreen:
    "DummyScreen to act as a placeholder when importing."
    printing = False
    mainLoop = None
    elementRegister = {}
    defaultColor = "white"

# ########################## - VARIABLES - ####################################
ImageFile.LOAD_TRUNCATED_IMAGES = True

##Usage: each key has a function to draw the shape, and a multiplier for the icon size compared to the smallest dimension of the image
shapeType = TypeVar("Shape", bound=str)

IMPLEMENTED_ICON_SHAPES : dict[shapeType, tuple[DrawShapes,float]] = {
                        "circle": (DrawShapes.draw_circle, DrawShapes.get_relative_size("circle")), 
                        "square": (DrawShapes.draw_square, DrawShapes.get_relative_size("square")),
                        "rounded_square": (DrawShapes.draw_rounded_square, DrawShapes.get_relative_size("rounded_square")), 
                        "rounded_rectangle": (DrawShapes.draw_rounded_rectangle, DrawShapes.get_relative_size("rounded_rectangle")),
                        "octagon": (DrawShapes.draw_octagon, DrawShapes.get_relative_size("octagon")),
                        "hexagon": (DrawShapes.draw_hexagon, DrawShapes.get_relative_size("hexagon")),
                        }   ##Maybe implement None as a string into this for easier parsing; currently seems to cause some issues tho
"Preimplemented background shapes to draw icons on. each key has a value tuple with (drawfunction, relative_iconsize)"

IMPLEMENTED_ICON_SHAPES_HINT = Literal[None, "circle", "square", "rounded_square", "rounded_rectangle", "octagon", "hexagon","ADVANCED"]

# ########################## - Core Element    - ##############################

class Element(ABC):
    """
    Everything which is going to be displayed on the screen is an Element. Accepts all keyword arguments when defining it, and sets them as object attributes so they can be used to store data too.

    Parameters
    ----------
    id : str, optional
        custom ID for this element, with which it can be found in the element register. Duplicate ID's are not allowed. 
        Otherwise set automatically (meaning it is the element's uniqueID), by default None
    area : PSSMarea, optional
        The area of the element, by default None
        Generally this is set by parent Layouts anyways, so there is no need to bother with it
    imgData : Image.Image, optional
        Optionally force the Image data, but will be overwritten when generating, by default None
    tap_action : InteractionFunctionType, optional
        An action to call when interacting (tapping) this element, by default None
        See the docstring for the property on usage
    background_color : Optional[ColorType], optional
        color of the element's background, by default None
    isInverted : bool, optional
        Invert the element image before printing, by default False
    show_feedback : bool, optional
        Show feedback when interacting with the element, by default None
    feedback_duration : Union[float,DurationType], optional
        The duration to show the feedback, by default DEFAULT_FEEDBACK_DURATION
    _register : Optional[bool], optional
        Register this element, by default None
        If None, element's are automatically registered before printing has started, and after printing starts, only elements with custom ID's are registered.
    """
    
    @classproperty
    def color_properties(cls) -> set:
        "Set containing all color properties of an element"
        return colorproperty._get_class_colors(cls)

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return {"generate": "async_generate", "update": "async_update_action"}
    
    @property
    def _emulator_icon(cls): return "mdi:shape"
    "Icon to use in the element tree of the emulator"

    def __init_subclass__(cls, *args, **kwargs):
        ##Method gotten from: https://stackoverflow.com/questions/71183263/automatically-call-method-after-init-in-child-class
        ##Cannot use a metaclass for this, which would've probably been preferred, as it messes up other elements that already have metaclasses
        super().__init_subclass__(*args, **kwargs)
        init = cls.__init__
        def new_init(self, *args, **kwargs):
            asyncio.set_event_loop(self.screen.mainLoop)
            id = kwargs.get("id",None)
            _register = kwargs.get("_register",None)
            init(self, *args, **kwargs)
            if cls is type(self):
                self.__post_init__(id, _register)
        cls.__init__ = new_init

    def __post_init__(self, id, _register):

        if self.screen == None:
            return

        if _register == None:
            _register = not self.parentPSSMScreen.printing if id == None else True
        if _register:
            self.parentPSSMScreen._register_element(self)
        return

    def __new__(cls, *args, **kwargs):
        ##Ensure that the id and unique id are set immediately, which allows for things like __repr__ and __hash__ to work when __init__ starts.
        instance = super().__new__(cls)
        id = kwargs.get("id",None)
        (instance.__id, instance.__unique_id) =  instance.__set_id(id)
        return instance

    def __init__(self,  id: str =None, area: PSSMarea=None, imgData: Image.Image = None, 
                tap_action: InteractionFunctionType = None,
                hold_action: InteractionFunctionType = None,
                hold_release_action: InteractionFunctionType = None,
                background_color: Optional[ColorType] = None,
                isInverted: bool = False, show_feedback: bool = None,
                feedback_duration: Union[float,DurationType] = DEFAULT_FEEDBACK_DURATION, forcePrintOnTop: bool = False,
                _register : Optional[bool] = None,
                **kwargs):
        
        self.__id: str
        self.__unique_id: str

        if asyncio._get_running_loop() == None and Screen != None:
            ##Locks need to actually be created in a running loop.
            ##May even have to check if the loop should be changed back later.
            asyncio.set_event_loop(self.parentPSSMScreen.mainLoop)
        
        self._requestGenerate = True
        "This variable is used to signal to parentLayouts that this element was updated, and needs to be regenerated."

        self.__generatorLock = asyncio.Lock()
        self.__updateLock = asyncio.Lock()
        self._feedbackTask : asyncio.Task = DummyTask()
        "asyncio task that handles the elements feedback function"

        self._parentLayout : Layout = None
        self._parentLayouts = []
        self._isPopup = False
        self._isTemporaryInverted = False

        self._imgData = imgData
        self._area = area
        self.background_color = background_color
        
        self._tap_action = None
        self.tap_action_data = {}
        self.tap_action_map = {}
        self.tap_action = tap_action

        self._hold_action = None
        self.hold_action_data = {}
        self.hold_action_map = {}
        self.hold_action = hold_action

        self._hold_release_action = None
        self.hold_release_action_data = {}
        self.hold_release_action_map = {}
        self.hold_release_action = hold_release_action

        self._isInverted = isInverted
        self._inverted = isInverted
        
        if show_feedback == None:
            show_feedback = True if tap_action != None else False
        self.show_feedback = show_feedback
        self.feedback_duration = feedback_duration

        for param in kwargs:
                if not hasattr(self, param): setattr(self, param, kwargs[param])

        if self.isLayout:
            generatorClass = self.generator.__qualname__.split(".")[0]
            generateClass = self.async_generate.__qualname__.split(".")[0]

            if self.__class__.__name__ in generatorClass and generateClass != generatorClass:
                msg = f"{self}: custom layout generators need to also have async_generate defined"
                _LOGGER.warning(msg)

    #region Element Properties
    @property
    def id(self) -> str:
        "The element id. Can be set when instantiating the element, but must be unique too."
        return self.__id
    
    @property
    def unique_id(self) -> str:
        "The unique, automatically generated id of this element"
        return self.__unique_id

    @property
    def imgData(self) -> Image.Image:
        return self._imgData

    @property
    def isLayout(self) -> bool:
        "Returns whether the element is a layout"
        return False
    
    @colorproperty
    def background_color(self) -> Union[ColorType,None]:
        "Color of the element background. Set to None to take on the color of its parent layout"
        return self._background_color
        
    @property
    def isInverted(self) -> bool:
        "True if the element is currently shown as inverted. Can be due to a temporary inversion (hardware inversion), a parent layout element or if inverted is true and it is printed as such."
        return self._isInverted

    @property
    def inverted(self) -> bool:
        "True if the default inverted state of the element is inverted (i.e. the image made in the generator will be inverted if true)."
        return self._inverted

    @property
    def isTemporaryInverted(self) -> bool:
        """
        Returns true show_feedback is true and invert Element has been called.
        """
        return self._isTemporaryInverted

    @property
    def feedback_duration(self) -> float:
        """
        Duration of the element's feedback function, before returning to its normal state
        Can be set to a string, which will be parsed to the right amount of seconds.
        """
        return self._feedback_duration
    
    @feedback_duration.setter
    def feedback_duration(self, value):
        if isinstance(value,str):
            parse = tools.parse_duration_string(value)
            if parse != None:
                value = parse

        if not isinstance(value, (int,float)):
            msg = f"Feedback duration must be either a valid duration string, or an interger or float. {value} is not valid."
            _LOGGER.exception(TypeError(msg))

        self._feedback_duration = value

    @property
    def feedbackTask(self) -> asyncio.Task:
        "Asyncio task that is ran when showing feedback."
        return self._feedbackTask

    @property
    def mainLoop(self) -> Optional[asyncio.BaseEventLoop]:
        "The mainloop of the screen"
        return Screen.get_screen().mainLoop

    @property
    def isGenerating(self) -> bool:
        "True if the elements generate function is running."
        if not hasattr(self, "_generatorLock"):
            return True
        return self._generatorLock.locked()

    @property
    def isUpdating(self) -> bool:
        "True if the element is currently updating"
        if not hasattr(self, "_updateLock"):
            return True
        return self.__updateLock.locked()

    @property
    def _generatorLock(self) -> asyncio.Lock:
        "This lock is set when calling `element.generate()`, and is meant to ensure that there aren't multiple threads generating it."
        return self.__generatorLock

    @property
    def _updateLock(self) -> asyncio.Lock:
        "The Lock object that ensures only one update cycle of this element can run at a time."
        return self.__updateLock

    @property
    def area(self) -> PSSMarea:
        """ Returns the area of the element, as [(x,y), (w,h)]"""
        return self._area
    
    @property
    def screen(self) -> "PSSMScreen":
        return Screen.get_screen()

    @property
    def parentPSSMScreen(self) -> "PSSMScreen":
        "The pssm screen objected associated with the element"
        return Screen.get_screen()
    
    @property
    def onScreen(self) -> bool:
        "True if the element is currently in the screen stack, or one of its parentLayouts is."
        b = False
        if (self in self.parentPSSMScreen.stack or
            (getattr(self,"parentLayouts",[]) and self.parentLayouts[0] in self.parentPSSMScreen.stack)):
            b = True
        return b

    @property
    def parentLayout(self) -> "Layout":
        "The first immediate layout containing this element, that is not a SubLayout"
        if not hasattr(self,"_parentLayout"):
            return None
        if self._parentLayout != None and getattr(self._parentLayout,"_isSubLayout",False):
            return self._parentLayout.parentLayout
        return self._parentLayout

    @property
    def parentLayouts(self) -> tuple["Layout"]:
        "Tuple with all the parent layouts of this element. Index 0 is the oldest parent."
        if self in self.parentPSSMScreen.stack or self.parentLayout == None:
            ##Technically, for elements directly in the stack, the parentlayout should be none too.
            return ()

        l = list(self.parentLayout.parentLayouts)
        l.append(self.parentLayout)
        return tuple(l)

    @property
    def isPopup(self) -> bool:
        "True if the element is a popup"
        return self._isPopup
    
    #Tap-action

    @elementaction
    def tap_action(self) -> InteractionFunctionType: 
        """
        The function called when the element is tapped. Set to None to have nothing called.
        If set to a dict, the values for tap_action_data and tap_action_map will be overwritten if the respective key is present.
        """
        return self._tap_action 
    
    @elementaction
    def hold_action(self) -> InteractionFunctionType: 
        """
        The function called when the element is held. Set to None to have nothing called.
        If set to a dict, the values for hold_action_data and hold_action_map will be overwritten if the respective key is present.
        """
        return self._hold_action 
    
    @elementaction
    def hold_release_action(self) -> InteractionFunctionType:
        """
        The function called when the element is held. Set to None to have nothing called.
        If set to a dict, the values for hold_release_action_data and hold_release_action_map will be overwritten if the respective key is present.
        """
        return self._hold_release_action 

    @property
    def parentBackground(self) -> Union[ColorType,None]:
        """
        The background color of the youngest parent layout of this element with a background defined.
        Returns None if no layout have its color set.
        If the element is a layout itself, and the background is set, will return that value.
        """
        for parent in reversed(self.parentLayouts):
            if parent.background_color != None:
                return parent.background_color
        else:
            return None
    
    @property
    def parentBackgroundColor(self) -> ColorType:
        "The assumed color of the parent background, in case none have a color defined. If it is determined to be an image, returns the default device color"
        if self.parentBackground == None or isinstance(self.parentBackground,Image.Image):
            if Style.is_valid_color(self.parentPSSMScreen.background):
                return self.parentPSSMScreen.background
            else:
                return self.parentPSSMScreen.device.defaultColor
        else:
            return self.parentBackground
    #endregion

    @classmethod
    def __set_id(cls, id):
        ##Automatically determines the last used ID for a given element classes, and increases it by 1
        ##That way, any element's unique id should be, in fact, unique, but also still readable
        c = cls.__name__
        idattr = f"_{c}__last_id"
        if hasattr(cls,idattr):
            new_id = getattr(cls,idattr) + 1
            setattr(cls,idattr,new_id)
        else:
            setattr(cls,idattr,0)
            new_id = 0
        Eltid = f"{cls.__name__}_{new_id}"
        if id == None:
            id = Eltid
        return (id, Eltid)

    def __repr__(self):
        if not hasattr(self,"id") or not hasattr(self,"unique_id"):
            ##In case the element has not been fully initialised yet
            ##This should not be a problem anymore since the id's are set in __new__
            return super().__repr__()
        if self.id != self.unique_id:
            return f"{self.unique_id}: {self.id}"
        else:
            return f"{self.id}"

    def __hash__(self):
        return hash(self.unique_id)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.unique_id == other.unique_id
        return NotImplemented

    def __update_attributes(self, updateAttributes={}) -> bool:
        updated = False
        for param in updateAttributes:
            if not hasattr(self,param) and self.parentPSSMScreen.printing:
                msg = f"{self.id} does not have attribute {param}. Call add_attribute if you want to add attributes during printing."
                _LOGGER.exception(AttributeError(msg))
            else:
                if getattr(self,param) != updateAttributes[param]:
                    setattr(self, param, updateAttributes[param])
                    updated = True
        return updated

    async def _async_update_attributes(self, updateAttributes = {}) -> bool:
        """
        Safety function to ensure the element does not generate while its attributes are being updated, because that can cause errors.
        Generally no need to call this, async_update takes care of that

        Parameters
        ----------
        updateAttributes : dict, optional
            The attributes to update, by default {}

        Returns
        -------
        bool :
            whether any attributes have been updated
        """        
        async with self._generatorLock:
            updated = self.__update_attributes(updateAttributes)
            return updated

    @elementactionwrapper.method
    def update(self, updateAttributes={}, skipGen=False, forceGen:bool = False,  skipPrint=False,
                reprintOnTop=False, updated : bool = False):
        """
        Pass a dict as argument, and it will update the attributes. Passes it on to _async_update, so execution does not wait until the element is done updating.  
        Note:
            Updating an element can be very slow ! It depends on every specific
            cases, but know there are a few ways to make it faster:
            - Use `screen.start_batch_writing()` and `screen.stop_batch_writing()`. This skips generating until the batch is stopped.
            - If you know this specific element is on top of the screen, use:
                `elt.update(updateAttributes=myDict, reprintOnTop=True)`
                Which will do the same, except it won't rebuild the whole stack
                image, it will just print this object on top. (On my tests, I
                could spare up to 0.5s !)

        Parameters
        ----------
        updateAttributes : dict, optional
            The element's attributes to update. If the attribute is not defined, a warning is issued, by default {}
        skipGen : bool, optional
            Just update the element's attribute, but do not do any generation
        forceGen : bool, optional
            Set to true to call the generator even if no attributes were updated, by default False
        skipPrint : bool, optional
            Do not update the screen, but do regenerate if needed, by default False
        reprintOnTop : bool, optional
            do not reprint the whole stack, but print this element on top of the screen. (much faster when possible), by default False
        updated : bool, optional
            Indicate this element was previously updated, to ensure reprinting goes correctly.
            Automatically becomes true if any of the attributes in `updateAttributes` changes, by default False
            Useful when working with layouts, and updating subelements first before reprinting.
        """

        if not self.parentPSSMScreen.printing:
            attr_updated = self.__update_attributes(updateAttributes)

        else:
            attr_updated = False
            for param in updateAttributes:
                if not hasattr(self,param) and self.parentPSSMScreen.printing:
                    _LOGGER.warning(f"{self.id} does not have attribute {param}. Call add_attribute if you want to add attributes during printing.")
                else:
                    if getattr(self,param) != updateAttributes[param]:
                        attr_updated = True
                        break
            asyncio.run_coroutine_threadsafe(self.async_update(updateAttributes, skipGen, forceGen, skipPrint,
                    reprintOnTop, updated), self.mainLoop)
        return (updated or attr_updated)

    @elementactionwrapper.method
    async def async_update(self, updateAttributes={}, skipGen=False, forceGen:bool = False,  skipPrint=False,
            reprintOnTop=False, updated : bool = False) -> bool:          
        """
        async implementation of update. Pass a dict as argument, and it will update the Element's attributes. Returns a boolean to indicate if the element was updated.
        
        Parameters
        ----------
        updateAttributes : dict, optional
            The element's attributes to update. If the attribute is not defined, a warning is issued, by default {}
        skipGen : bool, optional
            Just update the element's attribute, but do not do any generation
        forceGen : bool, optional
            Set to true to call the generator even if no attributes were updated, by default False
        skipPrint : bool, optional
            Do not update the screen, but do regenerate if needed, by default False
        reprintOnTop : bool, optional
            do not reprint the whole stack, but print this element on top of the screen. (much faster when possible), by default False
        updated : bool, optional
            Indicate this element was previously updated, to ensure reprinting goes correctly.
            Automatically becomes true if any of the attributes in `updateAttributes` changes, by default False
            Useful when working with layouts, and updating subelements first before reprinting.

        Returns
        -------
        bool
            Whether any attributes were updated (or if updated was set to `True`, if will also return `True`)
        """

        if self._updateLock.locked():
            update_list = []
            for elt in self.parentPSSMScreen.elementRegister.values():
                if elt._updateLock.locked():
                    update_list.append(elt)
            _LOGGER.debug(f"{self.id} waiting to acquire update lock. {len(update_list)} elements are waiting")

        async with self._updateLock:
            upd_attr = await self._async_update_attributes(updateAttributes)        
            updated = (upd_attr or updated)

            if not updateAttributes and not forceGen and not updated:
                msg = f"Element {self.id} update was called, but no attributes were updated and not regenerated."
                _LOGGER.debug(msg)
                return False

            ##Hoping this will allow tasks that update subElements to run first
            await asyncio.sleep(0)

            if skipGen:
                pass
            elif not updated and not forceGen:
                pass
            else:
                isBatch = self.parentPSSMScreen.isBatch
                if reprintOnTop:
                    _LOGGER.debug("Printing on Top")
                    if forceGen:
                        await self.async_generate()
                    await asyncio.to_thread(self.parentPSSMScreen.simple_print_element,element=self, skipGen=skipGen, apply_background=True)
                    return updated
                elif not isBatch and updated and self.onScreen:

                    ##Commented out the stuff below since print_stack already calls all the generators
                    ##Commenting that out apparently breaks HA trigger_functions

                    # We don't want unncesseray generation when printing batch
                    if self.isLayout or isinstance(self,Layout):
                        self : Layout
                        c = [elt._await_update() for elt in self.create_element_list()]
                        await asyncio.gather(*c, return_exceptions=True)
                        _LOGGER.debug(f"{self}: Child elements finished updating")

                    if self.parentLayouts:
                        # We recreate the pillow image of the oldest parent
                        # And it is not needed to regenerate standard objects, since those will be pasted over
                        # So all parent layouts are regenerated, after which print_stack is called, which simply grabs the imgData, which is kept in memory.
                        oldest_parent: Layout = self.parentLayouts[0]
                        
                        parentupdate = False
                        for parent in self.parentLayouts:
                            if parent != None and parent.isUpdating: 
                                parentupdate = True
                                break

                        if parentupdate: ##The parent element will take care of printing later or (unless it has skipprint on but that's usually your own responsibillity)
                            skipPrint = True
                            await self.async_generate()
                        else:
                            #Request the parentLayout to regenerate this element. Safety measure is in place to regenerate the parent if the element was not generated.
                            self._requestGenerate = True
                            if oldest_parent.isGenerating:
                                ##Wait for the oldest parent to finish generating. If 
                                _LOGGER.debug(f"{self}: Waiting for {oldest_parent.id} to finish generating")
                                await oldest_parent._await_generator()

                            if self._requestGenerate:
                                ##This will ensure the parent is up to date
                                await oldest_parent.async_generate(skipNonLayoutGen=True)

                    else:
                        await self.async_generate(skipNonLayoutGen=True)
                    # Then, let's reprint the stack
                    if not skipPrint:
                        ##Gotta force the layout gen? --> yes to update, but not commenting out and regenerating the layouts without the elements is by far faster.
                        await self.parentPSSMScreen.print_stack(area=self.area)
                elif forceGen:
                    if self.isGenerating:
                        _LOGGER.info(f"Waiting for {self.id} to finish generating")
                        await self._await_generator()
                    await self.async_generate()
            
            return updated

    async def async_update_action(self, *args, force_element_update: bool = False, **kwargs):
        """Function to update an element via actions.

        Catches out all positional arguments. Any non specified keyword arguments are passed as updateAttributes

        Parameters
        ----------
        force_element_update : bool, optional
            Forcibly set the element's update status to True, by default False
        """        
        if kwargs:
            _LOGGER.log(5, f"{self}: calling update via update_action")
            await self.async_update(updateAttributes=kwargs, updated=bool(force_element_update))
        return

    def _convert_dimension(self, dimension : Union[int,float,str,list,tuple], variables : dict ={}):
        """
        Converts the user dimension input (like `"h*0.1"`) to to proper integer
        amount of pixels.
        Basically, you give it a string. And it will change a few characters to
        their corresponding value, then return the evaluated string.
        The main usage is for the dimension strings, however it also accepts integers and float for ease of use.
        Floats are returned as floored integers (i.e. rounded to the closest integer < dimension)
        Lists or tuples are returned as lists or tuples with strings and floats converted to integers. Can't guarantee it will work when questionmark dimensions are present in the list/tuple.
        
        Examples
        --------
            I HIGHLY recommend doing only simple operation, like `"H*0.1"`, or
            `"W/10"`, always starting with the corresponding variable.\n
            But you can if you want do more complicated things:
                - `elt._convert_dimension("H+W")` ->  screen_height + screen_width
                - `elt._convert_dimension("p*300+max(w, h)")` -> 300 + max(element_width, element_height)
        
        Paramaters
        ----------
            dimension: the dimension, or iterable of dimensions, to convert
            variables (dict): dict with additional variable key value pairs to evaluate, along with `'W'`,`'H'`,`'w'`,`'h'`  and `'?'`

        Note:
            When using question mark dimension (like `"?*2"`), the question mark
            MUST be at the beginning of the string. I'd advice using question mark dimensions only in Layouts as well.
        """

        if isinstance(dimension,(list,tuple)):
            dim_list = []
            for dim in dimension:
                dim_list.append(self._convert_dimension(dim,variables))
            dimType = type(dimension)
            return dimType(dim_list)
        
        if isinstance(dimension, int):
            return dimension
        elif isinstance(dimension,float):
            return floor(dimension)
        elif isinstance(dimension, str):
            nd = ""
            W = self.parentPSSMScreen.width
            H = self.parentPSSMScreen.height
            if getattr(self,"area", None):
                (x, y), (w, h) = self.area
            else:
                # area not defined. Instead of being stuck, let's assume the
                # screen height and width are a decent alternative
                w, h = W, H

            dimVars = {"W":W,"H":H,"w":w, "h":h,"P":1,"p":1}
            dimVars.update(variables)
            if dimension[0] == '?':
                for c in dimension:
                    if c in variables:
                        nd += str(variables[c])
                    else:
                        nd += c

                # We return the string, another function in the (parent)Layout will take care of
                # evaluating it
                return nd
            else:
                return int(eval(dimension,dimVars))
        else:
            _LOGGER.warning("Could not parse the dimension")
            return dimension

    def add_attributes(self, newAttributes : dict = {}, overwrite=False, update=False):
        """
        adds attributes in newAttributes to the element. By default does not apply already existing attributes. 

        Parameters
        ----------
        newAttributes : dict, optional
            dict with the new attributes to add and their values, by default {}
        overwrite : bool, optional
            overwrite attributes that already exist? by default False
        update : bool, optional
            update the element (and reprint) after setting the new attributes? by default False

        Raises
        ------
        AttributeError
            _description_
        """        

        for k,v in newAttributes.items():
            if hasattr(self,k) and not overwrite and self.parentPSSMScreen.printing:
                msg = f"{self.id} already has attribute {k}"
                _LOGGER.error(msg)
                if const.RAISE: raise AttributeError(msg)
            else:
                if not hasattr(self, k) or overwrite:
                    setattr(self,k,v)
            
            if update:
                self.update()

    def _color_setter(self,attribute:str, value : ColorType, allows_None : bool = True, cls : type = None):
        """
        Tests if a given color is valid, and sets the attribute if so. Otherwise, logs an error

        Parameters
        ----------
        value : ColorType; 
            The color to check and set
        attribute : str
            The attribute to set.
        allows_None : bool
            Whether this color can be set to None, defaults to True
        cls : type
            Base class to use for the attribute. Used to define private attributes (those starting with __). If None, the element class itself is used.
        """
        if value == "None": #YAML parses null or nothing to None, however for colors, having a value that is representative of the color value is important I think.
            value = None

        if Style.is_valid_color(value):
            if value == None and (not allows_None):
                msg = f"{self}: {attribute} does not allow {value} as a color value"
            else:
                if attribute[:2] == "__":
                    if cls == None:
                        eCls = self.__class__.__name__
                    else:
                        eCls = cls.__name__
                    if str(eCls)[0] != "_":
                        attribute = f"_{eCls}{attribute}"
                    else:
                        attribute = f"{eCls}{attribute}"
                setattr(self,attribute, value)
                return
        elif isinstance(value,str):
            if self.parentLayout == None and not self in self.parentPSSMScreen.stack:
                ##Means it will be validated later
                setattr(self,attribute, value)
                return
            elif value in getattr(self.parentLayout,"_color_shorthands",{}):
                setattr(self,attribute, value)
                return
            else:
                msg = f"{self}: {value} is not identified as a valid color nor a valid shorthand for its parent ({self.parentLayout}) colors"
        else:
            msg = f"{self}: {value} is not identified as a valid color"

        _LOGGER.error(msg,exc_info=ValueError(msg))
    
    def _validate_color_properties(self):
        parent = self.parentLayout
        if parent == None:
            return
        
        short_cols = getattr(parent,"_color_shorthands",{})
        for col in self.color_properties:
            col_val = getattr(self,f"_{col}",None)
            if isinstance(col_val,str):
                ##Only test strings, any other value types are not shorthands and thus should have been tested already
                if col_val in short_cols:
                    continue
                elif not Style.is_valid_color(col_val):
                    msg = f"{self}: Color {col_val} is not a valid color, nor is it recognised as a value to reference a parent's color."
                    _LOGGER.error(msg)

    def _update_parent_colors(self, *updated_colors):
        parent = self.parentLayout
        if parent == None:
            return
        
        if not updated_colors == None:
            updated_colors = self.parentLayout.color_properties

        short_cols = getattr(parent,"_color_shorthands",{})
        update = False
        for col in self.color_properties:
            col_val = getattr(self,f"_{col}",None)
            if isinstance(col_val,str):
                if col_val in short_cols and short_cols[col_val] in updated_colors:
                    update = True
                    break        
        if update:
            self.update(updated=True)

    def _dimension_setter(self,attribute:str, value : PSSMdimension, variables : list[str] = [],cls : type = None):
        """
        Tests if a given value is a valid dimension (string, integer or float, or iterables of them.)

        Parameters
        ----------
        attribute : str
            the attribute to set
        value : PSSMdimension
            the value to test and set
        variables : list[str]
            list with variables that can aside from the standard one that can be used in this dimension
        """
        if isinstance(v := tools.is_valid_dimension(value,variables), Exception):
            prop  = attribute.lstrip("_")
            msg = f"{value} is not identified as a valid dimension for {prop} of {self.id}"
            _LOGGER.exception(msg,exc_info=v)
        else:
            if attribute[:2] == "__":
                if cls == None:
                    eCls = self.__class__.__name__
                else:
                    eCls = cls.__name__
                attribute = f"_{eCls}{attribute}"

            setattr(self,attribute, value)
            return

    def _function_setter(self, attribute : str, value : Union[Callable,str,interact_actionDict,None]):
        """
        Helper function to set a function action. If any errors are found, i.e. invalid type or not found functions, the attribute will be set to None.
        Also incorporates the element_checks if the screen has not started printing yet.

        Parameters
        ----------
        attribute : str
            The attribute that is being set. Keep in mind this should be the name of the property, it is automatically converted to a private attribute (i.e. a '_' is prepended to the attribute being set) to prevent infinite recursion loops.
            It is also used to set the appropriate data and map attribute (i.e. setattr is called for {attribute}_data and {attribute}_map)
        value : Union[Callable,str,interact_actionDict,None]
            The value to set. Can be a direct function object, a str that points to a shorthand function (either screen global or the element itself), or a dict. (Or None to do nothing)
            If the former two or None, {attribute}_data and {attribute}_map will automatically be emptied, which also happens if this value leads to an error, in which case the function will be set to None as well.
            When passing a dict, it can be structured the following way:
                `'action`' (required, Callable): the function/action to set. Accepts callables or strings.
                '`element_id`' (optional, str): Can be used to reference shorthand functions of other elements, like `{'action': 'element:show-popup`, 'element_id': 'my_popup'}`, will set the function to the show_popup method of popup 'my_popup'. Use the 'element:' prefix to indicate this.
                `'data'` (optional, dict): keyword arguments to pass to the set function, when called (and if implemented in the function call). If not present in the dict, will set {attribute}_data to an empty dict.
                `'map'` (optional, dict): keyword arguments to map to element attribute values and pass to the set function, when called (and if implemented in the function call). If not present in the dict, will set {attribute}_map to an empty dict.
        """        

        ##Make attribute the name of the property, the _ will be appended automatically.
        ##For recalls when printing starts
        ##Errors cause the function to be set to None, otherwise data and map etc. may interfere with the stuff.

        if isinstance(value,(Callable,str)) or value == None:
            func = value
        
        elif not isinstance(value, (dict,MappingProxyType)):
            msg = f"{self} {attribute} is of incorrect type. Must be a callable, string, dict or None. Is {type(value)}"
            _LOGGER.exception(TypeError(msg))
            func = None
        else:
            value = value.copy()
            if "action" not in value:
                msg = f"{self}: setting a function with a dict requires the key 'action'. {value} is not valid."
                _LOGGER.exception(KeyError(msg))
                func = None
            elif not isinstance(value["action"], (Callable,str)):
                msg = f"{self}: action key must be a function or a string. {type(value)}: {value} is not valid."
                _LOGGER.exception(TypeError(msg))
                func = None
            else:
                func = value["action"]

                if isinstance(func,Callable):
                    pass
                elif "element_id" not in value:
                    pass
                else:
                    if value["element_id"] in (self.parentPSSMScreen.elementRegister | self.screen.popupRegister):
                        ##From here: grab the element and the correct function
                        if value["element_id"] in self.parentPSSMScreen.popupRegister:
                            elt = self.parentPSSMScreen.popupRegister[value["element_id"]]
                        else:
                            elt = self.parentPSSMScreen.elementRegister[value["element_id"]]
                        if "element:" in func:
                            func = func.replace("element:","")
                        else:
                            msg = f"{self}: using element id in a function dict without using element: in the action string may cause issues."
                            _LOGGER.warning(msg)

                        if func in elt.action_shorthands:
                            func_str = elt.action_shorthands[func]
                            func = getattr(elt,func_str)
                        else:
                            msg = f"{elt.__class__} elements do not have a shorthand function for {func}. Cannot set {attribute} for {self}"
                            _LOGGER.exception(AttributeError(msg))
                            func = None
                    elif not self.parentPSSMScreen.printing:
                        self.parentPSSMScreen._add_element_attribute_check(self,attribute, value.copy())
                        func = None
                    else:
                        msg = f"{self}: element_id {value['element_id']} could not be found in the element register. {attribute} could not be set to {value}"
                        _LOGGER.exception(KeyError(msg))
                        func = None

        if isinstance(func,str):
            if "element:" in func:
                func = func.replace("element:","")
                if func in self.action_shorthands:
                    func_attr = self.action_shorthands[func]
                    func = getattr(self,func_attr,None)
                else:
                    msg = f"{self}: {self.__class__} do not have a shorthand function {func}"
                    _LOGGER.exception(AttributeError(value))
                    func = None
            elif func in self.parentPSSMScreen.shorthandActions:
                func = self.parentPSSMScreen.shorthandActions[func]
            else:
                if not self.parentPSSMScreen.printing:
                    if isinstance(value,dict): value = value.copy() ##Make sure any passed values don't change while the rest of the preprint code is running
                    self.parentPSSMScreen._add_element_attribute_check(self,attribute, value)
                    func = None
                else:
                    _LOGGER.warning(f"No known function with the name {value}")
                    func = None
        
        if not isinstance(func,Callable) and func != None:
            msg = f"{self} {attribute} turned out to not be a function, setting to None"
            _LOGGER.exception(TypeError(msg))
            func = None
        
        data_attr = f"{attribute}_data"
        map_attr = f"{attribute}_map"
        kwarg_attr = f"{attribute}_kwargs"

        if not hasattr(self, kwarg_attr):
            ##Be mindful that this means the property should return a value
            ##So data_attr and map_attr need to be able to return something before calling _function_checker
            pass
        elif isinstance(value, dict):
            ##These should not be set if the string could not be mapped to a function
            ##So the instance check is done twice, so the str check doesn't need to be rewritten.
            ##If the function is None it doesn't really matter since they won't be passed anyways

            ##Setters for these should be applied by the element

            ##Letting these fail silently is ok, I think?
            if hasattr(self, data_attr):
                if "data" in value and isinstance(value["data"],dict):
                    setattr(self, data_attr, value["data"])
                else:
                    setattr(self, data_attr, {})
            if hasattr(self, map_attr):
                if "map" in value and isinstance(value["map"],dict):
                    setattr(self, map_attr, value["map"])
                else:
                    setattr(self, map_attr, {})
        else:
            if hasattr(self, data_attr): setattr(self, data_attr, {})
            if hasattr(self, map_attr): setattr(self, map_attr, {})

        func_attr = f"_{attribute}"
        setattr(self,func_attr, func)

    def _get_action(self, touch_type: Literal["tap", "hold","hold_release"]) -> Optional[tuple[InteractionFunctionType, dict]]:        
        
        if getattr(self, f"{touch_type}_action", None) != None:
            func = getattr(self, f"{touch_type}_action")
            kwargs = getattr(self, f"{touch_type}_action_kwargs",{})
            return (func, kwargs)


    @abstractmethod
    def generator(self, area : PSSMarea=None, skipNonLayoutGen : bool =False) -> Image.Image:
        """
        Generates the pillow image of the element, sets it as imgData and returns the Image object.
        Considering the need to open files e.g. while generating, when running inkBoard it is advised to run `element.generate()` or `element.async_generator()`, as those have protections in place to (hopefully) prevent race conditions.

        args:
            area: screen area [(x,y),(w,h)] of this element. Optional, leave at None to have it set by the parentlayout
            skipNonLayoutGen (bool): only generate the layout (not applicable for non layout elements)
        """
        return

    @elementactionwrapper.method
    def generate(self, area : PSSMarea=None, skipNonLayoutGen : bool =False) -> Image.Image:
        """
        Generates the element's image data.

        Parameters
        ----------
        area : PSSMarea, optional
            optional area to use, by default None. Can be used to alter the area to generate in, but may also lead to unexpected results when using layout strings for example.
        skipNonLayoutGen : bool, optional
            Only used for layout type elements. When this is true, only elements that are layouts are regenerated. For other elements, the available imgData is used. Should improve performance when elements don't need to be regenerated, by default False

        Returns
        -------
        Image.Image
            The element's new image
        """
        saved_args = {"area": area, "skipNonLayoutGen": skipNonLayoutGen}
        
        if self.area == area == None:
            return

        loop = self.parentPSSMScreen.mainLoop

        try:
            if not loop.is_running():
                img = self.generator(**saved_args)
            else:
                #Can't promise this works, generally you'd want to call the async version
                img = tools._block_run_coroutine(self.async_generate(**saved_args), loop)
        except Exception as e:
            _LOGGER.warning(f"{e} went wrong generating {self}")
            return

        return img
    
    @elementactionwrapper.method
    async def async_generate(self, area : PSSMarea=None, skipNonLayoutGen : bool =False) -> Image.Image:
        """
        Generates the element's image data.

        Parameters
        ----------
        area : PSSMarea, optional
            optional area to use, by default None. Can be used to alter the area to generate in, but may also lead to unexpected results when using layout strings for example.
        skipNonLayoutGen : bool, optional
            Only used for layout type elements. When this is true, only elements that are layouts are regenerated. For other elements, the available imgData is used. Should improve performance when elements don't need to be regenerated, by default False

        Returns
        -------
        Image.Image
            The element's new image
        """
        saved_args = {"area": area, "skipNonLayoutGen": skipNonLayoutGen}

        if self._generatorLock.locked():
            _LOGGER.debug(f"{self} waiting for generator to unlock")

        try:
            async with self._generatorLock:
                if self.area == area == None:
                        return
                
                if asyncio._get_running_loop() == self.parentPSSMScreen.mainLoop:
                    _LOGGER.debug(f"{self}: switching async_generate to printLoop")
                

                    e = self.parentPSSMScreen.generatorPool
                    loop = self.parentPSSMScreen.mainLoop
                    coro = loop.run_in_executor(e,partial(self.generator,**saved_args))
                    img = await coro
                else:
                    img = self.generator(**saved_args)
            self._requestGenerate = False
            self._imgData = img
            return img
        except asyncio.CancelledError:
            return None

    async def _await_generator(self):
        "Helper coroutine that can be used to wait for an element's generator to finish."
        _LOGGER.verbose(f"Waiting for {self.id} to finish generating")
        async with self._generatorLock:
            await asyncio.sleep(0)
        
        return
    
    async def _await_update(self):
        "Helper coroutine that can be used to wait for an element's update to finish."
        _LOGGER.verbose(f"Waiting for {self.id} to finish updating")
        async with self._updateLock:
            await asyncio.sleep(0)
        return

    async def feedback_function(self) -> Callable[..., None]:
        "Function that makes visual feedback being shown when an element is interacted with. Defaults to invert_element as defined in pssm.PSSMscreen"
        self._feedbackTask = asyncio.create_task(self.parentPSSMScreen.async_invert_element(self,self.feedback_duration))
        await self.feedbackTask

colorproperty._base_element_class = Element

#region Layout elements
# ########################## - Layout Elements - ##############################
class Layout(Element):
    """
    A layout is collects elements, and creates an image out of them. Elements in a layout can also be layouts.
    If must be given the working area, and a layout, and will generate every element of the layout.

    Parameters
    ----------
    layout : PSSMlayout
        The layout to print, see docs for how to define one
    area : _type_, optional
        area of the element, by default None (set by parents)
    background_color : ColorType, optional
        layouts background color, by default None
    isInverted : bool, optional
        if the Layout is inverted, by default False
    radius : PSSMdimension, optional
        The radii of the corners, by default 0
    outline_color : ColorType, optional
        The color of the Layout's outline, by default None
    foreground_color : ColorType, optional
        The color to use as the foreground color (which is not used, but can be references by child elements), by default DEFAULT_FOREGROUND_COLOR
    accent_color : ColorType, optional
        The color to use as the accent color (which is not used, but can be references by child elements), by default DEFAULT_ACCENT_COLOR
    outline_width : PSSMdimension, optional
        The width of the Layout's outline, by default 0
    show_feedback : bool, optional
        Whether to show feedback when interacting with them (which does not check if a subelement is checked), by default False
    _isSubLayout : bool, optional
        Indicates this layout is a subLayout, i.e. one that is not used by child element's to get properties from, by default False
    """
    
    @classproperty
    def _color_shorthands(cls) -> dict[str,str]:
        "Class method to get shorthands for color setters, to allow for parsing their values in element properties. Returns a dict with the [key] being the shorthand to use for element properties and [value] being the tile attribute it links to."
        return {"background": "background_color", "outline": "outline_color", "foreground": "foreground_color", "accent": "accent_color"}

    @property
    def _emulator_icon(cls): return "mdi:view-dashboard"

    def __init__(self, layout : PSSMlayout, area=None, background_color : ColorType = None, isInverted=False, radius : PSSMdimension = 0, 
                outline_color : ColorType=None, foreground_color : ColorType = DEFAULT_FOREGROUND_COLOR, accent_color : ColorType = DEFAULT_ACCENT_COLOR,
                outline_width:PSSMdimension=0,
                show_feedback : bool = False, _isSubLayout : bool = False, 
                 **kwargs):


        self.__area = None
        if _isSubLayout:
            kwargs["_register"] = False
        self.__isSubLayout = _isSubLayout

        super().__init__(show_feedback=show_feedback, isInverted=isInverted, **kwargs)

        self._call_on_add : set[Element] = set()
        "Set of elements to call the on_add function of. Emptied after calling the element's own on_add"

        self._layout = []
        if layout != None:
            self.layout = layout

        self.background_color = background_color
        self.radius = radius
        self.outline_color = outline_color
        self.outline_width = outline_width

        self.foreground_color = foreground_color
        self.accent_color = accent_color

        self._area = area

        self._rebuild_area_matrix = True
        self._areaMatrix = None
        self._imgMatrix = None

        self.screen._add_element_attribute_check(self,"element_ids",self.__parent_setter_callback)

    #region
    # ----------------------------- Layout properties ---------------------------- #
    @property
    def isLayout(self) -> bool:
        "Returns whether the element is a layout"
        return True

    @property
    def layout(self) -> list[PSSMdimension,tuple[Element,PSSMdimension]]:
        "The layout list"
        return self._layout
    
    @layout.setter
    def layout(self, value:list):
        if value == getattr(self,"_layout",[]):
            return
        
        old_layout = self._layout
        try:
            self.is_layout_valid(value)
        except FuncExceptions as exce:
            _LOGGER.error(f"{self}: Layout invalid: {exce}")
            return

        self._layout = value
        self._rebuild_area_matrix = True

        if self.screen.printing:
            self.set_parent_layouts(old_layout, self.layout)

    @property
    def _area(self):
        """
        Private area property. Has a setter to allow for rebuilding the area matrix when it changes. Generally don't touch this.
        """
        return self.__area

    @_area.setter
    def _area(self, value):
        if value == self.__area:
            return
        
        self.__area = value
        self._rebuild_area_matrix = True

    @property
    def areaMatrix(self):
        return self._areaMatrix
    
    @property
    def imgMatrix(self):
        return self._imgMatrix

    @colorproperty
    def foreground_color(self) ->  Union[ColorType,None]:
        "Additional color property for Layouts. Not inherently used in the layout itself, but can be used in child elements, to give them a uniform style"
        return self._foreground_color


    @colorproperty
    def accent_color(self) ->  Union[ColorType,None]:
        "Additional color property for Layouts. Not inherently used in the layout itself, but can be used in child elements, to give them a uniform style"
        return self._accent_color


    @colorproperty
    def background_color(self) ->  Union[ColorType,None]:
        return self._background_color

    @colorproperty
    def outline_color(self) ->  Union[ColorType,None]:
        "Color of the elements outline. Set to None to use no outline (i.e. the background color)"
        return self._outline_color

    @property
    def outline_width(self) -> PSSMdimension:
        "Width of the outline of the encompassing rectangle"
        return self._outline_width
    
    @outline_width.setter
    def outline_width(self, value:PSSMdimension):
        self._outline_width : PSSMdimension
        self._dimension_setter('_outline_width',value)
        self._rebuild_area_matrix = True

    @property
    def radius(self) -> PSSMdimension:
        "Corner radius of the outlining rectangle"
        return self._radius
    
    @radius.setter
    def radius(self, value:PSSMdimension):
        self._radius : PSSMdimension
        self._dimension_setter('_radius', value)

    @property
    def _isSubLayout(self) -> bool:
        """
        Helper property to indicate this layout is considered a sublayout.
        If True, this means this layout will not be considered a parentLayout of elements, which is useful when parsing colors in TileLayouts for example.
        """
        try:
            return self.__isSubLayout
        except AttributeError:
            return False
    #endregion
    
    def is_layout_valid(self, validateLayout:list=[]):
        """
        Test wether the elements layout is valid, otherwise raises an exception
        args:
            validateLayout (list): If provided, this layout list will be checked. Otherwise will use self.layout
        
        Raises
        -------
        ValueError, TypeError
        """
        if validateLayout:
            layout = validateLayout
        else:
            layout = self.layout 

        if not isinstance(layout, list):
            raise TypeError("Layout Element is supposed to be a list")
        for row in layout:
            if not isinstance(row, list):
                raise TypeError("A layout row is supposed to be a list")
            elif len(row) == 0:
                raise Exception("A layout row cannot be empty")
            elif not isinstance(row[0], (str,int)):
                raise TypeError(
                    "The first element of a row (its height) should be a " +
                    "string or an integer"
                )
            for j in range(1, len(row)):
                eltTuple = row[j]
                isTuple = isinstance(eltTuple, tuple)
                isList = isinstance(eltTuple, list)
                if not (isTuple or isList):
                    raise TypeError(
                        "A layout row should be a list of Tuple " +
                        "(except for its first element)"
                    )
                if len(eltTuple) != 2:
                    raise ValueError(
                        "A layout element should be a Tuple : " +
                        "(Element, elementWidth)"
                    )
                isStr = isinstance(eltTuple[1], str)
                isInt = isinstance(eltTuple[1], int)
                if not (isInt or isStr):
                    raise TypeError(
                        "An element width should be a string or an integer"
                    )
                isElement = isinstance(eltTuple[0], Element)
                if not (isElement or eltTuple[0] is None):
                    if isinstance(eltTuple[0],str):
                        elt_id = eltTuple[0]
                        if elt_id in self.screen.elementRegister:
                            elt = self.screen.elementRegister[elt_id]
                            row[j] = (elt, eltTuple[1])
                            continue
                        elif not self.screen.printing:
                            continue

                    raise TypeError(
                        "A layout element should be a Tuple : " +
                        "(Element, elementWidth), with Element designating " +
                        " a PSSM Element"
                    )
        return True

    def __parent_setter_callback(self, *args):
        #Callback for setting parent layouts (when strings are present in a layout)
        self.is_layout_valid(self.layout)
        self.set_parent_layouts([],self.layout)

    def set_parent_layouts(self, old_layout : PSSMlayout, new_layout : PSSMlayout):
        """
        Sets the parentLayout attributes for the elements in old_layout and new_layout appropriately
        I.e., any element that is in old_layout but not in new_layout will have its parentLayout set to None (since it was removed)
        Any element that is in new_layout but not in old_layout will have its parentLayout set to this layout Element. 

        Parameters
        ----------
        old_layout : _type_
            The old layout of this element
        new_layout : _type_
            The new layout of this element
        """        

        old_elts = set(self.create_element_list(old_layout))
        new_elts = set(self.create_element_list(new_layout))

        if old_elts ^ new_elts: ##This checks if the sets have values that are unique to either set (i.e. value is in old_elt or new_elt, but not in both)
            self._call_on_add = set()
            for elt in new_elts - old_elts: ##This returns every element that is in new_elts and not in old_elts (i.e. all elements that are new)
                if (
                        callable(getattr(elt,"on_add",None)) and not elt.onScreen):

                    self._call_on_add.add(elt)
                if elt.parentLayout != self: 
                    elt._parentLayout = self
                    elt._validate_color_properties()

            for elt in old_elts - new_elts: ##This returns every element that is in old_elts but not in new_elts
                if "Clock" in elt.id:
                    _LOGGER.error(f"{self}: Calling on remove via set_parent_layouts")
                if elt.parentLayout == self: 
                    elt._parentLayout = None
                    if callable(getattr(elt,"on_remove",None)):
                        elt.on_remove()

    def on_add(self, call_all = False):
        "Function that is called when the layout is added to a screen object"
        _LOGGER.verbose(f"called layout on add will loop through {len(self.create_element_list())} elements; has {self.parentPSSMScreen} as screen")

        if call_all:
            for elt in self.create_element_list():
                if callable(getattr(elt,"on_add",None)):
                    self._call_on_add.add(elt)
            
        if self._rebuild_area_matrix:
            self.create_area_matrix()

        for elt in self._call_on_add:
            if elt.isLayout:
                elt.on_add(call_all=True)
            else:
                elt.on_add()

        self._call_on_add = set()

    def remove_element(self):
        "Called when a layout is removed. Handles calling the on_remove for the correct elements, and itself."
        for elt in self.create_element_list():
            if not elt.onScreen and callable(f := getattr(elt,"on_remove",None)):
                f()
        if callable(f := getattr(self,"on_remove",None)):
            f()

    def _style_update(self, attribute: str, value):
        "Called when a style property is updated"
        if attribute in self.color_properties:
            self._update_child_colors(attribute)

    def _update_child_colors(self, *updated_colors : str):
        
        update_list = list(updated_colors)
        for color in updated_colors:
            if color not in self.color_properties:
                _LOGGER.warning(f"{self}: {color} is not recognised as a color property")
                update_list.remove(color)
        for elt in self.create_element_list():
            elt._update_parent_colors(*update_list)

    def generator(self, area=None, skipNonLayoutGen=False):
        """
        Builds one img out of all the Elements it is being given
        """

        colorMode = self.parentPSSMScreen.imgMode
        color = Style.get_color(self.background_color, colorMode)
        
        if area is not None:
            self._area = area
        elif self.area == None:
            _LOGGER.warning(f"{self}: Cannot generate before an area is assigned")
            return

        if self.area == None or self._rebuild_area_matrix:
            self.create_area_matrix()
            if self._call_on_add:
                self.on_add()
            self.createImgMatrix(skipNonLayoutGen=False, background_color = self.background_color)

        elif not self.isGenerating: ##This means the async_generate function is running, i.e. it has created the image matrix already. Also in case of the _rebuild_area_matrix
            self.createImgMatrix(skipNonLayoutGen=skipNonLayoutGen, background_color = self.background_color)

        [(x, y), (w, h)] = self.area
        

        placeholder = Image.new(colorMode, (w, h), color=color)
        for i in range(len(self.areaMatrix)):
            for j in range(len(self.areaMatrix[i])):
                [(elt_x, elt_y), (elt_w, elt_h)] = self.areaMatrix[i][j]
                relative_x = elt_x - x
                relative_y = elt_y - y
                elt_img : Image.Image = self.imgMatrix[i][j]
                if elt_img is not None:
                    pos = (relative_x, relative_y)
                    if elt_img.mode == "RGBA" and colorMode == "RGBA":
                        placeholder.alpha_composite(elt_img, pos)
                    elif "A" in elt_img.mode and "A" not in colorMode:
                        placeholder.paste(self.imgMatrix[i][j], pos)
                    elif self.background_color != None and "A" in elt_img.mode:
                        placeholder.paste(elt_img, pos, mask=elt_img)
                    else:
                        placeholder.paste(elt_img, pos)

        if self.radius != 0:
            ##There should also be a way to draw this when outline width is not 0
            r = self._convert_dimension(self.radius)

            mask = Image.new("RGBA",placeholder.size,None)
            (mask,_) = DrawShapes.draw_rounded_rectangle(mask,
                    {"xy":  [(0, 0), (w,h)],
                    "fill": "white",
                    "radius": r},
                rescale=["xy","radius","width"])
            
            if "A" not in placeholder.mode:
                a = mask.getchannel("A")
                placeholder.putalpha(a)
            else:
                newImg = Image.new("RGBA",placeholder.size,None)
                newImg.paste(placeholder, mask=mask)
                placeholder = newImg

            outlineCol = Style.get_color(self.outline_color, colorMode)
            outW = self._convert_dimension(self.outline_width)

            ##Draw the outline on top, to ensure nothing is sticking out over it
            ##Style choice
            (outline,_) = DrawShapes.draw_rounded_rectangle(placeholder,
                    {"xy":  [(0, 0), (w,h)],
                    "fill": None,
                    "radius": r,
                    "width": outW,
                    "outline": outlineCol}, 
                rescale=["xy","radius","width"], paste=False)

            placeholder.alpha_composite(outline)

        if self.isInverted: 
            for elt in self.create_element_list():
                if self.isInverted and elt.inverted:
                    elt._isInverted = False
                elif self.isInverted and not elt.inverted:
                    elt._isInverted = True
                elif not self.isInverted and elt.isInverted:
                    pass
                elif not self.isInverted and not elt.isInverted:
                    pass
            
            ##Not using screen inversion since it makes for a mess during image generation I don't want to figure out.
            placeholder = tools.invert_Image(placeholder)
            

        self._imgData = placeholder
        return self.imgData

    def createImgMatrix(self, skipNonLayoutGen=False, background_color=DEFAULT_BACKGROUND_COLOR):
        matrix = []
        if not self.areaMatrix:
            _LOGGER.warning("Layout Error, areaMatrix has to be defined first")
            return None
        for i, _ in enumerate(self.areaMatrix):
            row = []
            for j, elt_area in enumerate(self.areaMatrix[i]):
                elt, _ = self.layout[i][j+1]
                elt : Element
                if elt is None:
                    elt_img = None
                else:
                    try:
                        if not elt.isLayout and skipNonLayoutGen:
                            if elt.imgData == None:
                                if elt.isGenerating:
                                    _LOGGER.debug(f"{self.id} Generator is waiting for {elt.id} to finish generating")
                                    tools._block_run_coroutine(elt._await_generator(),self.parentPSSMScreen.mainLoop)
                                    _LOGGER.verbose(f"{elt.id} finished generating: {elt.isGenerating}")
                                elt_img = elt.generator(elt_area)
                            else:
                                elt_img = elt.imgData
                        else:
                            if elt.isGenerating:
                                ##This line here causes a lot of generating to happen concurrently
                                ##From what I found, this could be fixed using dummy event loop that simply run until the generating is finished.
                                ##See the tool for  the solution
                                _LOGGER.debug(f"{self.id} Generator is waiting for {elt.id} to finish generating")
                                tools._block_run_coroutine(elt._await_generator(),self.parentPSSMScreen.mainLoop)
                                _LOGGER.verbose(f"{elt.id} finished generating: {elt.isGenerating}")

                            ##Don't need a new thread for generating since it should not ever be called in the mainloop
                            elt_img = elt.generator(area=elt_area, skipNonLayoutGen=skipNonLayoutGen)
                    except Exception:
                        _LOGGER.error(f"{self}: {elt} could not generate", exc_info=True)
                        elt_img = None

                row.append(elt_img)
            matrix.append(row)
        
        ##Somehow need a check here that ensures the imgMatrix and layout matrix match
        self._imgMatrix = matrix

    async def async_generate(self, area = None, skipNonLayoutGen: bool = False) -> Coroutine[Any, Any, Image.Image]:

        async with self._generatorLock:
            ##Deal with what?
            ##Check if the current loop is the mainloop -> done -> but test if needed. Cause no new threads are needed to be made when generating a layout

            if area is not None:
                self._area = area
            elif self.area == None:
                _LOGGER.warning(f"{self}: Cannot generate before an area is assigned")
                return

            if asyncio._get_running_loop() == self.mainLoop:
                _LOGGER.debug(f"{self}: switching async_generate to printLoop")
            
            if self.area == None or self._rebuild_area_matrix:
                self.create_area_matrix()
                if self._call_on_add:
                    self.on_add()
                await self.async_create_img_matrix(skipNonLayoutGen=False)
            else:
                await self.async_create_img_matrix(skipNonLayoutGen=skipNonLayoutGen)

                [(x, y), (w, h)] = self.area
            
            try:
                img = self.generator()
            except FuncExceptions:
                _LOGGER.exception(f"{self}: could not make image")
                img = None
        return img

    async def async_create_img_matrix(self, skipNonLayoutGen=False):
        matrix = []
        if not self.areaMatrix:
            _LOGGER.warning("Layout Error, areaMatrix has to be defined first")
            return None
        for i, _ in enumerate(self.areaMatrix):
            row = []
            for j, elt_area in enumerate(self.areaMatrix[i]):
                elt, _ = self.layout[i][j+1]
                elt : Element
                if elt is None:
                    elt_img = None
                else:                    
                    if not elt.isLayout and skipNonLayoutGen:
                        if elt.imgData == None or elt._requestGenerate:
                            if elt.isGenerating:
                                _LOGGER.debug(f"{self.id} Generator is waiting for {elt.id} to finish generating")
                                await elt._await_generator()
                                _LOGGER.verbose(f"{elt.id} finished generating: {elt.isGenerating}")
                                elt_img = elt.imgData
                            else:
                                elt_img = await elt.async_generate(elt_area)
                        else:
                            if elt.isGenerating:
                                _LOGGER.debug(f"{self.id} Generator is waiting for {elt.id} to finish generating")
                                await elt._await_generator()
                                _LOGGER.verbose(f"{elt.id} finished generating: {elt.isGenerating}")
                                elt_img = elt.imgData
                            elt_img = elt.imgData
                    else:
                        elt_img = await elt.async_generate(elt_area, skipNonLayoutGen=skipNonLayoutGen)
                row.append(elt_img)
            matrix.append(row)
        self._imgMatrix = matrix

    def create_area_matrix(self):
        # TODO : must honor min and max
        # FIXME: division by zero happens sometimes -> but simply ignoring it does not seem to cause issues
        matrix = []
        n_rows = len(self.layout)

        if self.area == None:
            _LOGGER.warning(f"{self}: Cannot create area matrix before an area has been assigned")
            return

        [(x, y), (w, h)] = self.area[:]
        if self.outline_width != 0 and self.outline_color != None:
            outW = self._convert_dimension(self.outline_width)
            outW = floor(outW*0.75)
            x = x + outW
            y = y + outW
            w = w - 2*outW
            h = h - 2*outW
        self.layoutArea = [(x,y),(w,h)]
        
        x0, y0 = x, y
        
        ##These should hopefully prevent rounding errors from questionmark dimensions to accumulate
        ##Which would make the total sum of element width/height fall a bit short of the respective layoutArea value.
        height_rounders = cycle([ceil,floor])  
        for i in range(n_rows):     # Lets loop through the rows
            row = self.layout[i]
            row_cols = []           # All the columns of this particular row
            row_height = row[0]
            converted_height = self._convert_dimension(row_height,{"w":w,"h":h})
            if isinstance(converted_height, int):
                true_row_height = converted_height
            else:
                remaining_height = self.calculate_remaining_height()
                dim = str(remaining_height) + converted_height[1:]
                true_row_height = next(height_rounders)(eval(dim))

            if true_row_height < 0:
                _LOGGER.error(f"{self}: row {i} height {row_height} converted to {true_row_height}, setting to 0")
                true_row_height = 0

            width_rounders = cycle([ceil,floor])
            for j in range(1, len(row)):
                element : Element
                (element, element_width) = row[j]
                r_var = true_row_height
                if r_var > w:
                    r_var = w
                converted_width = self._convert_dimension(element_width,{"w":w,"h":h,"r": r_var})
                if element is not None:
                    pass

                if isinstance(converted_width, int):
                    true_elt_width = converted_width
                else:
                    remaining_width = self.calculate_remaining_width(i,true_row_height)
                    dim = str(remaining_width) + converted_width[1:] 
                    true_elt_width = next(width_rounders)(eval(dim))

                    ##If overwriting the width to a pixel value here is required for something, it is in the extract_colwidth function, but idk why.
                    ##Seems to not affect it, otherwise probably just rewrite it to use the area matrix
                if true_elt_width < 0:
                    _LOGGER.error(f"{element}'s width {element_width} converted to {true_elt_width}, setting to 0")
                    true_elt_width = 0

                element_area = [(x0, y0), (true_elt_width, true_row_height)]
                x0 += true_elt_width

                row_cols.append(element_area)
                if element != None:
                    element._area = element_area

            y0 += true_row_height
            x0 = x
            matrix.append(row_cols)

        self._areaMatrix = matrix
        self._rebuild_area_matrix = False

    def create_element_list(self, layout : Optional[PSSMlayout] = None, full_list : bool = False) -> list["Element"]:
        """
        Returns a list of all the elements the Layout Element contains

        Parameters
        ----------

        layout : Optional[PSSMlayout]
            The layout to create the list from. If None, the element's layout will be used.
        full_list : bool
            Returns all elements in this layout and any `LayoutElement`'s contained within
        """
        eltList = []
        if layout == None:
            if not hasattr(self,"layout"):
                ##In case a layout has not been set yet, for color setters
                return []
            layout = self.layout
        
        for row in layout:
            for i in range(1, len(row)):
                elt, _ = row[i]
                if elt is not None:
                    elt : Element
                    eltList.append(elt)
                    if full_list and elt.isLayout:
                        eltList.extend(elt.create_element_list())
        return eltList

    def calculate_remaining_height(self):
        #Used to determine height of questionmarks
        rows = self.extract_rows_height()
        total_questionMarks_weight = 0
        total_height = 0
        [(_,_),(w,h)] = self.layoutArea
        for dimension in rows:
            converted_dimension = self._convert_dimension(dimension,{"w":w,"h":h})
            if isinstance(converted_dimension, int):
                total_height += converted_dimension
            else:
                weight = eval("1" + converted_dimension[1:])
                total_questionMarks_weight += weight
        layout_height = self.layoutArea[1][1]
        return (layout_height - total_height)/total_questionMarks_weight

    def calculate_remaining_width(self, rowIndex, row_height):
        #Used to determine width of questionmarks
        cols = self.extract_columns_width(rowIndex)
        total_width = 0
        total_questionMarks_weight = 0
        for dimension in cols:
            converted_dimension = self._convert_dimension(dimension, {"r": row_height})
            if isinstance(converted_dimension, int):
                total_width += converted_dimension
            else:
                weight = eval("1" + converted_dimension[1:])
                total_questionMarks_weight += weight
        layout_width = self.layoutArea[1][0]
        if total_questionMarks_weight == 0: 
            _LOGGER.warning("Division by 0, converted dim: {}".format(converted_dimension))
            return converted_dimension
        else:
            q_dim = (layout_width - total_width)/total_questionMarks_weight
            if q_dim < 0: 
                return 0
            else:
                return q_dim

    def extract_rows_height(self):
        rows = []
        for row in self.layout:
            rows.append(row[0])
        return rows

    def extract_columns_width(self, rowIndex):
        cols = []
        for col in self.layout[rowIndex]:
            if isinstance(col, tuple):
                cols.append(col[1])
        return cols

    async def _dispatch_click(self, interaction: InteractEvent) -> list[Callable]:
        """
        Finds the element on which the user clicked and returns a list of the found onTap functions
        """
        return await self._dispatch_click_LINEAR(interaction)

    async def _dispatch_click_LINEAR(self, interaction: InteractEvent):
        """
        Linear search through both the rows and the columns
        """
        click_x, click_y, action = interaction
        try:
            for i in range(len(self.areaMatrix)):
                if len(self.areaMatrix[i]) == 0:
                    continue
                first_row_elt = self.areaMatrix[i][0]
                last_row_elt = self.areaMatrix[i][-1]
                x = first_row_elt[0][0]
                y = first_row_elt[0][1]
                w = last_row_elt[0][0] + last_row_elt[1][0] - first_row_elt[0][0]
                h = last_row_elt[0][1] + last_row_elt[1][1] - first_row_elt[0][1]
                if tools.coords_in_area(click_x, click_y, [(x, y), (w, h)]):
                    # CLick was in that row
                    for j in range(len(self.areaMatrix[i])):
                        # Linear search through the columns
                        if tools.coords_in_area(click_x, click_y, self.areaMatrix[i][j]):
                            # Click was on that element
                            elt, _ = self.layout[i][j+1]
                            if elt is not None:
                                disp = await self.parentPSSMScreen._dispatch_click_to_element(
                                        interaction, elt
                                    )
                                if type(disp) != list:
                                    _LOGGER.warning(f"Layout returned {disp}")
                                    disp = []

                                return disp
        except FuncExceptions as exce:
            _LOGGER.warning(f"{self}: Cannot iterate fully to dispatch click: {exce}", exc_info=exce)
        return []

    def _dispatch_click_DICHOTOMY_colsOnly(self, coords):
        """
        Linear search through the rows, dichotomy for the columns
        (Because of the empty rows, a dichotomy for the rows doesn't work)
        NEEDS TO BE FIXED TOO (example : two buttons in a row)
        """
        click_x, click_y = coords
        row_A = -1
        for i in range(len(self.areaMatrix)):
            # Linear search though the rows
            if len(self.areaMatrix[i]) == 0:
                # That's a fake row (a margin row)
                continue
            first_row_elt = self.areaMatrix[i][0]
            last_row_elt = self.areaMatrix[i][-1]
            x = first_row_elt[0][0]
            y = first_row_elt[0][1]
            w = last_row_elt[0][0] + last_row_elt[1][0] - first_row_elt[0][0]
            h = last_row_elt[0][1] + last_row_elt[1][1] - first_row_elt[0][1]
            if tools.coords_in_area(click_x, click_y, [(x, y), (w, h)]):
                # CLick was in that row
                row_A = i
                break
        if row_A == -1:
            return None
        col_A = 0
        col_C = max(len(self.areaMatrix[row_A]) - 1, 0)
        xA = self.areaMatrix[row_A][col_A][0][0]
        xC = self.areaMatrix[row_A][col_C][0][0]
        if click_x < xA:
            return None
        if click_x > xC + self.areaMatrix[row_A][col_C][1][0]:
            return None
        while col_C > col_A + 1:
            col_B = int(0.5*(col_A+col_C))      # The average of the two
            xB = self.areaMatrix[row_A][col_B][0][0]
            if click_x >= xB or col_B == col_C:
                col_A = col_B
                xA = xB
            else:
                col_C = col_B
                xC = xB
        # Element is at indexes row_A, col_A
        elt, _ = self.layout[row_A][col_A+1]
        if elt is not None and elt.tap_action is not None:
            self.parentPSSMScreen._dispatch_click_to_element(coords, elt)
        return True

    def _dispatch_click_DICHOTOMY_Full_ToBeFixed(self, coords):
        """
        Finds the element on which the user clicked
        Implemented with dichotomy search (with the hope of making things
        faster, especially the integrated keyboard)
        """
        # TODO : To be fixed
        # For now it does not work, because there are empty rows which
        # break the loop
        click_x, click_y = coords
        row_A = 0
        row_C = max(len(self.areaMatrix) - 1, 0)
        _LOGGER.debug(self.areaMatrix[row_C])
        while len(self.areaMatrix[row_A]) == 0:
            row_A += 1
        while len(self.areaMatrix[row_C]) == 0:
            row_C -= 1
        # First column THEN first row , [(x, y), (w, h)] THUS first tuple of
        # list THEN second coordinate of tuple
        yA = self.areaMatrix[row_A][0][0][1]
        yC = self.areaMatrix[row_C][0][0][1]
        if click_y < yA:
            return None
        if click_y > yC + self.areaMatrix[row_C][0][1][1]:
            return None
        while row_C > row_A+1:
            row_B = int(0.5*(row_A+row_C))      # The average of the two
            while len(self.areaMatrix[row_B]) == 0:
                row_B += 1
            yB = self.areaMatrix[row_B][0][0][1]
            if click_y >= yB or row_B == row_C:
                row_A = row_B
                yA = yB
            else:
                row_C = row_B
                yC = yB
        # User clicked on element ar row of index row_A
        # Let's do the same for the column
        col_A = 0
        col_C = max(len(self.areaMatrix[row_A]) - 1, 0)
        xA = self.areaMatrix[row_A][col_A][0][0]
        xC = self.areaMatrix[row_A][col_C][0][0]
        if click_x < xA:
            return None
        if click_x > xC + self.areaMatrix[row_A][col_C][1][0]:
            return None
        while col_C > col_A + 1:
            col_B = int(0.5*(col_A+col_C))      # The average of the two
            xB = self.areaMatrix[row_A][col_B][0][0]
            if click_x >= xB or col_B == col_C:
                col_A = col_B
                xA = xB
            else:
                col_C = col_B
                xC = xB
        # Element is at indexes row_A, col_A
        elt, _ = self.layout[row_A-2][col_A+1]
        if elt is not None and elt.tap_action is not None:
            self.parentPSSMScreen._dispatch_click_to_element(coords, elt)
        return True


class _TileBase(Layout):
    """
    Base element for Tile based element functionality. Provides base functionality for using layout strings and using color shorthands (the latter has by now been extended to layouts in general).
    Cannot be used as is, needs to be called from a childclass. The elements need to have been set before calling the init of the _TileBase.

    Parameters
    ----------
    tile_layout : Union[str,PSSMlayout]
        layout string used to build this element. Can be a valid layout matrix too, but generally should not be needed to do so.
    vertical_sizes : dict, optional
        Vertical sizing of elements, by default {"inner": 0, "outer": 0} (That being the sizes of the margins)
    horizontal_sizes : dict, optional
        Horizontal sizing of elements, by default {"inner": 0, "outer": 0} (That being the sizes of the margins)
    foreground_color : Optional[ColorType], optional
        Foreground color of the Tile, by default DEFAULT_FOREGROUND_COLOR
        Can be used in element_properties by `'foreground``, which will parse the color to the element.
    accent_color : Optional[ColorType], optional
        Accent color of the Tile, by default DEFAULT_ACCENT_COLOR.
        Can be used in element_properties by `'accent``, which will parse the color to the element.
        By default not used
    background_color : Optional[ColorType], optional
        Background color of the Tile, by default None
        Can be used in element_properties by `'background``, which will parse the color to the element.
    outline_color : Optional[ColorType], optional
        Outline Color of the Tile, by default None
        Can be used in element_properties by `'outline``, which will parse the color to the element.
    """

    _default_layouts : dict = {}
    "Dict that can hold default layouts for elements."

    _restricted_element_properties : dict[str,set[str]] = {}
    "Properties of the elements that are not allowed to be set."

    @classproperty
    def _color_shorthands(cls) -> dict[str,str]:
        "Class method to get shorthands for color setters, to allow for parsing their values in element properties. Returns a dict with the [key] being the shorthand to use for element properties and [value] being the tile attribute it links to."
        return {"background": "background_color", "foreground": "foreground_color", "outline": "outline_color", "accent": "accent_color"}

    @property
    def _emulator_icon(cls): return "mdi:layers-triple"

    def __init__(self, tile_layout : Union[str,PSSMlayout], vertical_sizes = {"inner": 0, "outer": 0}, horizontal_sizes = {"inner": 0, "outer": 0},
                foreground_color : Optional[ColorType] = DEFAULT_FOREGROUND_COLOR, accent_color : Optional[ColorType] = DEFAULT_ACCENT_COLOR, background_color : Optional[ColorType] = None, 
                outline_color : Optional[ColorType] = None, element_properties = {},
                **kwargs):

        self._tile_layout = None
        self.__hide = ()

        self._color_setter("_foreground_color",foreground_color,True, cls=_TileBase)
        self._color_setter("_background_color",background_color,True, cls=_TileBase)
        self._color_setter("_outline_color",outline_color,True, cls=_TileBase)
        self._color_setter("_accent_color",accent_color,True, cls=_TileBase)

        self._vertical_sizes = {"inner": 0, "outer": 0}
        self._horizontal_sizes = {"inner": 0, "outer": 0}

        self.vertical_sizes = vertical_sizes
        self.horizontal_sizes = horizontal_sizes

        ##This should automatically add all elements
        self._element_properties = {}
        
        if isinstance (tile_layout, str):
            layout = parse_layout_string(tile_layout, None, self.hide, self.vertical_sizes, self.horizontal_sizes, **self.elements)
        else:
            layout = tile_layout
        super().__init__(layout, background_color=background_color, outline_color=outline_color, foreground_color=foreground_color, accent_color=accent_color,  **kwargs)

        if isinstance (tile_layout, str):
            self._tile_layout = tile_layout
            if tile_layout in self.__class__._default_layouts:
                self._reparse_layout = True

        for elt_str in  element_properties:
            elt = self.elements[elt_str]
            elt.add_attributes(element_properties[elt_str])

        self.element_properties = element_properties
        self._reparse_element_colors()
        
    #region
    @property
    def tile_layout(self) -> Optional[str]:
        "String used to set the layout. None if the layout was set directly"
        if self._tile_layout in self.__class__._default_layouts:
            l = self.__class__._default_layouts[self._tile_layout]
            return l
        
        return self._tile_layout
    
    @tile_layout.setter
    def tile_layout(self, value : str):
        if not isinstance(value, str):
            msg = f"{self}: tile_layout must be a string. {value} is not valid."
            _LOGGER.exception(TypeError(msg))
            return
        
        if value != self._tile_layout:
            self._reparse_layout = True
            self._tile_layout = value

    @Layout.layout.setter
    def layout(self, value:Union[list,str]):
        if isinstance(value, str):
            self.__class__.tile_layout.fset(self, value)
            return

        try:
            self.is_layout_valid(value)
        except FuncExceptions as exce:
            _LOGGER.error(f"Layout invalid: {exce}")
            value = [["?",(None,"?")]]
        
        old_layout = self._layout

        self._tile_layout = None
        self._reparse_layout = False
        self._layout = value
        self._rebuild_area_matrix = True

        self.set_parent_layouts(old_layout,self._layout)


    @property
    @abstractmethod
    def elements(self) -> MappingProxyType[str,Element]:
        "Elements in the layout. This property needs to be redefined for subclasses."
        return self.__elements

    @property
    def hide(self) -> tuple[str]:
        "Elements that will be explicitly removed from the layout parsed from `tile_layout`. Set to None, or an empty iterable to hide nothing."
        return self.__hide

    @hide.setter
    def hide(self, value : list):
        if value == None:
            value = []
        elif isinstance(value,str):
            value = [value]
        else:
            value = list(value)
        value_set = set(value)
        for elt in filter(lambda elt: elt not in self.elements, value_set):
            _LOGGER.warning(f"{self} does not have an element {elt}. Will be removed from the hide list")
            value.remove(elt)
        
        if value_set == set(self.__hide):
            return

        self.__hide = tuple(value_set)
        self._reparse_layout = True

    @property
    def vertical_sizes(self) -> dict[str,PSSMdimension]:
        "Vertical sizing of the elements in layout strings. Setting this will update from the current values, not overwrite it."
        return self._vertical_sizes
    
    @vertical_sizes.setter
    def vertical_sizes(self, value : dict):

        allowed_keys = {"inner", "outer"} | set(self.elements.keys())
        val_keys = set(value.keys()) | allowed_keys
        if val_keys != allowed_keys:
            msg = f"{self.id} vertical sizes only allows {allowed_keys}. {value.keys()} has at least 1 not allowed. Don't forget to add new elements before setting vertical and horizontal sizes."
            _LOGGER.exception(KeyError(msg))
            return

        self._vertical_sizes.update(value)
        self._reparse_layout = True

    @property
    def horizontal_sizes(self) -> dict[str,PSSMdimension]:
        "Vertical sizing of the elements in layout strings. Setting this will update from the current values, not overwrite it."
        return self._horizontal_sizes
    
    @horizontal_sizes.setter
    def horizontal_sizes(self, value : dict[str,PSSMdimension]):

        allowed_keys = {"inner", "outer"} | set(self.elements.keys())
        val_keys = set(value.keys()) | allowed_keys
        if val_keys != allowed_keys:
            msg = f"{self.id} horizontal sizes only allows {allowed_keys}. {value.keys()} has at least 1 not allowed. Don't forget to add new elements before setting vertical and horizontal sizes."
            _LOGGER.exception(KeyError(msg))
            return

        self._horizontal_sizes.update(value)
        self._reparse_layout = True

    @property
    def element_properties(self) -> dict[str,dict]:
        """
        Dict with properties for each element. Accepts parsing colors.
        Use as nested dicts, the first key specifying the element tag, with the dict within  denoting the properties to set.
        """
        return self._element_properties
    
    @element_properties.setter
    def element_properties(self, value : dict[str, dict]):
        if not isinstance(value, dict):
            _LOGGER.exception(TypeError("Element properties must be a dict"))
            return
        
        for elt, props_or in value.items():
            props = props_or.copy()
            if elt not in self.elements:
                _LOGGER.warning(f"{self} does not have an element {elt}")
            else:
                if elt in self._restricted_element_properties:
                    restrictions = self._restricted_element_properties[elt]
                    prop_keys = set(props.keys())
                    for restr in filter(lambda restr: restr in restrictions, prop_keys):
                        msg = f"{self} does not allow setting {restr} for {elt}. Will not be changed."
                        _LOGGER.warning(msg)
                        props.pop(restr)

                if elt in self._element_properties:
                    self._element_properties[elt].update(props)
                else:
                    self._element_properties[elt] = props
                if not self.parentPSSMScreen.printing:
                    self._reparse_element_colors()
        
        if self.parentPSSMScreen.printing:
            self._reparse_colors = True
    
    @colorproperty
    def foreground_color(self) -> Union[ColorType]:
        "The main color to use for the icon and text. Can be overwritten by iconSettings and buttonSettings respectively."
        return self._foreground_color

    @colorproperty
    def accent_color(self) -> Union[ColorType]:
        "The main color to use for the icon and text. Can be overwritten by iconSettings and buttonSettings respectively."
        return self._accent_color

    @colorproperty
    def outline_color(self) ->  Union[ColorType,None]:
        return self._outline_color
    #endregion

    def _style_update(self, attribute, value):
        self._reparse_colors = True
        super()._style_update(attribute, value)

    def _reparse_element_colors(self, elt_name : str = None):
        """
        Calls the setters for all property setters, use when setting e.g. foreground_color or background_color
        May be deprecated since it has been implemented in the colorproperty decorator. element_properties will not be removed though. 
        
        Parameters
        ----------
        elt_name : str, optional
            Optional name for the element to update, by default None, which will reparse the colors for all element properties.
        """
        ##Can't really remove this yet as it seems to cause issues with ~stuff~ (i.e. person element does not show the person picture anymore) 

        ##Idk if this works fill figure it out later when actually using this.
        if elt_name == None:
            prop_loop = self.element_properties.items()
        else:
            if elt_name not in self._element_properties:
                return
            elif elt_name not in self.elements:
                _LOGGER.warning(f"{self} does not have an element {elt} in its defined elements")
                return
            else:
                prop_loop = [(elt_name, self._element_properties[elt_name])]
        
        color_setters = self.__class__._color_shorthands
        for elt_str, props in prop_loop:
            set_props = props.copy()
            elt = self.elements[elt_str]
            color_props = elt.color_properties
            for prop in color_props.intersection(set_props): ##This part grabs only the properties that are in the element_property dict that correspond to color attributes of the element's class
                if isinstance(set_props[prop],(tuple,list)) and prop in color_props:
                    prop_list = list(set_props[prop])
                    for i, prop_value in enumerate(prop_list):
                        if prop_value in color_setters:
                            color_attr = color_setters[prop_value]
                            prop_list[i] = getattr(self,color_attr)
                    set_props[prop] = prop_list     ##This should still work fine with rgb color lists I believe? Since integers will never show up in color_setter
                elif set_props[prop] in color_setters: ##Check if the value of the element's color attribute to be set corresponds to a known shorthand color of _this_ (i.e. the parentlayout) element
                    color_attr = color_setters[set_props[prop]] ##Grab the parent layout's corresponding attribute
                    set_props[prop] = getattr(self,color_attr) ##Grab the value of said attribute, and set that as the actual color value
            elt.update(set_props, skipPrint=self.isUpdating)

        if not elt_name:
            self._reparse_colors = False

    def generator(self, area=None, skipNonLayoutGen=False):
        
        if self.tile_layout != None and self._reparse_layout:
            old_layout = self.layout.copy()
            new_layout = parse_layout_string(self.tile_layout, None, self.hide, self.vertical_sizes, self.horizontal_sizes, **self.elements)
            if new_layout != old_layout: ##This doesn't quite work since sublayouts are a thing
                self.set_parent_layouts(old_layout,new_layout)
                self._layout = new_layout
                skipNonLayoutGen=False
                self._rebuild_area_matrix = True

            self._reparse_layout = False

        if self._reparse_colors:
            skipNonLayoutGen = False
            self._reparse_element_colors()

        ##Check what to do with regenerating layouts, mainly for when colors change.
        ##May be doable by overwriting async update and checking if a color property is in it.
        return super().generator(area, skipNonLayoutGen)

    async def async_generate(self, area=None, skipNonLayoutGen=False):
        
        async with self._generatorLock:
            if self.tile_layout != None and self._reparse_layout:
                old_layout = self.layout.copy()
                new_layout = parse_layout_string(self.tile_layout, None, self.hide, self.vertical_sizes, self.horizontal_sizes, **self.elements)
                if new_layout != old_layout: ##This doesn't quite work since sublayouts are a thing
                    self.set_parent_layouts(old_layout,new_layout)
                    self._layout = new_layout
                    skipNonLayoutGen=False
                    self._rebuild_area_matrix = True

                self._reparse_layout = False

            if self._reparse_colors:
                skipNonLayoutGen = False
                self._reparse_element_colors()

        img = await super().async_generate(area, skipNonLayoutGen)
        return img
        ##Check what to do with regenerating layouts, mainly for when colors change.
        ##May be doable by overwriting async update and checking if a color property is in it.


class TileLayout(_TileBase):
    """
    A general TileLayout, with self defined elements and layout.

    Parameters
    ----------
    tile_layout : Union[str,PSSMlayout]
        The layout of the tile
    elements : dict[str,Element]
        The elements that can be used within the tile_layout
    vertical_sizes : dict, optional
        Vertical sizes of the elements, by default { "inner": 0,"outer": 0 }
    horizontal_sizes : dict, optional
        Horizontal sizes of the elements, by default { "inner": 0,"outer": 0 }
    """

    def __init__(self, tile_layout: Union[str,PSSMlayout], elements : dict[str,Element], vertical_sizes={ "inner": 0,"outer": 0 }, horizontal_sizes={ "inner": 0,"outer": 0 }, **kwargs):

        self.__elements = elements
        
        super().__init__(tile_layout, vertical_sizes, horizontal_sizes, **kwargs)

    @property
    def elements(self) -> MappingProxyType[str,Element]:
        return self.__elements

    def add_element(self, name : str, element : Element):
        """
        Adds an element to the tile

        Parameters
        ----------
        name : str
            The name to reference the element in e.g. the tile_layout
        element : Element
            The element to add.
        """        
        elts = dict(self.__elements)
        if name in elts:
            _LOGGER.warning(f"{self} already has an element {name}: {elts[name]}. It will be overwritten.")
        
        elts[name] = element
        
        self.__elements = MappingProxyType(elts)


class ButtonList(Layout):
    """
    NOT UP TO DATE
    Generates a Layout with only one item per row, all the same type (buttons)
    and same height and width
    Args:
        buttons (list): a [{"text":"my text","onclickInside":onclickInside},
            someOtherDict, someOtherDict] array. Each dict will contain the
            parameters of each button of the button list
        margins (list): a [top, bottom,left,right] array
        spacing (str or int): vertical space between button elements
    """
    
    def __init__(self, buttons:list, margins:list=[0, 0, 0, 0], spacing=0, **kwargs):
        
        self._buttons = buttons
        self.margins = margins
        self.spacing = spacing
        layout = self.build_layoutFromButtons()
        super().__init__(layout, **kwargs)

    #region
    @property
    def buttons(self) -> list:
        return self._buttons
    
    @buttons.setter
    def buttons(self, value:list):
        self._buttons = value

    @property
    def margins(self) -> list:
        "The margins of the buttons"
        return self._margins

    @margins.setter
    def margins(self, value:list):
        if len(value) != 4:
            _LOGGER.error(f"Margin list must have exactly 4 values. {value} is not valid")
        else:
            self._margins = value
    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        self._layout = self.build_layoutFromButtons()
        return super().generator(area, skipNonLayoutGen)

    def build_layoutFromButtons(self):
        # TODO : must honor min_width,max_width etc
        [top, bottom, left, right] = self.margins
        buttonLayout = [[top-self.spacing]]
        for button in self.buttons:
            buttonElt = Button(text=button['text'])
            for param in button:
                setattr(buttonElt, param, button[param])
            row_height = "?"
            buttonLayout.append([self.spacing])
            row = [row_height, (None, left), (buttonElt, "?"), (None, right)]
            buttonLayout.append(row)
        buttonLayout.append([bottom])
        return buttonLayout

#endregion

#region Popups
class Popup(Layout):
    """
    A popup to be displayed above everything else. Can be added by calling screen.add_element, or Popup.show()

    Parameters
    ----------
    layout : list, optional
        The layout to use in this popup, by default []
    width : PSSMdimension, optional
        The width of the popup, by default "W*0.8"
    height : PSSMdimension, optional
        Height of the popup, by default "H*0.5"
    horizontal_position : PSSMdimension, optional
        Horizontal position of the upper left corner,, by default "(W-w)/2" (i.e. centered)
    vertical_position : PSSMdimension, optional
        Vertical position of the upper left corner, by default "(H-h)/2" (i.e. centered)
    background_color : Optional[ColorType], optional
        Color of the background, by default DEFAULT_BACKGROUND_COLOR
    blur_background : bool, optional
        If True, the screen is blurred, except for the popup itself, by default DEFAULT_BLUR_POPUP_BACKGROUND
    outline_color : Optional[ColorType], optional
        Color of the outline, by default None
    outline_width : int, optional
        Width of the outline, by default 5
    radius : str, optional
        Radius of the corners, by default "H*0.05"
    auto_close : bool, optional
        time of no input after which a popup is automatically closed. (Set to False, or lower than 0 to disable auto close for this popup). If true, will use the default time set on the parent screen, by default True
    popupID : str, optional
        Optional popupID, which means the popup is added to the screen's popup register, by default None
    """

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return Element.action_shorthands | {"show-popup": "async_show", "close-popup": "async_close"}

    @property
    def _emulator_icon(cls): return "mdi:tooltip"

    def __init__(self, layout=[], width: PSSMdimension = "W*0.8", height: PSSMdimension = "H*0.5",
                horizontal_position: PSSMdimension = "(W-w)/2", vertical_position: PSSMdimension = "(H-h)/2", 
                background_color : Optional[ColorType] = DEFAULT_BACKGROUND_COLOR, blur_background : bool = DEFAULT_BLUR_POPUP_BACKGROUND, outline_color : Optional[ColorType] = None, outline_width=5, radius="H*0.05",
                auto_close=True, popupID : str = None, **kwargs):

        super().__init__(layout=layout, background_color=background_color, 
                         outline_color=outline_color, outline_width=outline_width, radius=radius, **kwargs)

        self._width = width
        self._height = height
        self.horizontal_position = horizontal_position
        self.vertical_position = vertical_position
        self._isPopup = True
        self.auto_close = auto_close
        self.blur_background = blur_background

        if self.parentPSSMScreen != None:
            self.make_area()

        self._tapEvent : asyncio.Event
        "Event that is set when the popup is tapped. Used to track when to automatically close it."

        if popupID == None:
            self.__popupID = None
        else:
            self.__popupID = popupID

    #region
    # ----------------------------- popup properties ----------------------------- #
    @Element.tap_action.getter
    def tap_action(self) -> InteractionFunctionType: 
        self._tapEvent.set()
        return self._tap_action
    
    @property
    def popupID(self) -> str:
        "ID of this popup by which it can be found in the popup register, if not None"
        return self.__popupID
    
    @property
    def blur_background(self) -> bool:
        "If true, when adding the popup to the screen, the background around it is blurred"
        return self.__blur_background
    
    @blur_background.setter
    def blur_background(self, value):
        self.__blur_background = bool(value)

    @property
    def width(self) -> PSSMdimension:
        "The width of the popup"
        return self._width
    
    @width.setter
    def width(self, value: PSSMdimension):
        self._width = value

    @property
    def height(self) -> PSSMdimension:
        "The height of the popup"
        return self._height

    @height.setter
    def height(self, value: PSSMdimension):
        self._height = value

    @property
    def horizontal_position(self) -> PSSMdimension:
        "x Postion off the popup's upper left corner."
        return self._horizontal_position
    
    @horizontal_position.setter
    def horizontal_position(self, value: PSSMdimension):
        self._horizontal_position : PSSMdimension
        self._dimension_setter("_horizontal_position", value)

    @property
    def vertical_position(self) -> PSSMdimension:
        "y Position of the popups upper left corner"
        return self._vertical_position
    
    @vertical_position.setter
    def vertical_position(self, value: PSSMdimension):
        self._vertical_position : PSSMdimension
        self._dimension_setter("_vertical_position", value)

    @property
    def auto_close(self) -> Union[float,bool]:
        "The time with no interaction after which this popup is automatically closed. Set to False to disable. If True, it will use the default value of the screen instance."
        return self._auto_close
    
    @auto_close.setter
    def auto_close(self,value: Union[float,bool]):
        if value == False:
            self._auto_close = False
        elif type(value) is int or type(value) is float:
            if value < 0:
                self._auto_close = False
            else:
                self._auto_close = value
        else:
            self._auto_close = True
    #endregion

    def create_area_matrix(self):
        if self.area == None:
            self._area = self.make_area()
        super().create_area_matrix()

    def make_area(self):
        w = self._convert_dimension(self.width)
        h = self._convert_dimension(self.height)
        (x,y) = self._convert_dimension((self.horizontal_position, self.vertical_position),{"w":w,"h":h})
        return [(x, y), (w, h)]

    def show(self):
        loop = self.parentPSSMScreen.mainLoop
        loop.create_task(self.async_show())

    @elementactionwrapper.method
    async def async_show(self):
        ##Only allows adding one of a popup.
        if self.area != (a:= self.make_area()):
            self._area = a

        if self not in self.parentPSSMScreen.popupsOnTop:
            self.parentPSSMScreen.add_element(self)
            self.parentPSSMScreen.popupsOnTop.append(self)
        else:
            _LOGGER.warning(f"Popup {self.id} is already on screen. Close it first.")
        
        self._tapEvent = asyncio.Event()
        if self.auto_close:
            asyncio.create_task(self._auto_close_timer())
        if self in self.parentPSSMScreen.popupsOnTop:
            if self.parentPSSMScreen.popupsOnTop.count(self) > 1:
                ##For some reason it puts two menus on top?
                _LOGGER.warning("this is weird")
        return

    def close(self, *args, **kwargs):
        loop = self.parentPSSMScreen.mainLoop
        loop.create_task(self.async_close(*args, **kwargs))

    @elementactionwrapper.method
    async def async_close(self, *args, **kwargs):
        loop = self.screen.mainLoop
        task = loop.create_task(self.screen.async_remove_element(self))
        await task
        c = self.screen.popupsOnTop.count(self)
        for i in range(c):
            self.screen.popupsOnTop.remove(self)
        
        self._tapEvent.set()

        if self.screen.device.screenType == "E-Ink":
            await asyncio.to_thread(
                self.screen.device.refresh_screen)

    async def _auto_close_timer(self):
        if self.auto_close == True:
            time = self.parentPSSMScreen.close_popup_seconds
        else:
            time = self.auto_close
        if not time: 
            return
        while self in self.parentPSSMScreen.popupsOnTop:
            try:
                await asyncio.wait_for(self._tapEvent.wait(),time)
            except asyncio.TimeoutError:
                self._tapEvent.clear()
                _LOGGER.debug(f"Closing popup {self.id} automatically")
                await self.async_close()
            else:
                self._tapEvent.clear()


class PopupConfirm(Popup):
    """
    A simple popup that can show a prompt with a title, and two buttons to comfirm or cancel.
    args:
        titleText (str): Text to show in the popup title
        maintext (str): The main text to show in the popup, underneath the title
        confirmText (str): The text to show in the confirm button
        cancelText (str): Text to show in the cancel button
        mainTextXPos (str): horizontal alignment of the main text
        mainTextYPos (str): vertical alignment of the main text
        title_font (str): Font of the title
        title_font_size (str or int): size of the title text
        title_font_color (str): color of the title text
        (Etc. for other font settings.)
        
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-question"

    def __init__(self, titleText:str="", mainText:str="", confirmText:str="OK",
                cancelText:str="Cancel",
                title_font:str=DEFAULT_FONT, title_font_size:Union[str,int]=DEFAULT_FONT_SIZE,
                mainFont:str=DEFAULT_FONT, mainFontSize:Union[str,int]=DEFAULT_FONT_SIZE,
                buttonFont:str=DEFAULT_FONT, buttonFontSize:Union[str,int]=DEFAULT_FONT_SIZE,
                title_font_color:str="black", mainFontColor:str="black",
                buttonFontColor:str="black",
                mainTextXPos:Union[str,int]="center", mainTextYPos:Union[str,int]="center",
                **kwargs):
        super().__init__(**kwargs)
        self.titleText:str = titleText
        self.mainText:str = mainText
        self.confirmText:str = confirmText
        self.cancelText:str = cancelText
        self.title_font:str = title_font
        self.mainFont:str = mainFont
        self.buttonFont:str = buttonFont
        self.title_font_size:Union[str,int] = title_font_size
        self.mainFontSize:Union[str,int] = mainFontSize
        self.buttonFontSize:Union[str,int] = buttonFontSize
        self.title_font_color:str = title_font_color
        self.mainFontColor:str = mainFontColor
        self.buttonFontColor:str = buttonFontColor
        self.mainTextXPos:Union[str,int] = mainTextXPos
        self.mainTextYPos:Union[str,int] = mainTextYPos
        self.userAction = 0
        self.okBtn = None
        self.cancelBtn = None
        self.build_layout()

    def build_layout(self):
        titleBtn = Button(
            text=self.titleText,
            font=self.title_font,
            font_size=self.title_font_size,
            font_color=self.title_font_color
        )
        mainBtn = Button(
            text=self.mainText,
            font=self.mainFont,
            font_size=self.mainFontSize,
            font_color=self.mainFontColor,
            text_x_position=self.mainTextXPos,
            text_y_position=self.mainTextYPos
        )
        okBtn = Button(
            text=self.confirmText,
            font=self.buttonFont,
            font_size=self.buttonFontSize,
            font_color=self.buttonFontColor,
            tap_action=self.confirm
        )
        cancelBtn = Button(
            text=self.cancelText,
            font=self.buttonFont,
            font_size=self.buttonFontSize,
            font_color=self.buttonFontColor,
            tap_action=self.cancel
        )
        lM = (None,1)
        layout = [
            ["?*1.5", (titleBtn, "?"), lM],
            ["?*3", (mainBtn, "?"), lM],
            ["?*1", (okBtn, "?"), (cancelBtn, "?"), lM]
        ]
        self.layout = layout
        return layout

    def confirm(self, elt=None, coords=None):
            self.userAction = 1
            self.waitForResponse(1)

    def cancel(self,elt=None, coords=None):
            self.userAction = 2
            self.waitForResponse(2)
            

    def waitForResponse(self, action=0):
        if action == 0:
            return
        
        self.parentPSSMScreen.OSKHide()
        hasConfirmed = self.userAction == 1
        self.userAction = 0  # Reset the state
        self.close()
        return hasConfirmed


class PopupMenu(Popup):
    """
    Base class for popup menus. Provides a title bar and close icon, and a layout to fill in the rest.
    
    Parameters
    ----------
    menu_layout : Layout
        The layout to show underneath the menu header.
    title : str
        The title of the menu
    title_font : str, optional
        Font of the title text, by default DEFAULT_FONT_BOLD
    close_icon : _type_, optional
        icon to show in the top right corner. Closes the popup on tap, by default "mdi:close-thick"
    title_color : str, optional
        Color of the title text, by default "white"
    close_icon_color : ColorType, optional
        Color of the closing icon, by default "white"
    header_color : ColorType, optional
        Color of the header bar, by default DEFAULT_MENU_HEADER_COLOR    
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-outline"

    ##This one will provide the basis, but shouldn't be singleton
    ##Building: make layout with a title and a close button, everything underneath is up to the designer
    def __init__(self,  menu_layout : Layout, title : str, title_font : str = DEFAULT_FONT_HEADER,  close_icon : Optional[mdiType] = "mdi:close-thick", title_color : ColorType = "white", close_icon_color : ColorType = "white", header_color : ColorType = DEFAULT_MENU_HEADER_COLOR, **kwargs):
        self.title = title
        "Title of the menu"

        self.title_font = title_font
        "Font of the title"

        self.close_icon = close_icon
        "Icon in the top right corner, closes the menu."

        self.header_color = header_color
        self.menu_layout = menu_layout
        self.close_icon_color = close_icon_color
        self.title_color = title_color

        layout = self._build_popup_layout()
        super().__init__(layout, **kwargs)
    
    #region
    @colorproperty
    def header_color(self) -> ColorType:
        " Color of the header bar"
        return self._header_color

    @colorproperty
    def title_color(self):
        "Color of the title text"
        return self._title_color

    @colorproperty
    def close_icon_color(self):
        "Color of the closing icon"
        return self._close_icon_color

    @property
    def menu_layout(self) -> Layout:
        "The layout element that makes up the body of the popup"
        return self._menu_layout
    
    @menu_layout.setter
    def menu_layout(self, value):
        if isinstance(value, str):
            if value in self.screen.elementRegister:
                value = self.screen.elementRegister[value]
        self._menu_layout = value

    @property
    def title_font(self) -> str:
        "The font used for the popup title"
        return self._title_font
    
    @title_font.setter
    def title_font(self, value):
        self._title_font = value

    @property
    def close_icon(self) -> str:
        "The mdi icon to use for the button that closes the popup"
        return self._close_icon
    
    @close_icon.setter
    def close_icon(self, value):
        self._close_icon = value
    #endregion

    def _build_popup_layout(self):
        "Builds the layout to pass onto the popup class, using the settings for the menu header and the provided menu layout."
        ##I think this should be the generator?
        title_H = self._convert_dimension("H*0.1", {"H": self.screen.height})
        if title_H < 50:
            title_H = 50
        titleButton = Button(self.title, self.title_font, fit_text=True, font_size=40, font_color=self.title_color, show_feedback=False)
        close_icon = Icon(self.close_icon, tap_action=self.async_close, icon_color=self.close_icon_color)
        titleLayout = [["?*0.1", (None, "?")],["?*0.8",(titleButton,"?"),(close_icon,"r*2")], ["?*0.15", (None, "?")]]
        titleLayout = Layout(titleLayout, background_color=self.header_color)
        layout = [[title_H,(titleLayout,"w*1.01")],
                ["?", (self.menu_layout,"?")]]
        return layout

    async def async_generate(self, area=None, skipNonLayoutGen: bool = False) -> Coroutine[Any, Any, Image.Image]:
        async with self._generatorLock:
            self.layout= self._build_popup_layout()
        return await super().async_generate(area, skipNonLayoutGen)


class PopupButtons(Popup):
    ##Edited this from the normal buttons, to allow it to generate. Made by combining the input popup code with the main popup code.
    """
    A popup to be displayed above everything else with buttons, to simple ask a question
    Args:
        userButtons (list): The list of buttons to be added to the popup
        titleText (str): Title of popup
        mainText (str): String for the main body of text (set to None to omit field)
        width (str): The width of the popup
        height (str): The height of the popup
        horizontal_position (float): Relative position on the x axis of the center point
        vertical_position (float): Relative position on the y axis of the center point
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-text"

    def __init__(self, userButtons: list =[],  titleText:str="", mainText:str="",
                title_font:str=DEFAULT_FONT, title_font_size:str=DEFAULT_FONT_SIZE,
                mainFont:str=DEFAULT_FONT, mainFontSize:str=DEFAULT_FONT_SIZE,
                title_font_color="black", mainFontColor="black",
                mainTextXPos="center", mainTextYPos="center",
                width="W*0.8", height=None,
                background_color = None,
                horizontal_position:float=0.5, vertical_position:float=0.3, **kwargs):

        self.userButtons = userButtons
        self.titleText = titleText
        self.mainText = mainText
        self.title_font = title_font
        self.mainFont = mainFont
        self.title_font_size = title_font_size
        self.mainFontSize = mainFontSize
        self.title_font_color = title_font_color
        self.mainFontColor = mainFontColor
        self.mainTextXPos = mainTextXPos
        self.mainTextYPos = mainTextYPos
        self.background_color = background_color
        self.userAction = 0
        self.width = width
        if height == None:
            height = "H*0.5" if self.mainText != "" else "H/3"
        self.height = height
        self.horizontal_position = horizontal_position
        self.vertical_position = vertical_position

        super().__init__(layout = self.build_layout(), **kwargs)

    def build_layout(self):
        titleBtn = Button(
            text=self.titleText,
            font=self.title_font,
            font_size=self.title_font_size,
            font_color=self.title_font_color,
            outline_color="white",
            background_color= self.background_color
        )
        if self.mainText != "":
            mainBtn = Button(
                text=self.mainText,
                font=self.mainFont,
                font_size=self.mainFontSize,
                font_color=self.mainFontColor,
                text_x_position=self.mainTextXPos,
                text_y_position=self.mainTextYPos,
                outline_color="white",
                background_color= self.background_color
        )

        cancelBtn = Icon(
            'close',
            centered = True, 
            tap_action=self.close_popup,
            background_color= self.background_color
            )

        lM = (None,1)
        buttonLayout = ["?*1"]
        for element in self.userButtons:
            buttonLayout.append((element,"?"))
        buttonLayout.append(lM)

        if self.mainText != "":      
            layout = [
                ["?*1.5", (titleBtn, "?*0.8"), (cancelBtn, "?*0.2"), lM],
                ["?*1.5", (mainBtn, "?"), lM],
                buttonLayout
            ]
        else:
            layout = [
                ["?*1.5", (titleBtn, "?*0.8"), (cancelBtn, "?*0.2"), lM],
                buttonLayout
            ]
        self.layout = layout
        return layout

    async def close_popup(self,elt=None, coords=None):
            await self.parentPSSMScreen.async_remove_popup()

    def waitForResponse(self, action=0):
        if action == 0:
            return
        
        self.parentPSSMScreen.OSKHide()
        hasConfirmed = self.userAction == 1
        self.userAction = 0  # Reset the state
        self.parentPSSMScreen.remove_element(self)
        return hasConfirmed


class PopupDrawer(Popup):
    ##Edited this from the normal buttons, to allow it to generate. Made by combining the input popup code with the main popup code.
    """
    A popup to be displayed above everything else with buttons, to simple ask a question
    Args:
        drawerElements (list): The list of buttons to be added to the popup
        direction: (str) either up, down, left or right. defines direction of the popup
        drawerLength: (str or int): length of the drawer The secondary dimension (relatively, its width) depends on the paren element. If not specified will use (#elements*size(parent_elt))
        parentElt: element from which the popup will open
        overlapParent (bool): print the popup over the parent element, or the side of it
        showCloseArrow (bool): show an arrow that can be tapped to close the drawer? 
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-minus"

    def __init__(self, *drawerElements, parentElt, direction:str, drawerLength:Optional[Union[str,int]]=None, 
                overlapParent:bool=False, showCloseArrow:bool=True,
            **kwargs):
        super().__init__(**kwargs)
        self._drawerElements = drawerElements
        self.direction = direction
        self.parentElt = parentElt
        self.drawerLength = drawerLength
        self.userAction = 0
        self._overlapParent = overlapParent
        self._showCloseArrow = showCloseArrow
        
        #Going to do (messy) area calculations       
        self._closeButtonRes : float = 4 #The relative dimensions of the closing button

    #region 
    # -------------------------- Popupdrawer Properties -------------------------- #
    @property
    def drawerElements(self) -> Union[list,tuple]:
        "The elements within the drawer"
        return self._drawerElements

    @drawerElements.setter
    def drawerElements(self, value: Union[list,tuple]):
        ##Maybe perform a check here at a later point to test if these are actually valid elements? --> idk if it's directly possible from tools cause it may cause circularimports
        self._drawerElements = value

    @property
    def direction(self) -> str:
        "The opening direction of the drawer. Up, down, left or right."
        return self._direction
    
    @direction.setter
    def direction(self, value:str):
        if value.lower() not in ["up", "down", "left", "right"]:
            _LOGGER.error(f"{value} is not a valid drawer direction. Setting not applied")
        else:
            self._direction = value.lower()

    @property
    def offset(self):
        "The (x,y) offset of the drawer"
        return self._offset

    @property
    def drawerLength(self) -> Optional[Union[str,int]]:
        "The length of the drawer. If None, will be set to fit all elements"
        return self._drawerLength

    @drawerLength.setter
    def drawerLength(self,value: Optional[Union[str,int]]):
        self._drawerLength = value

    @property
    def showCloseArrow(self) -> bool:
        "True if the drawer shows an arrow to close it when opened."
        return self._showCloseArrow

    @showCloseArrow.setter
    def showCloseArrow(self,value:bool):
        self._showCloseArrow = value

    # ------------------ settings related to the parent element ------------------ #
    @property
    def parentElt(self):
        "The parent element that opens the drawer"
        return self._parentElt
    
    @parentElt.setter
    def parentElt(self, value : Element): ##Wonder if element works here to indicate it must be a PSSM element?
        self._parentElt = value
        self._parentArea = value.area

    @property
    def parentArea(self) -> list[tuple,tuple]:
        "The area of the drawers parent element"
        return self._parentArea

    @property
    def overlapParent(self) -> bool:
        "True if the drawer opens over the parent element, false if it opens on its edges"
        return self._overlapParent

    @overlapParent.setter
    def overlapParent(self,value:bool):
        self._overlapParent = value
    #endregion

    def make_area(self):
        overlap_parent = self.overlapParent
        show_close_arrow = self.showCloseArrow
        #Some offsets caused by the closing element within the drawer
        if self.direction == "up" or self.direction == "down":
            closeBtn_width = 0
            closeBtn_height = self.parentArea[1][0]/self._closeButtonRes
            if self.drawerLength == None:
                itemArea = [self.parentArea[1][0],len(self.drawerElements)*self.parentArea[1][0]]
            else:
                itemArea = [self.parentArea[1][0],self._convert_dimension(self.drawerLength)]
        elif self.direction == "right" or self.direction=="left":
            closeBtn_height = 0
            closeBtn_width = self.parentArea[1][1]/self._closeButtonRes
            if self.drawerLength == None:
                itemArea = [self.parentArea[1][1]*len(self.drawerElements),self.parentArea[1][1]]
            else:
                itemArea = [self._convert_dimension(self.drawerLength),self.parentArea[1][1]]

        self._closeButtonDim = [closeBtn_width, closeBtn_height] if show_close_arrow else [0,0]
        #Possible area values for the element. Offset is a little more than currently if the close buttons are defined. Should be able to calculate their size using width and height
        offsetArea = [int(itemArea[0] + self._closeButtonDim[0]), 
                        int(itemArea[1] + self._closeButtonDim[1])]

        #Setting the correct offsets for the given options
        #Remember: origin is in the upper left corner of element. Correct rotation for the closing button is also set here
        if self.direction == "up":
            self._closeRotation = 0
            self._offset = [0, self.parentArea[1][1]-offsetArea[1]] if overlap_parent else [0, -1*offsetArea[1]]
        elif self.direction == "down":
            self._closeRotation = 180
            self._offset = [0,0] if overlap_parent else [0, self.parentArea[1][1]]
        elif self.direction == "left":
            self._closeRotation = 90
            self._offset = [self.parentArea[1][0] - offsetArea[0],0] if overlap_parent else [-1*offsetArea[0], 0]
        elif self.direction == "right":
            self._closeRotation = 270
            self._offset = [0,0] if overlap_parent else [self.parentArea[1][0], 0]

        self._width = offsetArea[0]
        self._height = offsetArea[1]
        self._horizontal_position = self.parentArea[0][0] + self.offset[0]
        self._vertical_position = self.parentArea[0][1] + self.offset[1]

        self._area = [(self.horizontal_position, self.vertical_position), (self.width, self.height)]
        #postions have to fixed a little to have the start coordinates correct for the popup
        
    def generator(self,**kwargs):
        if not self.isGenerating:
            self.make_area()
            self.build_layout()
        super().generator(**kwargs)

    async def async_generate(self, area=None, skipNonLayoutGen: bool = False) -> Coroutine[Any, Any, Coroutine[Any, Any, Image.Image]]:
        async with self._updateLock:
            self.make_area()
            self.build_layout()
    
        return await super().async_generate(area, skipNonLayoutGen)

    def build_layout(self):

        closeBtn = Icon(
            "arrow",
            centered = True,
            icon_color="gray10",
            tap_action=self.close_drawer,
            background_color= self.background_color,
            forceSquare=False,
            rotation_angle=self._closeRotation
            )

        #close button size determined by trial and error I guess
        layout = []
        if self.direction == "up" or self.direction=="down":
            for element in self.drawerElements:
                eltrow = ["?", (element,"?")]
                layout.append(eltrow)
            
            if self.showCloseArrow:
                closeRow = [int(self._closeButtonDim[1]), (None,"?/2"), (closeBtn, int(self._closeButtonDim[1]*2)), (None,"?/2")]
                layout.insert(0, closeRow) if self.direction == "up" else layout.append(closeRow)

        elif self.direction == "right" or self.direction=="left":
            layout.append(["?*1"])
            layoutRow = layout[0]
            for element in self.drawerElements:
                layoutRow.append((element,"?"))
            if self.showCloseArrow:
                closeCol = (Layout([["?/2"],[int(self._closeButtonDim[0]*1.75), (closeBtn,"?")],["?/2"]]), int(self._closeButtonDim[0]))
                if self.direction == "left":
                    layoutRow.insert(1, closeCol)
                else:
                    layoutRow.append(closeCol)
            layout[0] = layoutRow

        self.layout = layout
        return layout

    def close_drawer(self,elt=None, coords=None):
            self.userAction = 1
            self.close()

    def waitForResponse(self):
        while self.userAction == 0:
            self.parentPSSMScreen.device.wait(0.01)
        self.parentPSSMScreen.OSKHide()
        hasConfirmed = self.userAction == 1
        self.userAction = 0  # Reset the state
        self.parentPSSMScreen.remove_element(self)
        return hasConfirmed

#endregion

class Button(Element):
    """
    Basically a rectangle (or rounded rectangle) with text printed on it

    Parameters
    ----------
    text : Optional[str], optional
        The text to show, by default ""
    font : str, optional
        font to use, either a shorthand font or fontfile, by default DEFAULT_FONT
    font_size : PSSMdimension, optional
        Size to use for the font, by default DEFAULT_FONT_SIZE
    font_color : Union[bool,ColorType], optional
        Color of the font, by default True (Automatically picks a contrasting color)
    background_color : _type_, optional
        Background color, by default None
    outline_color : Optional[ColorType], optional
        Outline color, by default None
    outline_width : PSSMdimension, optional
        Outline width, by default 1
    radius : int, optional
        Corner radius, by default 0
    margins : int, optional
        text margins, by default 0 (Can be set as CSS margins)
    text_x_position : Union[int,Literal[&quot;l&quot;,&quot;m&quot;,&quot;r&quot;,&quot;s&quot;]], optional
        Horizontal position of the text anchor, by default "center"
    text_y_position : Union[int,Literal[&quot;a&quot;,&quot;t&quot;,&quot;m&quot;,&quot;s&quot;,&quot;b&quot;,&quot;d&quot;]], optional
        Vertical position of the text anchor, by default "center"
    text_anchor_alignment : textAlignmentType, optional
        alignment of the text anchor, by default (None,None)
    multiline : bool, optional
        Use multiline text, either as defined or if the text does not fit, by default False
    isInverted : bool, optional
        Invert the Element, by default False
    resize : bool, optional
        Changes the font_size parameter when needed, such that the text size won't change with every new text. Sizes are not saved upon resets, so finding a good size takes a few changes. 
        Value acts as a minimum allowed size, by default False
    fit_text : bool, optional
        fit text into the Element's area. If true, font_size will be used as the minimum font_size (set to 0 for no minimum), by default False
    """

    @property
    def _emulator_icon(cls): return "mdi:alpha-b-box"

    def __init__(self, text: Optional[str]="", font:str=DEFAULT_FONT, font_size: PSSMdimension = DEFAULT_FONT_SIZE, font_color : Union[bool,ColorType] = DEFAULT_FOREGROUND_COLOR, #"black",
                background_color: ColorType =None, outline_color: Optional[ColorType] = None, outline_width : PSSMdimension = 1, radius:int=0, 
                margins : int = 0, text_x_position : Union[int,Literal["l","m","r","s"]] ="center", text_y_position : Union[int,Literal["a","t","m","s","b","d"]] ="center", text_anchor_alignment : textAlignmentType = (None,None), multiline : bool =False, 
                isInverted:bool=False, resize=False, fit_text=False, **kwargs):

        super().__init__(isInverted=isInverted, **kwargs)
        
        if text != None:
            self.text = text
        
        self.background_color = background_color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.font = font
        self.font_size = font_size
        self.radius = radius
        self.font_color = font_color

        self.margins = margins
        self.text_x_position = text_x_position
        self.text_y_position = text_y_position
        self.text_anchor_alignment = text_anchor_alignment
        
        self._loadedFont = None
        self._convertedText = None
        self._imgDraw = None
        self.fit_text = fit_text
        self.resize = resize
        self._multiline = multiline

        self._current_font_size = 0
        "The currently used font_size, in pixels"

    # -------------------------- Text element properties ------------------------- #
    #region
    @property
    def textArea(self) -> PSSMarea:
        return self._textArea
    
    @property 
    def text(self) -> str:
        "The current text displayed on the button. Setting this attribute automatically converts the value into a string."
        return self.__text
    
    @text.setter
    def text(self, value:str):
        if not isinstance(value,str):
            _LOGGER.debug(f"Converting {type(value)} to a string")
            value = str(value)
        self.__text = value

    @property
    def font(self):
        "The path to the element's font. If set to a known font, the path will automatically be added"
        return self._font
    
    @font.setter
    def font(self,value:str):
        value = tools.parse_known_fonts(value)
        self._font = value

    @property
    def loadedFont(self):
        "The font loaded via the font property (popuplated after screen is generated)"
        return self._loadedFont

    @colorproperty
    def font_color(self):
        "The color of the font"
        return self._font_color

    @property
    def font_size(self) -> Union[str,int]:
        "The size of the font"
        return self._font_size
    
    @font_size.setter
    def font_size(self, value : Union[str,int]):
        self._font_size: PSSMdimension
        self._dimension_setter("_font_size", value)
    
    @property
    def radius(self) -> Union[str,int]:
        "Corner radius of the encapsulating rectangle. Currently only accepts integers"
        return self._radius
    
    @radius.setter
    def radius(self,value:int):
        self._dimension_setter("_radius",value)

    @colorproperty
    def outline_color(self) ->  Union[ColorType,None]:
        "Color of the elements outline. Set to None to use no outline (i.e. the background color)"
        return self._outline_color

    @property
    def outline_width(self) -> PSSMdimension:
        "The width of the outline of the background rectangle"
        return self._outline_width

    @outline_width.setter
    def outline_width(self, value : PSSMdimension):
        self._dimension_setter("_outline_width",value)

    @property
    def imgDraw(self) -> ImageDraw:
        return self._imgDraw
    
    # ---------------------------- Textbox properties ---------------------------- #
    @property
    def margins(self) -> tuple[int,int,int,int]:
        """
        The text margins. Always returns a 4 tuple, but can be set to a single number, or two/three/four item iterable. 
        Same as css margins, so the values are returned as (top,right,bottom,left), and set according to css margins (https://www.w3schools.com/css/css_margin.asp)
        """
        return self._margins
    
    @margins.setter
    def margins(self, value : PSSMdimension):
        self._margins : PSSMdimension
        if isinstance(value,(tuple,list)):
            if len(value) > 4:
                msg = f"Margin lists cannot be larger than 4."
                _LOGGER.exception(msg,ValueError(msg))
                return
            elif len(value) == 2:
                value = value*2
            elif  len(value) == 3:
                value = (value[0],value[1],value[2],value[1])
        
        elif isinstance(value,(int,float,str)):
            value = (value,)*4
        else:
            msg = f"Invalid margin type."
            _LOGGER.exception(msg,TypeError(msg))
            return
        self._dimension_setter('_margins',value)
    
    @property
    def multiline(self) -> bool:
        "Will text not fitting within the bounding box be wrapped to the next line?"
        return self._multiline
    
    @multiline.setter
    def multiline(self, value:bool):
        self._multiline = value

    @property
    def fit_text(self) -> bool:
        "Is text fitted within the bounding box? If true, font_size will be used as minimum font_size"
        if self.resize != False: ##This prevents a value of 0 from messing stuff up
            return True
        return self._fit_text
    
    @fit_text.setter
    def fit_text(self,value:bool):
        self._fit_text = value

    @property
    def resize(self) -> Union[bool,str,int,float]:
        """
        If not False, will use this value as a minimum allowed size for any text displayed. 
        Changes the font_size parameter when needed, such that the text size won't change with every new text. Sizes are not saved upon resets, so finding a good size takes a few changes. 
        The same goes when the element is resized.
        """
        return self.__resize
    
    @resize.setter
    def resize(self, value):
        if isinstance(value, bool):
            if value != False:
                msg = "Resize cannot be explicitly true, please use an integer or dimensional string"
                _LOGGER.exception(ValueError(msg))
            else:
                self.__resize = value
            return

        if v := tools.is_valid_dimension(value):
            if isinstance(v,Exception):
                _LOGGER.exception(v,exc_info=v)
            else:
                self.__resize = value
            
    @property
    def text_x_position(self) -> Union[int,Literal["l","m","r","s"]]:
        "Horizontal alignment of the text. Can be top, bottom or center, a Pillow textanchor (shorthand and longhand), a pssm dimensional string or an integer."
        return self._text_x_position

    @text_x_position.setter
    def text_x_position(self, value:Union[str,int]):
        if isinstance(value,int):
            if value < 0:
                _LOGGER.error(f"Text position must be a positive or 0 integer, {value} is not valid, setting to 0")
                value = 0
        else:
            ops = ["left","middle","right","center"]
            PILvals = ["l","m","r","s"]
            if value in ["baseline","s"]:
                _LOGGER.error("Baseline alignment is only for vertical text, which is not implemented. Setting to center")
                value = "center"
            elif value.lower() not in ops and value.lower() not in PILvals:
                valid = tools.is_valid_dimension(value)
                if isinstance(valid,Exception):
                    _LOGGER.error(f"{value} is not a valid dimensional string for text_x_position: {valid}. Setting to center")
                    value = "center"

        self._text_x_position = value

    @property
    def text_y_position(self) -> Union[int,Literal["a","t","m","s","b","d"]]:
        "Vertical alignment of the text. Can be top, bottom or center, a Pillow textanchor (shorthand and longhand), a pssm dimensional string or an integer."
        return self._text_y_position

    @text_y_position.setter
    def text_y_position(self, value:Union[str,int]):
        if isinstance(value,int):
            if value < 0:
                _LOGGER.error(f"Text position must be a positive or 0 integer, {value} is not valid")
                value = 0
            else:

                PILvals = ["a","t","m","s","b","d"]
                ops = ["ascender","top","middle","baseline","bottom","descender"]
                if value.lower() not in ops and value.lower() not in PILvals:
                    valid = tools.is_valid_dimension(value)
                    if isinstance(valid,Exception):
                        _LOGGER.error(f"{value} is not a valid dimensional string for text_y_position: {valid}. Setting to center")
                        value = "center"
            
        self._text_y_position = value

    @property
    def text_anchor_alignment(self) -> tuple[Literal[None,"l","m","r","s"],Literal[None,"a","t","m","s","b","d"]]:
        "Alignment of the textAnchor as (horizontal,vertical). Leave (one of) None to determine the anchor from text_x_position or text_y_position respectively. See https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors for possible values, only accepts shorthands."
        return self._text_anchor_alignment
    
    @text_anchor_alignment.setter
    def text_anchor_alignment(self, value: tuple[Literal[None,"l","m","r","s"],Literal[None,"a","t","m","s","b","d"]]):
        (horV, verV) = value
        if horV == None:
            hor = None
        elif horV in ["l","m","r","s"]:
            hor = horV
        else:
            _LOGGER.error(f"{horV} is not a valid horizontal alignment. Please ensure you used a value from the Pillow docs, or None. Setting value to None")
            hor = None

        if verV == None:
            ver = None
        elif verV in ["a","t","m","s","b","d"]:
            ver = verV
        else:
            _LOGGER.error(f"{verV} is not a valid vertical alignment. Please ensure you used a value from the Pillow docs, or None. Setting value to None")
            ver = None
        self._text_anchor_alignment = (hor, ver)

    @property
    def textAlignment(self) -> tuple[tuple[xType,yType],str]:
        """
        The text's (x,y) coordinates and the alignment of the text anchor, depends on text_x_position and text_y_position. 
        If both are integers, or pssm dimensional strings, it will default to 'la'.
        """
        (xAnch,yAnch) = self.text_anchor_alignment
        xAL = self.text_x_position
        horAL = ["l","m","r","s"]# --> s is not valid but xPosition cannot be set to it anyways
        horDict = { "left": "l",
                    "middle": "m",
                    "right": "r",
                    "center": "m",
                    "baseline": "s" }
        horCoords = {"l": 0, "m": "w/2", "r": "w"}
        if xAnch != None:
            hor = xAnch
            x = horCoords[xAnch]
        elif xAL in horAL:
            hor = xAL
            x = horCoords[hor]
        elif xAL in horDict:
            hor = horDict[xAL]
            x = horCoords[hor]
        else:
        ##xPosition setter already checks if it is a valid dimensional string, so we do not need to validate that. This also catches  if it's an integer
            hor = "l"
            x = xAL

        yAL = self.text_y_position
        verAL = ["a","t","m","s","b","d"]# --> s is not valid but xPosition cannot be set to it anyways
        verDict = { "ascender": "a",
                    "top": "a" if self.multiline else "t", ##Using t for top instead of a since it aligns it to the top like someone would (likely) expect. a leaves quite some space underneath still
                    "middle": "m",
                    "baseline": "s",
                    "bottom": "d" if self.multiline else "b",
                    "descender": "d",
                    "center": "m" }
        verCoords = {"a": 0, "t": 0, "m": "h/2", "s": "h*0.95", "b": "h", "d": "h"}
        if yAnch != None:
            ver = yAnch
            y = verCoords[yAnch]
        elif yAL in verAL:
            ver = yAL
            y = verCoords[ver]
        elif yAL in verDict:
            ver = verDict[yAL]
            y = verCoords[ver]
        else:
            ver = "a"
            y = yAL

        return ((x,y),hor+ver)
    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        if area == None:
            area = self.area

        if area == None:
            _LOGGER.verbose(f"Element {self} has no area asigned. Returning")
            ##No area assigned yet, wait till it is done by a layout
            return

        [(x, y), (w, h)] = area

        marg = self._convert_dimension(self.margins)
        textArea = [(area[0][0]+marg[3], area[0][1]+marg[0]),(area[1][0]-marg[1], area[1][1]-marg[2])]
        self._area = area
        img_background = self.parentBackgroundColor if self.background_color == None else self.background_color
        img_mode = self.parentPSSMScreen.imgMode
        if self.parentPSSMScreen.imgMode != 'RGBA':
            img_background = self.parentBackgroundColor if self.background_color == None else self.background_color
        else:
            img_background = self.background_color

        if self.radius != 0 or (self.outline_width != 0 and self.outline_color != None):
            img = Image.new(self.parentPSSMScreen.imgMode,(w,h),color=None)
            r = self._convert_dimension(self.radius)
            outW = self._convert_dimension(self.outline_width)
            yOff = outW
            xOff = r if r>outW else outW
            textArea =  [(textArea[0][0]+xOff, textArea[0][1]+yOff),(textArea[1][0]-xOff, textArea[1][1]-yOff)]
            drawArgs = {
                "xy": [(0,0),(w,h)],
                "radius": r,
                "fill": Style.get_color(self.background_color, img_mode),
                "outline": Style.get_color(self.outline_color, img_mode),
                "width": self._convert_dimension(self.outline_width)
                }

            (img, _) = DrawShapes.draw_rounded_rectangle(img, drawArgs=drawArgs, rescale=["xy","radius","width"], paste=False)
            
            ##drawImg from drawShapes is returned in the higher resolution. Create a new one since it otherwise it messes up the fitting functions and parsers
            ##Luckily textdraw does not suffer from resolution loss
            imgDraw = ImageDraw.Draw(img, self.parentPSSMScreen.imgMode)
        else:
            col = Style.get_color(img_background,self.parentPSSMScreen.imgMode)
            img = Image.new(self.parentPSSMScreen.imgMode,(w,h),color=col)
            imgDraw = ImageDraw.Draw(img, self.parentPSSMScreen.imgMode)

        self._imgDraw = imgDraw

        if self.fit_text:
            loaded_font = self.fit_text_func(self.text, textArea, self.font)
        else:
            font_size = self.font_size
            if not isinstance(font_size, int):
                font_size = self._convert_dimension(font_size)
                if not isinstance(font_size, int):
                    # That's a question mark dimension, or an invalid dimension.
                    # Rollback to default font size
                    font_size = self._convert_dimension(DEFAULT_FONT_SIZE)
            
            self._current_font_size = font_size
            loaded_font = ImageFont.truetype(self.font, font_size)
        self._loadedFont = loaded_font

        if self.multiline:
            myText = self.wrapText(self.text, loaded_font, imgDraw)
        else:
            myText = self.text
        self._convertedText = myText
        ((x,y),anchor) = self.textAlignment

        if not isinstance(x,int):
            x = self._convert_dimension(x, variables={"w": textArea[1][0], "h": textArea[1][1]})        
        x = x + abs(textArea[1][0] - area[1][0])

        if not isinstance(y,int):
            y = self._convert_dimension(y, variables={"w": textArea[1][0], "h": textArea[1][1]})
        y = y + abs(textArea[1][1] - area[1][1])
    
        if isinstance(self.font_color, bool):

            if self.background_color == None:
                text_bg = self.parentBackgroundColor
            else:
                text_bg = self.background_color

            textCol = Style.contrast_color(text_bg, img_mode)
        else:
            textCol = Style.get_color(self.font_color, self.parentPSSMScreen.imgMode)
        
        if self.multiline:
            alignment = "left"

            alignment = self.text_x_position
            align_vals = {"left", "center", "right"}
            align_map = {"l": "left", "middle": "center", "m": "center", "r": "right", "s": "center", "baseline": "center"}
            
            if alignment in align_map:
                alignment = align_map[alignment]
            
            if alignment not in align_vals:
                alignment = "left"

            imgDraw.multiline_text(
                (x, y),
                myText,
                font=loaded_font,
                fill=textCol,
                anchor=anchor,
                align=alignment
            )
        else:
            imgDraw.text(
                (x, y),
                myText,
                font=loaded_font,
                fill=textCol,
                anchor=anchor, 
            )
        
        if self.inverted:
            img = tools.invert_Image(img)

        self._textArea = textArea
        return img

    def wrapText(self, text, loaded_font, imgDraw : ImageDraw.ImageDraw):
        def get_text_width(text):
            return imgDraw.textlength(text=text, font=loaded_font)

        [(x, y), (max_width, h)] = self.area
        text_lines = [
            ' '.join([w.strip() for w in line.split(' ') if w])
            for line in text.split('\n')
            if line
        ]
        space_width = get_text_width(" ")
        wrapped_lines = []
        buf = []
        buf_width = 0

        for line in text_lines:
            for word in line.split(' '):
                word_width = get_text_width(word)

                expected_width = word_width if not buf else \
                    buf_width + space_width + word_width

                if expected_width <= max_width:
                    # word fits in line
                    buf_width = expected_width
                    buf.append(word)
                else:
                    # word doesn't fit in line
                    wrapped_lines.append(' '.join(buf))
                    buf = [word]
                    buf_width = word_width
            if buf:
                wrapped_lines.append(' '.join(buf))
                buf = []
                buf_width = 0
        return '\n'.join(wrapped_lines)

    def fit_text_func(self, text : str, area : list[tuple[int],tuple[int]], font : str):
        #Start with the default size as an initial guess
        [(x, y), (w, h)] = area
        
        if self.resize != False:
            min_size = self._convert_dimension(self.resize)
            start_size = self._convert_dimension(self.font_size)
        else:
            min_size = self._convert_dimension(self.font_size)
            start_size = floor(h*0.95)

        min_size = max(min_size, 1)
        text_height = max(start_size,1)

        loaded_font = ImageFont.truetype(font, text_height)
        text_length = loaded_font.getlength(text)
        
        if text_length > w*0.95:
            text_height = int((text_height*w*0.95)/text_length)
            if text_height < min_size:
                _LOGGER.debug(f"Could not fit {text} without violating min size {min_size}, height required is {text_height}" )
                text_height = int(min_size)
            loaded_font = loaded_font.font_variant(size=text_height)
            text_length = loaded_font.getlength(text)
            _LOGGER.verbose(f"Fitted text {text} with length {text_length} into area {area}")
        
        self._current_font_size = text_height
        if self.resize:
            self.font_size = text_height
        
        return loaded_font


class ImageElement(Element):
    """
    Base class for the Picture and Icon element, for shared properties
    Currently not implemented for the Icon class yet.
    """

    @property
    def background_shape(self) -> Literal[IMPLEMENTED_ICON_SHAPES_HINT]:
        """
        The shape of the icons background. If not set, no shape is used and background color is used as the background color of the entire element of the area.
        Can be one of ["circle", "square", "rounded_square", "rounded_rectangle", "octagon", "hexagon"], None or ADVANCED. See background_shapeDict for usage of advanced (Not fully tested, so be aware)
        Set to None for no background shape.
        """
        return self._background_shape
    
    @background_shape.setter
    def background_shape(self, value:Union[str,None]):
        if value == None or value.lower() == "none":
            self._background_shape = None
        elif value == "ADVANCED":
            _LOGGER.debug("Advanced icon shape applied")
            self._background_shape = value
        elif value.strip().lower().replace(" ","_") in IMPLEMENTED_ICON_SHAPES:
            ##Maybe add some string stuff like lower in here to allower for minor changes in what people fill in.
            ##Mainly, remove spaces for underscores, and lower all text
            self._background_shape = value 
        else:
            _LOGGER.error(f"{value} is not a predefined icon background shape, nor is it set to ADVANCED. Setting shape to none")
            self._background_shape = None

    @property
    def shape_settings(self) -> dict:
        """
        Settings for the background shape. Advanced setting, generally best to leave it as an emtpy dict. Stuff may not work as intended as I cannot test everything.
        Optional arguments are required using ADVANCED, except for icon_coords (icon will default to being centered)
        Usage:
            method[Optional] (str): ImageDraw method to call. Only used when using background_shape ADVANCED
            drawArgs (dict): dict with arguments to be passed to the ImageDraw function. If background_shape is an implemented shape, omitting arguments will means default values will be used.
        """
        return self._shape_settings.copy()
    
    @shape_settings.setter
    def shape_settings(self, value:dict):
        value = value.copy()
        self._shape_settings = value

    @property
    def mirrored(self) -> bool:
        """Is the icon mirrored?"""
        return self._mirrored
    
    @mirrored.setter
    def mirrored(self,value:bool):
        self._mirrored = value

    @property
    def fileError(self) -> bool:
        """Returns true if the currently set value for icon did not return a valid icon or image"""
        return self._fileError


class Picture(ImageElement):
    """
    Element that can be used to display picture files.

    Parameters
    ----------
    picture : Union[str, Path, Image.Image]
        The path pointing to the picture file. Singular files (Like picture.jpg) or paths beginning with '/' (like /folder/picture.jpg) will have the file sought for in the custom picture folder.
    background_color : _type_, optional
        Element background color, by default None
    background_shape : IMPLEMENTED_ICON_SHAPES_HINT, optional
        Shape of the background, by default None. When not None, the image will be formed into this shape (i.e. cut off, or padded to fit).
    shape_settings : str, optional
        Optional settings to apply to the background shape. by default {}
    fit_method : Literal["contain", "cover", "fit", "pad", "resize", "crop"], optional
        The way to fit the picture into the element area, by default "fit".
        Pictures, upon opening, will be set to cover the assigned area, after which the fitting_method is applied.
        This behaviour can be turned off by setting _cover_element_area to `False`
    fit_method_arguments : dict, optional
        Optional arguments to apply to the fitting method. Advanced method, and all fitting methods can be used without, by default {}
    isInverted : bool, optional
        If the picture should be inverted, by default False
    mirrored : bool, optional
        If the picture should be mirrored, by default False
    """

    @property
    def _emulator_icon(cls): return "mdi:image"

    def __init__(self, picture: Union[str, Path, Image.Image], background_color : Optional[ColorType]=None, 
                background_shape:IMPLEMENTED_ICON_SHAPES_HINT = None, 
                fit_method = "fit", fit_method_arguments : dict = {}, shape_settings : dict = {},
                isInverted = False, mirrored = False,
            **kwargs):  

        self._pictureImage = None

        if picture != None:
            self.picture = picture
        else:
            self._fileError = False
            self.picture = Image.new("P", (50,50), None)

        self.background_shape = background_shape
        self.shape_settings = shape_settings

        self._force_open : bool = False
        """
        Force the image file to be opened each time the generator is called.
        May help fix the image dissapearing at some point (though that should not happen and warrants a bug report)
        Setting this to `True` will affect performance. Defaults to `False`.
        """

        self._cover_element_area : bool = True
        """
        When the picture attribute is changed, or the element's area changes, the picture (either the opened file or the `Image.Image` instance), is resized to cover the element area.
        Setting this to `False` prevents this from happening. Defaults to `True`, may lead to unexpected results.
        """

        self.fit_method = fit_method
        self.fit_method_arguments = fit_method_arguments
        self.mirrored = mirrored

        self.__area = None
        self.__pictureData = None

        super().__init__(isInverted=isInverted, background_color=background_color, **kwargs)
        return

    #region
    @property
    def picture(self) -> Union[str, Path, Image.Image]:
        "The file or Image object use as the picture. By default searched the folder that is set as the custom picture folder for the picture file."
        return self._picture
    
    @picture.setter
    def picture(self, value: Union[str, Path, Image.Image]):
        img = value

        ##It'll be set to false in the end anyways this should be fine
        self._fileError = True
        if not isinstance(img, Image.Image):
            if isinstance(img, Path):
                p = img
            else:
                if img[0] == "/" or img[0:2] != "./":
                    p = const.CUSTOM_FOLDERS["picture_folder"] / img
                else:
                    p = Path(img)
                
            if not p.exists():
                msg = f"Picture file {p} does not exist."
                _LOGGER.error(msg)            
            self.__picturePath = p

        else:
            
            value = value.copy()
            self.__picturePath = None

            ##Can/should I do this in a thread? May be too easy like this to block the event loop
            ##Can simply make a tool for it, and add an async function here that's run as a task for it.
            ##And in the generator just wait for it to be opened.
        
        self.__reopen = True
        self._picture = value
        self._fileError = False

    @property
    def pictureData(self) -> Any:
        "Property that can be used to hold additional data for the picture"
        #Leaving this in camelCase since it's generally not used for how the element looks, despite it having a setter
        return self.__pictureData
    
    @pictureData.setter
    def pictureData(self, value):
        self.__pictureData = value

    @property
    def pictureImage(self) -> Image.Image:
        "Image object of the picture"

        ##If running into problems with copy (i.e. Nonetype has no attribute read, or whatever):
        ##It seems to work best to open the image, but set the attribute as a copy of it
        ##May need to check though, perhaps it's good to add the reopen property? (set when the area changes)
        return self._pictureImage.copy()

    @property
    def fit_method(self) -> Literal["contain", "cover", "fit", "pad", "resize", "crop"]:
        """
        The way to fit the picture to the element area. 
        Cover and Contain are the base methods, and will always work (i.e. won't break no matter what is set in fit_method_arguments)
        All other functions do work without setting the fit_method_arguments, but can break when setting options for that.
        
        When using crop, the image will be resized to the alloted area if it is not the correct size

        If the image still does not happen to be the correct size, it will be forcibly fitted.

        Returns
        -------
        Literal["contain", "cover", "fit", "pad", "resize", "crop"]
            The method to used to fit the picture.
        """
        return self.__fit_method
    
    @fit_method.setter
    def fit_method(self, value):
        if value not in ["resize", "crop", "contain", "cover", "fit", "pad"]:
            msg = f"{value} is not an allowed fit_method. Using default value and method"
            _LOGGER.warning(msg)
            value = "default"

        self.__fit_method = value

    @property
    def fit_method_arguments(self) -> dict:
        """
        Arguments to apply to the fitting method.

        For resize, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize
        For crop, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.crop
        
        For the other methods, see: https://pillow.readthedocs.io/en/stable/reference/ImageOps.html

        

        Returns
        -------
        dict
            arguments for the fitting method.
        """
        
        ##For resampling method: each method has an integer value: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Resampling.NEAREST
        ##Do apply a check for method, i.e. it must be an integer value
        return self.__fit_method_arguments.copy()
    
    @fit_method_arguments.setter
    def fit_method_arguments(self, value):
        self.__fit_method_arguments = MappingProxyType(value)
    
    @property
    def _area(self):
        """
        Private area property. Has a setter to allow for reopening the image file when it changes (cause it can also be set by layouts). Generally don't touch this.
        """
        return self.__area

    @_area.setter
    def _area(self, value):
        if value == self.__area:
            return
        
        self.__area = value
        self.__reopen = True
    #endregion

    def generator(self, area: CoordType[CoordType, CoordType] = None, skipNonLayoutGen: bool = False) -> Image.Image:
        
        if area == None:
            area = self.area
        else:
            self._area = area

        if area == None:
            _LOGGER.warning(f"Element {self} has no area asigned. Cannot generate")
            return

        [(x, y), (w, h)] = area
        size = (w,h)

        try:
            if self.__reopen or self._force_open:
                
                ##This should ensure the image file is always opened before continueing to generate
                ##Idea behind it: opening (may) take a while. So it's faster to have the image object already loaded
                ##Like this, it will be opened in the generator if needed (generators all run in a thread, so should be non-blocking), but is only opened in here if the element is still busy opening it.

                if not isinstance(self.picture, Image.Image):
                    img = Image.open(self.__picturePath).copy()
                else:
                    img = self.picture.copy()

                self.__reopen = False

                if self._cover_element_area:
                    self._pictureImage = ImageOps.cover(img,size,Image.Resampling.LANCZOS)
                else:
                    self._pictureImage = img
                
                img = self._pictureImage
                self._fileError = False
            else:
                img = self.pictureImage
        except (FileNotFoundError, AttributeError):
            ##Make missing image.
            _LOGGER.error(f"Unable to open image at {self.__picturePath}")
            self._fileError = True
            self.__reopen = True
            img = Image.new("RGBA", size, "gray")
            img = mdi.draw_mdi_icon(img, MISSING_PICTURE_ICON, icon_size=int(h*0.3))
            self._pictureImage = img

        if self.background_shape != None:

            ##Add in the shape_settings, and a way to automatically set a background color
            ##Probably the element background?

            if self.background_shape == "ADVANCED":
                method = self.shape_settings.pop("method")
                try:
                    (shape_img, _) = DrawShapes.draw_advanced(Image.new("RGBA", (w,h)), method, 
                                                drawArgs=self.shape_settings.get("drawArgs",{}), paste=False)
                except FuncExceptions as exce:
                    _LOGGER.error(f"Error drawing advanced shape {method}: {exce}")
            else:
                draw_func = DrawShapes.get_draw_function(self.background_shape)
                drawArgs = self.shape_settings.get("drawArgs",{})
                if not "fill" in drawArgs:
                    ##Gotta use parentBackgroundColor since the background_shape will be used as a mask too.
                    drawArgs["fill"] = self.parentBackgroundColor if self.background_color == None else self.background_color
                    # if drawArgs["fill"] == None: drawArgs["fill"] = "black"
                (shape_img, _) = draw_func(Image.new("RGBA", (w,h)), drawArgs=drawArgs, paste=False)

            ##This would assume no transparency data in the image
            ##So fix this using a paste with mask I think.

        if self.background_shape != None:
            pic_area = shape_img.getbbox() if shape_img.getbbox() else (0,0,w,h)
        else:
            pic_area = (0,0,w,h)
        pic_size = (pic_area[2]-pic_area[0], pic_area[3]-pic_area[1])
        
        ##None should automatically go to the last fit function which is not necessary anyways
        fit_func =  self.fit_method if not self.fileError else None

        if img.size == pic_size:
            pass
        else:
            ##Gotta go through the method_arguments as it may require some colouring at least.
            if fit_func == "crop":
                kwargs = {"box": self.fit_method_arguments.get("box", pic_area)}
            elif fit_func == "contain":
                ##Don't need to use parentbackground or something since that'll get pasted over anyways
                kwargs = {"color": self.fit_method_arguments.get("color", self.background_color)}
                if "method" in self.fit_method_arguments:
                    kwargs["method"] = self.fit_method_arguments["method"]
            elif fit_func == "cover":
                kwargs = {"method": self.fit_method_arguments.get("method", Image.Resampling.BICUBIC)}
            else:
                kwargs = dict(self.fit_method_arguments)

            img = tools.fit_Image(img, pic_size, fit_func, kwargs)

        if self.isInverted:
            img = tools.invert_Image(img)

        if self.mirrored:
            img = ImageOps.mirror(img)

        if self.background_shape != None:
            mask = shape_img.crop(shape_img.getbbox()).getchannel("A")
            mask = Image.eval(mask, lambda p: 255 if p > 0 else 0)

            ##Using a new image gets rid of the artefacts since the actual shape is not there.
            img_new = Image.new(shape_img.mode,shape_img.size, None)
            img_new.paste(img, box=pic_area, mask=mask)
            img = img_new

        if img.size != size:
            _LOGGER.warning(f"{self.id} did not yield the correct size. Fitting to ensure correct size")
            img = ImageOps.fit(img,size)

        self._imgData = img

        return self.imgData

    async def _open_picture_file(self, image_path : Union[str,Path]):
        """
        Opens the image at image path and sets it as the _pictureImage attribute
        Threadsafe, generally not needed, as it is done in the generator when required (which should be threadsafe) 
        Blocks `picture.generate()` from running until the picture is opened.
        
        Parameters
        ----------
        image_path : _type_
            Image path

        """
        async with self._generatorLock:
            self._pictureImage = None
            img = await tools.open_image_file_threadsafe(image_path)
            self._pictureImage = img
        return

BADGE_LOCATIONS = Literal[None, "UR", "UL", "LL", "LR"]
"Type hint for possible badge locations"

class Icon(ImageElement):
    """
    An icon, built from an mdi icon or an image. Optionally add a badge. Takes all options from Element too.
    If an image file is supplied, it is automatically converted to the same sizing as mdi icons use, so the icon margins are constant.
    
    Parameters
    ----------
    icon : Optional[Union[mdiType,str]], optional
        The icon to use, by default DEFAULT_ICON
        Accepts mdi icons (by specifying an icon with mdi:), or icon files. Also accepts a number of shorthands which are hopefully documented somewhere
    icon_color : Union[ColorType,bool], optional
        The icon color, by default DEFAULT_FOREGROUND_COLOR
    background_color : Optional[ColorType], optional
        background color, by default None
    background_shape : IMPLEMENTED_ICON_SHAPES_HINT, optional
        Background shapes, see the documentation for valid values, by default None
        This shape takes on the background color by default, unless otherwise defined in the shape settings.
    shape_settings : dict, optional
        Settings to apply to the shape, by default {}
    isInverted : bool, optional
        _description_, by default False
    invert_icon : bool, optional
        Inverts only the icon, by default False
    mirrored : bool, optional
        Mirror the icon, by default False
    rotation_angle : Union[int,float], optional
        angle in degrees to rotate the icon, by default 0
    force_aspect : bool, optional
        when using an image file, this will resize and crop the image have a similar sizing to MDI icons, by default True
    badge_icon : Optional[Union[mdiType,str]], optional
        mdi icon to overlay on the icon; Set to none to omit, by default None
    badge_settings : dict, optional
        _description_, by default {}
    badge_location : Optional[BadgeLocationType], optional
        settings for the badge. See attribute description for keys, by default None
    badge_color : _type_, optional
        Color of the badge icon, by default None
    badge_size : Optional[float], optional
        Size of the badge icon, relative to icon itself, by default None
    badge_offset : int, optional
        amount of pixels to offset the badge from the borders of the element, by default 0
    """

    @property
    def _emulator_icon(cls): return "mdi:drawing-box"

    def __init__(self, icon: Optional[Union[mdiType,str]] = DEFAULT_ICON, icon_color:Union[ColorType,bool] = DEFAULT_FOREGROUND_COLOR, background_color : Optional[ColorType]=None, background_shape:IMPLEMENTED_ICON_SHAPES_HINT = None, shape_settings : dict = {},
                isInverted : bool = False, invert_icon : bool = False,
                mirrored:bool=False, rotation_angle: Union[int,float] = 0, force_aspect = True, 
                badge_icon : Optional[Union[mdiType,str]] = None, badge_settings : dict = {}, badge_location : Optional[BadgeLocationType] = None, badge_color = None, badge_size : Optional[float] = None, badge_offset : int = 0, **kwargs):
    
        super().__init__(isInverted=isInverted, **kwargs)
        
        if icon != None: ##This allows elements that have a seperate setter to not throw the error
            self.icon = icon
        
        self._iconData = (None, None)
        self.icon_color = icon_color
        self.background_shape = background_shape
        self.background_color = background_color
        self.shape_settings = shape_settings
        self.rotation = rotation_angle

        ###Boolean settings
        self.mirrored = mirrored
        self.invert_icon = invert_icon
        self.force_aspect = force_aspect
        self._fileError = False
        self.__feedbackImg = None

        ###Badge settings
        self.badge_icon = badge_icon
        self.badge_settings = badge_settings
        self.badge_color = badge_color
        self.badge_location = badge_location
        self.badge_size = badge_size
        self.badge_offset = badge_offset

        self._iconColorValue = None
        "Tuple with the color channel values as determined from the value of self.icon_color in concurrence with the other settings."

        for param in kwargs:
            if "alert" in param:
                _LOGGER.warning(f"found leftover alert in icon, change to badge. Entity is {kwargs.get('entity', 'Not defined')}")

    #region
    # -------------------------- Icon Element properties ------------------------- #      
    @property
    def icon(self) -> Optional[Union[str,Image.Image]]:
        """
        The current icon. Can be set to a str (either an mdi icon or image file), or a PIL image instance directly.
        If the latter, the image will still be treated as an image file i.e. any icon settings etc. are applied to it regardless (This does also mean you don't need to worry about sizing, as that is also taken care of).
        Can also be set to None for no icon.
        """
        return self._icon

    @icon.setter
    def icon(self, value:Union[str,Image.Image]):
        self._icon_setter("_icon", value, allow_none=True)

    def _icon_setter(self, attribute : str, value : str, only_mdi : bool = False, allow_none = False):
        """
        Quickhand function to set icon attributes.

        Parameters
        ----------
        attribute : str
            the attribute to set
        value : str
            the value of the attribute
        only_mdi : bool, optional
            Only accept values corresponding to mdi icons, by default False
        allow_none : bool, optional
            Allow the icon to be set to None, by default False
        """

        if value == None and allow_none:
            pass
        
        elif isinstance(value,(Path,Image.Image)):
            pass

        elif mdi.is_mdi(value):
            pass
        else:
            if only_mdi:
                msg = f"{value} is not recognised as a valid mdi icon type"
                _LOGGER.error(ValueError(msg))
                return
            else:
                ##Test if the icon file exists here. Check the generator maybe?
                pass

        if attribute[:2] == "__":
            eCls = self.__class__.__name__
            attribute = f"_{eCls}{attribute}"
        setattr(self,attribute, value)

    @property
    def iconData(self) -> tuple:
        "Returns data related to the icon. For mdi icon, it's (unicode, hexcode) or (False, False) if it could not be found. For an image, it is (pathToImage,True/False) depending on if it was found"
        return self._iconData

    @property
    def feedbackImg(self) -> Optional[Image.Image]:
        "Pillow Image that will be shown when interacting with the icon."
        return self.__feedbackImg

    @property
    def rotation(self) -> Union[int,float]:
        "The rotation of the icon in degrees. Positive for counterclockwise, negative for clockwise."
        return self._rotation
    
    @rotation.setter
    def rotation(self, value:Union[int,float]):
        self._rotation = value

    @colorproperty
    def icon_color(self) -> Union[ColorType,bool]:
        """
        Color of the icon, defaults to True, so you need to specify this as false to make images keep their color.
        If a boolean and an mdi icon, the color is set automatically for best contrast. 
        If an image file, a boolean of True will fill the image with the best chosen color, and if False, will use the original image.
        Otherwise will use the provided value as color.
        """
        return self._icon_color

    @property
    def shape_settings(self) -> dict:
        """
        Settings for the background shape. Advanced setting, generally best to leave it as an emtpy dict. Stuff may not work as intended as I cannot test everything.
        Optional arguments are required using ADVANCED, except for icon_coords (icon will default to being centered)
        Usage:
            method[Optional] (str): ImageDraw method to call. Mainly usefull when using background_shape ADVANCED
            icon_size[Optional] (str or int): size of the icon
            icon_coords[Optional] (tuple): center coordinates of the icon when using an mdi icon, or the coordinates of the upper left corner if using an image
            drawArgs (dict): dict with arguments to be passed to the ImageDraw function. If background_shape is an implemented shape, omitting arguments will means default values will be used.
        """
        return self._shape_settings.copy()
    
    @shape_settings.setter
    def shape_settings(self, value:dict):
        value = value.copy()
        self._shape_settings = value

    # ---------------------------- Boolean properties ---------------------------- #
    @property
    def mirrored(self) -> bool:
        """Is the icon mirrored?"""
        return self._mirrored
    
    @mirrored.setter
    def mirrored(self,value:bool):
        self._mirrored = value

    @property
    def invert_icon(self) -> bool:
        """
        True if the icon only is inverted. This works seperately from isInverted, which inverts an entire element, and is applicable to all elements. 
        invert_icon is only applicable for icons, mainly to provide a way to give images which do not have a solid color (like filled meteocons) more contrast without being confined to a single colored icon.
        """
        return self._invert_icon
    
    @invert_icon.setter
    def invert_icon(self, value:bool):
        self._invert_icon = value

    @property
    def force_aspect(self) -> bool:
        """Is the icon forceable squared?"""
        return self._force_aspect
    
    @force_aspect.setter
    def force_aspect(self,value:bool):
        self._force_aspect = value

    @property
    def fileError(self) -> bool:
        """Returns true if the currently set value for icon did not return a valid icon or image"""
        return self._fileError

    # ----------------------------- Badge properties ----------------------------- #
    @property
    def badge_icon(self) -> Optional[mdiType]:
        """The current icon of the badge. Must be None, an mdi icon or a PIL image instance."""
        return self._badge_icon

    @badge_icon.setter
    def badge_icon(self, value: Optional[str]):
        if value != None and not isinstance(value, (str, Image.Image)):
            _LOGGER.error(f"{value} cannot be used as a badge icon, setting to error icon.")
            self._badge_icon = MISSING_ICON
        else:
            self._badge_icon = value

    @property
    def badge_settings(self) -> dict:
        """
        Dict with settings to apply to the badge
        """
        d = self._badge_settings.copy()
        d.setdefault("icon_color", self.badge_color)
        return d
    
    @badge_settings.setter
    def badge_settings(self, value : dict):
        value = value.copy()
        for key in value:
            if key not in ALLOWED_BADGE_SETTINGS: 
                _LOGGER.warning(f"{key} is not an allowed badge setting")
                value.pop(key)
        self._badge_settings = value

    @property
    def badge_location(self) -> BadgeLocationType:
        """
        The location of the badge. 
        Can be Can be one of UR, LR, UL or LL (Upper Right, Lower Right, Upper Left, Lower Left). Also accepts the fully written strings, but will be set to  the abbreviated location.
        """
        return self._badge_location
    
    @badge_location.setter
    def badge_location(self, value: BadgeLocationType):
        if value == None:
            self._badge_location = value
            return
        
        valid_locs = ["UR", "LR", "UL", "LL"]
        rem =  [" ", "-", "_"] ##Possible string parts to remove
        valid_strings = ["upperright", "lowerright", "upperleft", "lowerleft"]
        if value.upper() in valid_locs:
            self._badge_location = value
        else:
            input = value
            for char in rem:
                value = value.replace(char,"")
            value = value.lower()

            if value in valid_strings:
                loc = valid_locs[valid_strings.index(value)]
                _LOGGER.verbose(f"Badge location provided as {input}, set as {loc}")
                self._badge_location = loc
            else:
                _LOGGER.error(f"Unable to decode {input} as a valid badge location, location set to {DEFAULT_BADGE_LOCATION}. Use one of {valid_locs} as shorthand or {valid_strings} (where spaces, dashes and underscores are removed and input is converted to lowercase)")
                self._badge_location = DEFAULT_BADGE_LOCATION

    @property
    def badge_size(self) -> Union[float,None]:
        "Size of the badge relative to the parent icon. Must be between 0 and 1. If set to a percantage, will be converted to such a value."
        return self._badge_size

    @badge_size.setter
    def badge_size(self, value:Union[float,str,None]):
        input=value
        if value == None:
            self._badge_size = value
            return
        
        if type(value) == str:
            if value[-1] == "%":
                perc = float(value.replace("%",""))
                value = perc/100
            else:
                _LOGGER.error(f"Could not convert badge_size value {input} to a percentage")
                return
        
        if value < 0 or value > 1:
            _LOGGER.error(f"badge_size {input} should be between 0 and 100, or 0% to 100%")
        else:
            self._badge_size = value

    @property
    def badge_offset(self) -> int:
        """Badge Offset from the edges of the icon in pixels"""
        return self._badge_offset
    
    @badge_offset.setter
    def badge_offset(self, value:int):
        if value < 0:
            _LOGGER.error("Offset must be 0 or larger")
        else:
            self._badge_offset = value
    #endregion
    
    def generator(self, area=None, skipNonLayoutGen=False):
                
        if area == None: #Added this if case to the original code;
            area = self.area
        else:
            self._area = area

        if area == None:
            _LOGGER.verbose(f"Element {self} has no area asigned. Returning")
            return
        
        [(x, y), (w, h)] = area
        draw_size = min(w, h)

        if draw_size <= 0:
            _LOGGER.warning(f"{self}: Image size but be larger than 0, cannot draw in area {area}")
            return

        icon_size = draw_size
        draw_size = (draw_size, draw_size)

        layoutBackgroundColor = self.parentBackgroundColor
        imgMode = self.parentPSSMScreen.imgMode
        
        drawImg = False

        if self.background_shape != None:
            loadedImg = Image.new(imgMode, (draw_size[0],draw_size[1]),None)
            img_background = Style.get_color(layoutBackgroundColor, imgMode)
            ##Currently only implemented for L/LA colortype
            if self.background_color != True:
                shape_color = Style.get_color(self.background_color, imgMode)
            else: 
                shape_color = Style.contrast_color(layoutBackgroundColor,imgMode)
                if "L" in imgMode:
                    if shape_color[0] > 110 and shape_color[0] < 175: shape_color = Style.get_color("white",imgMode)

            icon_bg = shape_color
            if self.background_color == None:
                icon_bg = img_background
                ##Default to white if the shape color and background color do not contrast enough

            shape = self.background_shape.strip().lower().replace(" ","_")
            if self.background_shape == "ADVANCED":
                method = self.shape_settings["method"]
                icon_size = self.shape_settings.get("icon_size",1)
                _LOGGER.debug(f"Drawing advanced shape {method}")
                try:
                    (loadedImg, drawImg) = DrawShapes.draw_advanced(loadedImg, method, 
                                                drawArgs=self.shape_settings.get("drawArgs",{}), paste=False)
                except FuncExceptions as exce:
                    _LOGGER.error(f"Error drawing advanced shape {method}: {exce}")
            
            elif shape in IMPLEMENTED_ICON_SHAPES:
                drawFunc, relSize = IMPLEMENTED_ICON_SHAPES[shape]
                icon_size = self.shape_settings.get("icon_size",floor(min(draw_size)*relSize))
                
                drawArgs = self.shape_settings.get("drawArgs",{})
                if not "fill" in drawArgs:
                    drawArgs["fill"] = shape_color
                (loadedImg, drawImg) = drawFunc(loadedImg, drawArgs=drawArgs, paste=False)
            else:
                ##This should not happen since the check happens (or will happen) when setting the value
                _LOGGER.error(f"{self.background_shape} is not a recognised valid value for background shape.")
        else:
            if self.background_color != None:
                img_background = Style.get_color(self.background_color, imgMode)
                icon_bg = img_background
                loadedImg = Image.new(imgMode, (draw_size[0],draw_size[1]),img_background)
            elif layoutBackgroundColor != None:
                img_background = layoutBackgroundColor
                icon_bg = img_background
                loadedImg = Image.new(imgMode, (draw_size[0],draw_size[1]),None)
            else:
                img_background = None
                icon_bg = self.parentPSSMScreen.device.defaultColor
                loadedImg = Image.new(imgMode, (draw_size[0],draw_size[1]),None)

            img_background = Style.get_color(img_background,imgMode)

        self._fileError = False
        _LOGGER.debug(f"Icon is {self.icon}, path is {self._iconData}")

        if self.icon != None and mdi.is_mdi(self.icon):
            icon = self.icon
            _LOGGER.verbose(f"Parsing mdi icon {icon}")
            mdistr = mdi.parse_MDI_Icon(icon)
            
            if isinstance(self.icon_color, bool):
                icon_color_value = Style.contrast_color(icon_bg, imgMode)
            else:
                icon_color_value = Style.get_color(self.icon_color,imgMode)

            if mdistr[0]: 
                self._iconData = mdistr

                if drawImg:
                    ##drawImg from drawShapes is still in the higher resolution, so the icon size and coordinates are scaled
                    dw_size = drawImg.im.size
                    scale = dw_size[0]/draw_size[0]
                    dr_im = drawImg._image
                    icon_size = int(icon_size*scale)
                    if "icon_coords" in self.shape_settings:
                        coords = self.shape_settings["icon_coords"]
                        icon_coords = (int(coords[0]*scale),int(coords[1]*scale))
                        loadedImg = mdi.draw_mdi_icon(dr_im, self._iconData, icon_size=icon_size, icon_color=icon_color_value, iconDraw= drawImg, icon_coords=icon_coords)
                    else:
                        loadedImg = mdi.draw_mdi_icon(dr_im, self._iconData, icon_size=icon_size, icon_color=icon_color_value, iconDraw = drawImg)
                    loadedImg = loadedImg.resize(draw_size,Image.Resampling.LANCZOS)
                else:
                    loadedImg = mdi.draw_mdi_icon(loadedImg, self._iconData, icon_color=icon_color_value)
                _LOGGER.debug(f"Drew icon {self.icon}")
            else:
                _LOGGER.error(f"Could not parse mdi file: {icon}")
                self._fileError = True
        elif self.icon != None:
            _LOGGER.debug(f"Getting image {self.icon} for icon element {self.id}")
            try:
                if isinstance(self.icon, Image.Image):
                    iconImg = self.icon
                    img = iconImg
                else:
                    self._iconData = self.icon
                    img = tools.parse_known_image_file(self.icon)
                    iconImg = Image.open(img)
            except FileNotFoundError:
                _LOGGER.warning(f"Image file {img} does not exist at path {self._iconData}")
                self._fileError = True
                icon_color_value = Style.contrast_color(icon_bg, imgMode)
            else:
                ##Convert it here already to prevent problems with pasting etc. Cause like this is is guaranteed to have an alpha channel
                if iconImg.mode != imgMode: iconImg = iconImg.convert(imgMode)
                ##MDI icons have a live area of 20dp, and padding of 2dp on both sides.
                ##So for resizing: grab min size of the loaded img, take that as square size
                ##Resize the icon. Size must be ~20/24 of the square (0.83); Image.thumbnail should make the image fit within the size
                ##Determine the origin of the square within the loaded img
                
                ##This way, any alpha channel around the icon is automatically removed
                iconImg = iconImg.crop(iconImg.getbbox())
                squareSize = icon_size
                liveArea = 20/24 ##The ratio of the area where icons are as defined by mdi design guide
                thumbSize = int(squareSize*liveArea)
                iconImg = ImageOps.contain(iconImg,(thumbSize,thumbSize))
                
                if self.icon_color:
                    if self.icon_color == True:
                        icon_color_value = Style.contrast_color(icon_bg, imgMode)
                    else:
                        icon_color_value = Style.get_color(self.icon_color,imgMode)
                    icondraw = ImageDraw.Draw(iconImg)
                    icondraw.bitmap((0,0),iconImg.getchannel("A"),icon_color_value)
                else:
                    ##This is set for the badge default later on, not applied to the image itself.
                    icon_color_value = Style.contrast_color(icon_bg, imgMode)
                
                if "icon_coords" in self.shape_settings:
                    iconOriging = self.shape_settings["icon_coords"]
                else:
                    iconOriging = (
                        int((draw_size[0]-iconImg.width)/2), 
                        int((draw_size[1]-iconImg.height)/2))
                _LOGGER.verbose(f"Pasting an icon image with size {iconImg.size} onto an image with size {loadedImg.size} onto origin {iconOriging}")
                if iconImg.mode == "RGBA" and loadedImg.mode == "RGBA":
                    loadedImg.alpha_composite(iconImg, iconOriging)
                elif "A" in iconImg.mode and not "A" in loadedImg.mode:
                    loadedImg.paste(iconImg,iconOriging, iconImg.getchannel("A"))
                else:
                    ##Did not find any during testing, but this may yield odd results? 
                    ## I had some moments where pasting an alpha image would mean the alpha channel would also be applied to the original image, i.e. remove its background 
                    loadedImg.paste(iconImg, iconOriging, iconImg)
        else:
            if isinstance(self.icon_color, bool):
                icon_color_value = Style.contrast_color(icon_bg, imgMode)
            else:
                icon_color_value = Style.get_color(self.icon_color,imgMode)
        self._iconColorValue = icon_color_value

        if self.fileError:
            ##Gotta test this one out too to check if the icon gets a seeable color
            _LOGGER.error(f"{self}: Could not find icon matching {self.icon}")
            self._iconData = mdi.parse_MDI_Icon(MISSING_ICON)
            loadedImg = Image.new(imgMode, (draw_size[0],draw_size[1]), None)
            loadedImg = mdi.draw_mdi_icon(loadedImg, MISSING_ICON)
            icon_color_value = Style.contrast_color(icon_bg, imgMode)
            drawImg = False

        #Mirror the image if required        
        if self.mirrored:
            loadedImg = ImageOps.mirror(loadedImg)
            drawImg = False

        #Rotate the image if the angle is not a multiple of 360
        ##I think I need to check this?
        if self.rotation % 360:
            loadedImg = loadedImg.rotate(self.rotation)
            drawImg = False

        if self.badge_icon != None:
            #badgeOpts = {"badge_color": "color", "badge_location": "location", "badge_size": "relSize", "badge_offset": "offset"}
            badgeDict = self.badge_settings #{"background_color": icon_bg}
            
            if "background_color" not in self.badge_settings: 
                if self.background_shape == None:
                    ##This should be ok, the color is the problem I suspect
                    badgeDict["background_color"] = None
                else:
                    badgeDict["background_color"] = shape_color

            badgeDict.setdefault("icon_color", self.badge_color)

            if self.badge_location != None:
                badgeDict.setdefault("location", self.badge_location)

            ##I think this needs to be rewritten for quite a bit since multiple badge properties are not taken into account
            _LOGGER.verbose(f"Badge dict is {badgeDict}")

            try:
                loadedImg = self.add_badge(loadedImg, parentIconSize=draw_size, **badgeDict)
            except:
                _LOGGER.error(f"{self} Could not add badge", exc_info=True)

        if self.invert_icon:
            _LOGGER.verbose(f"Inverting an icon")
            loadedImg = tools.invert_Image(loadedImg)
            drawImg = False

        self.__feedbackImg = None

        if self.show_feedback:
            self.__feedbackImg = self.generate_feedback_icon(loadedImg, img_background, (w,h))

        if self.background_color != None and self.background_shape == None:
            col = Style.get_color(self.background_color,imgMode)
        else:
            col = None
        loadedImg = ImageOps.pad(loadedImg,(w,h), color=col)

        if self.inverted:
            loadedImg = tools.invert_Image(loadedImg)

        self._imgData = loadedImg
        return self.imgData

    def add_badge(self, img : Image.Image, drawImg = False, parentIconSize=None,  background_color=None,
                        icon_color = None, relSize : float = 0.4, location=DEFAULT_BADGE_LOCATION, offset : tuple =(0,0)) -> Image.Image:
        """
        Adds a badge to the icon.
        args:
            img: PILLOW image object to add the badge to
            colorMode (str): colortype of the image
            background_color (str) background color of the badge. Set to none for no circle. Set to (0,0) to cut a transparent circle out of the image (if possible).
            parenIconSize: the size of the parent icon
            icon_color (str): color of the badge icon
            relSize (float): the size of the badge relative to the parent icon
            location (str): Location of the badge. Can be one of UR, LR, UL or LL (Upper Right, Lower Right, Upper Left, Lower Left) 
            offset: badge offset (x,y) from the bounds of the image
        """

        colorMode = img.mode
        size = img.size

        if parentIconSize == None: parentIconSize = img.size
        circle_diameter = round((min(parentIconSize)*relSize))
        marginx = 0 if circle_diameter*0.5 + parentIconSize[0]*0.5 > img.size[0]*0.5 else round(0.5*(img.size[0] - parentIconSize[0] - circle_diameter))        
        marginy = 0 if circle_diameter*0.5 + parentIconSize[1]*0.5 > img.size[1]*0.5 else 0.5*((img.size[1] - parentIconSize[1] - circle_diameter)) 
        margin = (marginx, marginy)

        if relSize > 1:
            _LOGGER.warning(f"Icon {self.badge_icon} for {self} has relative size {relSize} > 1, defaulting to 0.5")
            relSize = 0.5

        circle_diameter = round((min(size)*relSize))

        if location == "LL":
            (x0, y0) = (margin[0]+offset[0], size[1]-circle_diameter-margin[1] - offset[1])
            (x1, y1) = (margin[0] + circle_diameter + offset[0], size[1]-margin[1] - offset[1])
        elif location == "UL":
            (x0, y0) = (margin[0] + offset[0], margin[1] + offset[1])
            (x1, y1) = (margin[0] + circle_diameter + offset[0], margin[1]+circle_diameter + offset[1])
        elif location == "UR":
            (x0, y0) = (size[0]-circle_diameter-margin[0] - offset[0], margin[1] + offset[1])
            (x1, y1) = (size[0] - margin[0] - offset[0], circle_diameter + margin[1] + offset[1])
        else:
            (x0, y0) = (size[0]-circle_diameter-margin[0] - offset[0], size[1]-circle_diameter-margin[1] - offset[1])
            (x1, y1) = (size[0]-margin[0] - offset[0], size[1]-margin[1] - offset[1])
        x0 = int(x0)
        y0 = int(y0)

        circle_coo = [(x0,y0),(x1,y1)]
        _LOGGER.verbose(f"Drawing circle size {circle_diameter} at coordinates {location}: {circle_coo} on image with size {size}, margin {margin} ({getattr(self, 'entity_id', 'no entity')})")
        if background_color != None:
            background_color_tuple = Style.get_color(background_color,colorMode)
        else:
            background_color_tuple = Style.get_color(None, colorMode)

        if icon_color == None: icon_color = self.icon_color          
        relSize = floor(IMPLEMENTED_ICON_SHAPES["circle"][1]*DrawShapes.MINRESOLUTION)
        
        badgeImg = Image.new(img.mode,(DrawShapes.MINRESOLUTION, DrawShapes.MINRESOLUTION), None)
        

        (badgeImg, drawImg) = DrawShapes.draw_circle(badgeImg, drawArgs={"fill": background_color_tuple}, paste=False)

        if mdi.is_mdi(self.badge_icon):
            badgeImg = mdi.draw_mdi_icon(badgeImg,self.badge_icon, icon_size=relSize, icon_color=icon_color)
        else:
            col = Style.get_color(icon_color,"RGBA")
            if isinstance(self.badge_icon, Image.Image):
                badge = self.badge_icon.copy()
            else:
                badge = tools.parse_known_image_file(self.badge_icon)
            
            newImg = mdi.make_mdi_icon(badge, relSize, col)
            pasteCoords = (int((badgeImg.width-relSize)/2),)*2
            badgeImg.alpha_composite(newImg,pasteCoords)

        badgeImg = badgeImg.resize((circle_diameter, circle_diameter))
        
        if "A" in img.mode: ##This take care of having a transparent circle cutout of the sourceimage, regardless of whether it's RGBA or not.
            if background_color == None or background_color_tuple[-1] == 0:
                (maskImg, _) = DrawShapes.draw_circle(badgeImg, drawArgs={"fill": "white"}, paste=False)
                maskImg = maskImg.resize((circle_diameter, circle_diameter))
                img.paste(Image.new(img.mode,maskImg.size,None),(x0,y0),mask=maskImg)

        if img.mode == "RGBA":
            img.alpha_composite(badgeImg, (x0,y0))
        else:
            img.paste(badgeImg,(x0,y0),mask=badgeImg)
        
        return img

    def generate_feedback_icon(self, img : Image.Image, background_color : ColorType, size : tuple[wType,hType]) -> Optional[Image.Image]:
        """
        Generates a feedback icon to show when interacting with the element, if the icon has a background shape.

        Parameters
        ----------
        img : Image.Image
            The image to adapt the feedback image from
        background_color : ColorType
            The background color of the icon
        size : tuple[int,int]
            The size to adapt from

        Returns
        -------
        Optional[Image.Image]
            The feedback image object, or None if the background shape is None
        """

        if self.background_shape == None:
            return None

        imgMode = img.mode
        (w,h) = size
        _LOGGER.verbose(f"Saving inverted {self.icon} icon onto image with colormode {imgMode}")
        
        if isinstance(background_color,tuple): 
            inv_background = background_color[0]
        else:
            inv_background = background_color
        invertedImg = Image.new(imgMode,img.size, inv_background)

        red = 0.85  ##Size of the feedback icon relative to the original one
        inv = img.copy().resize((int(img.width*red),int(img.height*red)),Image.Resampling.LANCZOS)
        inv = tools.invert_Image(inv)
        pasteCoords = (floor((w-img.width)/2),floor((h-img.height)/2))

        center = (floor((img.width)/2),floor((img.height)/2))
        pasteCoords = (floor(center[0]-(inv.width/2)),floor(center[1]-(inv.height/2)))

        invertedImg.paste(Image.new(imgMode,(img.width,img.height),
                                    tools.invert_Color(inv_background, imgMode)), (0,0), mask=img.getchannel("A"))
        if imgMode == "RGBA":
            invertedImg.alpha_composite(inv,pasteCoords)
        else:
            invertedImg.paste(inv,pasteCoords,mask=inv)
        invertedImg = ImageOps.pad(invertedImg,(w,h))

        if not self.inverted:
            invertedImg = tools.invert_Image(invertedImg)
        
        return invertedImg

    async def feedback_function(self):
        "Instead of inverting, can show a different imagefile in the area of the icon. Slightly slower than the default function."
        
        if self.feedbackImg == None: ##show_feedback is already called in the screen dispatch
            self._feedbackTask = asyncio.create_task(self.parentPSSMScreen.async_invert_element(self,self.feedback_duration))
        else:
            self._feedbackTask = asyncio.create_task(self.icon_feedback())
        await self.feedbackTask
        return
    
    async def icon_feedback(self):

        ##Originally did this by directly printing to the device, but simplePrint and just changing the imgdata is faster (in terms of code lines at least) and has easier checks/altering for e.g. the background
        self.parentPSSMScreen.simple_print_element(self, skipGen=self.feedbackImg)

        await asyncio.sleep(self.feedback_duration)

        if self.isUpdating or self.isGenerating:
            return

        self.parentPSSMScreen.simple_print_element(self, skipGen=True)
        return

#endregion

class Line(Element):
    """
    Draws a simple line

    Parameters
    ----------
    line_color : ColorType, optional
        Color of the line, by default DEFAULT_FOREGROUND_COLOR
    width : PSSMdimension, optional
        The width of the line, by default 1
    orientation : Literal[&quot;horizontal&quot;,&quot;vertical&quot;,&quot;diagonal1&quot;, &quot;diagonal2&quot;], optional
        Orientation of the line, by default "horizontal"
    alignment : Union[Literal[&quot;center&quot;,&quot;top&quot;,&quot;bottom&quot;, &quot;left&quot;, &quot;right&quot;], PSSMdimension], optional
        Alignment of the line, by default "center"
    """

    @property
    def _emulator_icon(cls): return "mdi:ruler"

    def __init__(self, line_color: ColorType =DEFAULT_FOREGROUND_COLOR, width: PSSMdimension = 1, orientation : Literal["horizontal","vertical","diagonal1", "diagonal2"]="horizontal", 
                 alignment : Union[Literal["center","top","bottom", "left", "right"], PSSMdimension]="center", **kwargs):

        super().__init__(**kwargs)
        self.line_color = line_color
        self.width = width
        self.orientation = orientation
        self.alignment = alignment

    #region
    @colorproperty
    def line_color(self) -> ColorType:
        "The color of the line"
        return self._line_color

    @property
    def width(self) -> PSSMdimension:
        "Width of the line"
        return self.__width
    
    @width.setter
    def width(self, value):
        self._dimension_setter("__width",value)

    @property
    def orientation(self) -> Literal["horizontal","vertical","diagonal1", "diagonal2"]:
        "Line orientation. Diagonal1 goes from top right to bottom left, diagonal2 goes from bottom right to top left"
        return self.__orientation
    
    @orientation.setter
    def orientation(self,value: Literal["horizontal","vertical","diagonal1", "diagonal2"]):
        if value not in ["horizontal","vertical","diagonal1", "diagonal2"]:
            msg = f'Line orientation must be one of ["horizontal","vertical","diagonal1", "diagonal2"], {value} is not valid'
            _LOGGER.error(ValueError(msg))
            return
        
        self.__orientation = value
    
    @property
    def alignment(self) -> Union[Literal["center","top","bottom", "left", "right"], PSSMdimension]:
        """
        Alignment of the line relative to it's area. top/bottom and left/right are adjusted respectively for the orientation.
        Has no affect when orientation is diagonal
        """
        val = self.__alignment 
        if val == "center" or "diagonal" in self.orientation or val not in ["center","top","bottom", "left", "right"]:
            return val
        else:
            if self.orientation == "horizontal":
                if val == "left": val = "top"
                if val == "right": val = "bottom"
            else:
                if val == "top": val = "left"
                if val == "bottom": val = "right"
            return val
    
    @alignment.setter
    def alignment(self, value):
        if value not in ["center","top","bottom", "left", "right"]:
            if isinstance(tools.is_valid_dimension(value), bool):
                self.__alignment = value
            else:
                msg = f'Line alignment must be one of ["center","top","bottom", "left", "right"], {value} is not valid'
                _LOGGER.error(ValueError(msg))
            return
        self.__alignment : Literal["center","top","bottom", "left", "right"] = value
    #endregion

    def generator(self, area, skipNonLayoutGen=False):
        if area != None:
            area = self._area

        if area == None:
            return
        
        (x, y), (w, h) = area
        self._area = area
        colorMode = self.parentPSSMScreen.imgMode

        line_w = self._convert_dimension(self.width)

        if self.orientation == "horizontal":

            if self.alignment == "center":
                line_y = round(h/2)
            elif self.alignment == "bottom":
                line_y = h - round(line_w/2)
            elif self.alignment == "top":
                line_y = 0 + round(line_w/2)
            else:
                line_y = self._convert_dimension(self.alignment)

            coo = [(0, line_y), (w, line_y)]
        elif self.orientation == "vertical":
            if self.alignment == "center":
                line_x = round(w/2)
            elif self.alignment == "right":
                line_x = w - round(line_w/2)
            elif self.alignment == "left":
                line_x = 0 + round(line_w/2)
            else:
                line_x = self._convert_dimension(self.alignment)

            coo = [(line_x, 0), (line_x, h)]

        elif self.orientation == "diagonal1":
            coo = [(0, 0), (w, h)]
        else:               # Assuming diagonal2
            coo = [(0, h),(w,0)]

        rectangle = Image.new(
            colorMode,
            (w, h),
            color=Style.get_color(self.background_color, colorMode)
        )
        draw = ImageDraw.Draw(rectangle)
        draw.line(
            coo,
            fill=Style.get_color(self.line_color, colorMode),
            width=line_w
        )
        self._imgData = rectangle
        return self.imgData
    
    def update(self, updateAttributes={}, skipGen=False, forceGen = False, skipPrint=False, reprintOnTop=False, updated = False):
        upd = super().update(updateAttributes, skipGen, forceGen, skipPrint, reprintOnTop, updated)
        return upd


class _BaseSlider(Element):
    """
    Base class for sliders, provides necessary properties and some functions.
    Can only be used as a parent class, not as an element on its own.

    Parameters
    ----------
    orientation : str, optional
        Slider orientation, horizontal or vertical. by default "horizontal"
    position : int, optional
        starting position of the slider, by default 50
    minimum : float, optional
        minimum value the slider can take, by default 0
    maximum : float, optional
        maximum value the slider can take, by default 100
    value_type : int, float
        The type to return when calling Slider.Value, handy when requiring integers. Defaults to float
    interactive : bool, optional
        whether the slider updates its position when it is clicked, by default True
    tap_action : Callable[elt, coords], optional
        function to call when tapping the slider, by default None
    """

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return Element.action_shorthands | {"set-position": "_set_position_action"}

    def __init__(self, orientation : Literal["horizontal","vertical"], position : Union[int,float]=None, 
                minimum : float = 0, maximum : float = 100, value_type : Union[type[float],type[int],Literal["int","float"]] = float, 
                show_feedback : bool = False, interactive : bool = True, tap_action=None, on_position_set: dict = None,
                **kwargs):

        super().__init__(tap_action=tap_action, show_feedback=show_feedback, **kwargs)

        self.interactive=interactive
        self.orientation = orientation
        self.minimum=minimum
        self.maximum = maximum
        if not position:
            position = self.minimum
        self.position = position
        self.value_type = value_type

        self.on_position_set_data = {}
        self.on_position_set_map = {}
        self.on_position_set = on_position_set

    #region
    @property
    def orientation(self) -> Literal["horizontal","vertical"]:
        "The orientation of the slider. Horizontal or Vertical."
        return self.__orientation
    
    @orientation.setter
    def orientation(self, value:str):
        if value.lower() not in ["horizontal", "vertical","hor","ver"]:
            msg = f"Slider orientation must be hor(izontal) or ver(tical). {value} is not allower"
            _LOGGER.exception(msg,exc_info=TypeError(msg))
        else:
            if "hor" in value.lower():
                self.__orientation = "horizontal"
            else:
                self.__orientation = "vertical"

    @property
    def position(self) -> Union[int,float]:
        "The position of the slider within the defined value range"
        return self._position
    
    @position.setter
    def position(self, value:Union[int,float]):
        self._position = value

    @property
    def value(self) -> Union[int,float]:
        "Synonym for position slider position"
        return self._position

    @property
    def minimum(self) -> float:
        "The lowest possible value the slider can take."
        return self.__min
    
    @minimum.setter
    def minimum(self,value : float):
        self.__min = value

    @property
    def maximum(self) -> float:
        "The highest possible value the slider can take"
        return self.__max
    
    @maximum.setter
    def maximum(self, value:float):
        self.__max = value
        
    @property
    def value_type(self) -> Union[type[float],type[int]]:
        return self.__value_type
    
    @value_type.setter
    def value_type(self, value: Union[type[float],type[int],Literal["int","float"]]):
        if isinstance(value,str):
            value = eval(value)
        
        if value not in [int,float]:
            _LOGGER.exception(f"value_type must be int or float, not {value}",exc_info=TypeError("Not float or integer type"))
            return
        else:
            self.__value_type = value

    @property
    def valueRange(self) -> tuple[Union[int,float],Union[int,float]]:
        "The range of the slider, as tuple with (min,max)."
        return (self.minimum, self.maximum)
    
    @property
    def lineCoords(self) -> list[tuple,tuple]:
        """ The current coordinates (min,max) of the line. Set by the generator."""
        return self._lineCoords
    
    @property
    def interactive(self) -> bool:
        "If true, clicking on the slider will update the position to that place."
        return self.__interactive
    
    @interactive.setter
    def interactive(self, value:bool):
        if not isinstance(value, bool):
            msg = "interactive must be boolean"
            _LOGGER.exception(msg, TypeError(msg))
        else:
            self.__interactive = value

    @elementaction
    def tap_action(self) -> InteractionFunctionType:
        """
        Slider tap_action. First updates the slider position, then calls the set tap_action.
        tap_action can be set by changing tap_action without it interfering with the slider update (I think).
        Use Slider._tap_action to access the actual function after setting.
        """
        return self.__tap_action

    @elementaction
    def on_position_set(self) -> Callable[["_BaseSlider",Union[float,int]],Any]:
        "Function that is called whenever the slider's position changes. Passes the element and the new position."
        return self._on_position_set

    #endregion

    async def __tap_action(self, elt, coords, **kwargs):
        if self.interactive:
            await self._slider_interact(elt,coords)
            kwargs.update(self.tap_action_kwargs)
        
        if self._tap_action == None:
            return
        await tools.wrap_to_coroutine(self._tap_action,elt,coords, **kwargs)

    async def _slider_interact(self, elt, coords):
        """Function that handles the slider being clicked on. Performs logic checks and then executes onTap"""

        rel_touch = self._get_touch_position(coords)
        _LOGGER.verbose(f"Slider position set to {rel_touch}")

        await self.async_set_position(rel_touch)

    async def async_set_position(self, new_position, *args):
        if new_position == self.position:
            return
        
        if self.on_position_set:
            task = tools.wrap_to_coroutine(self.on_position_set, self, new_position)
        else:
            task = None

        if hasattr(self,"_fast_position_update") and not self.parentPSSMScreen.popupsOnTop:
            await asyncio.to_thread(
                self._fast_position_update, new_position)
        elif hasattr(self,"_fast_position_update"):    
            for popup in self.parentPSSMScreen.popupsOnTop:
                if tools.get_rectangles_intersection(self.area,popup.area) or popup.blur_background:
                    self.position = new_position
                    asyncio.create_task(self.async_update(updated=True))
                    if task: asyncio.create_task(task)
                    return
            await asyncio.to_thread(
                self._fast_position_update, new_position)
        else:
            self.position = new_position
            asyncio.create_task(self.async_update(updated=True))
        
        if task: asyncio.create_task(task)
        return

    def set_position(self, new_position):
        self.parentPSSMScreen.mainLoop.create_task(self.async_set_position(new_position))

    def _get_touch_position(self, coords):
        (x, y), (w, h) = self.area
        if self.orientation == "horizontal":
            ##This should map every 1 pixel to a amount of value
            t = coords[0] - x - self.lineCoords[0][0]
            rangeMap = (self.valueRange[1] - self.valueRange[0])/(self.lineCoords[1][0] - self.lineCoords[0][0])
            pos = t*rangeMap + self.valueRange[0]

        elif self.orientation == "vertical":
            ##Breakpoint since vertical sliders still need testing
            t = self.lineCoords[1][1] - (coords[1] - y)
            rangeMap = (self.valueRange[1] - self.valueRange[0])/(self.lineCoords[1][1] - self.lineCoords[0][1])
            pos = t*rangeMap + self.valueRange[0]

        rel_touch = pos
        if rel_touch < self.valueRange[0]:
            rel_touch = self.valueRange[0]
        elif rel_touch > self.valueRange[1]:
            rel_touch = self.valueRange[1]
        
        return rel_touch

    @elementactionwrapper.method
    async def _set_position_action(self, new_position):
        "Set position function that can be used as a tap_action (so long as new_position is defined as a keyword)"
        asyncio.create_task(self.async_set_position(new_position=new_position))

CheckStateDict = TypedDict("CheckStateDict", {'True': dict, 'False': dict})

class _BoolElement(Element):
    """
    Building Block for elements that can be set to a true or false state (i.e. checkboxes).

    Parameters
    ----------
    state : bool, optional
        Initial state of the element, by default False
    interactive : bool, optional
        If true, the element's state will toggle when tapping it, by default True
    on_set : Callable[[&quot;CheckElement&quot;, bool],Any], optional
        Function to call when the element state is changed, by default None
    state_attributes : dict[True : dict, False : dict], optional
        When calling set_state, these attributes will be changed to the value in the corresponding state, by default {True:{},False: {}}
    """
    
    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return Element.action_shorthands | {"set-state": "set_state_async", "toggle-state": "async_toggle_state"}

    def __init__(self, state : bool = False, on_set : Callable[["_BoolElement", bool],Any] = None, state_attributes : CheckStateDict = {True:{},False: {}}, interactive : bool = True):
        self.__state = bool(state)
        self.interactive = interactive

        self._on_set_data = {}
        self._on_set_map = {}

        self.on_set = on_set
        self.state_attributes = state_attributes

        for param,value in self.state_attributes[str(self.state)].items():
            setattr(self,param,value)

    #region
    @property
    def state(self) -> bool:
        "True if the checkbutton is on/checked etc."
        return self.__state
    
    @property
    def interactive(self) -> bool:
        "If true, tapping the element will toggle its state"
        return self.__interactive
    
    @interactive.setter
    def interactive(self, value : bool):
        self.__interactive = bool(value)
    
    @property
    def state_attributes(self) -> CheckStateDict:
        "Element attributes to change depending on the checked state"
        return self.__state_attributes

    @state_attributes.setter
    def state_attributes(self, value : CheckStateDict):
        value : CheckStateDict
        val_dict = {"True": {}, "False": {}}
        
        for k, v in value.items():
            key = str(k).title()
            if key in val_dict:
                val_dict[key] = v

        self.__state_attributes = val_dict

    @Element.tap_action.getter
    def tap_action(self) -> list[Callable[["_BoolElement",tuple[int,int]],Any]]:
        """
        _BoolElement tap_action. Accessing this during runtime will have the element's state toggle. Access _tap_action to get the function without that happening during runtime.
        """
        if self.parentPSSMScreen.mainLoop.is_running() and self.interactive:
            asyncio.create_task(self.__check_element_interact())
        return self._tap_action

    @elementaction
    def on_set(self) -> Callable[["_BoolElement",bool],Any]:
        "Action that is called whenever the box is checked/unchecked. Passed are the element itself, and a boolean with the new state (True for checked, False for unchecked)"
        return self._on_set
    #endregion

    async def __check_element_interact(self):
        "Helper function to toggle the checkbox on interaction"
        await self.set_state_async()

    def set_state(self, new_state : Optional[bool] = None, *args):
        "Set the boolean state to `new_state`"
        asyncio.create_task(self.set_state_async(new_state))

    async def set_state_async(self, new_state : Optional[bool] = None, *args):
        """
        Set the new state of the element. on_set is processed first before updating the element, so be wary it does not block

        Parameters
        ----------
        new_state : Optional[bool], optional
            the new state to set. Leave as None to toggle the current state, by default None
        """
        if new_state == None:
            new_state = not self.state
        
        new_state = bool(new_state)
        if new_state != self.state:
            self.__state = new_state
            coro_list = []
            new_state = str(new_state)
            if self.on_set != None:
                coro_list.append(tools.wrap_to_coroutine(self.on_set,self,new_state, **self.on_set_kwargs))
            if self.onScreen:
                coro_list.append(self.async_update(updateAttributes=self.state_attributes[new_state],forceGen=True))
            
            await asyncio.gather(*coro_list)

    def toggle_state(self, *args):
        "Toggles the current state"
        asyncio.create_task(self.set_state_async())

    async def async_toggle_state(self, *args):
        "Toggles the current state"
        await self.set_state_async()


class _ElementSelect(Element):
    """
    Provides a base for a layout of connected elements which can be selected.
    This class wraps the provided layout into a selector. The instance that is returned should _NOT_ be used as the element.
    All the properties needed are put into the element's class (only for that element, not globally).
    
    Parameters
    ----------
    layout_element : Union[Layout, &quot;_ElementSelect&quot;]
        The layout that (presumably) holds the elements. This element will be wrapped into an ElementSelect  (i.e. attributes will be updated to provide the functionality needed)
    elements : dict[Literal[&quot;option&quot;], Element]
        A dict mapping the options to set onto the elements. Initially, none of the elements will be considered selected.
    select_multiple : bool, optional
        Allow selecting multiple elements, by default False
        If True, clicked an element will select that one (or deselect it if it was selected). If False, this will also deselect the current selected element (Or just deselect this one if it is the selected element.)
    allow_deselect : bool, optional
        Allows deselecting the selected option, only used if select_multiple is False (if select_multiple is True, deselecting is always allowed)
    on_select : InteractionFunctionType, optional
        A function to call when the selection changes, by default None
        The function will be passed the ElementSelect element, as well as the selected option(s)
    active_properties : dict, optional
        Properties to apply to any element that are selected (i.e. considered active), by default {"background_color": "active"}
    inactive_properties : dict, optional
        Properties to apply to any element that are not selected (i.e. considered inactive), by default {"background_color": "inactive"}
    active_color : ColorType, optional
        Additional color property that can be used as a shorthand via 'active', by default DEFAULT_FOREGROUND_COLOR
    inactive_color : ColorType, optional
        Additional color property that can be used as a shorthand via 'inactive', by default DEFAULT_ACCENT_COLOR
    foreground_color : ColorType, optional
        Color to use as a foreground_color, which can also be used  in the active/inactive properties, by default DEFAULT_FOREGROUND_COLOR
    accent_color : ColorType, optional
        Color to use as a accent_color, which can also be used  in the active/inactive properties,, by default DEFAULT_ACCENT_COLOR    
    """

    @classproperty
    def _color_shorthands(cls) -> dict[str,str]:
        "Class method to get shorthands for color setters, to allow for parsing their values in element properties. Returns a dict with the [key] being the shorthand to use for element properties and [value] being the tile attribute it links to."
        return {"active": "active_color", "inactive": "inactive_color"} | _TileBase._color_shorthands

    def __post_init__(self, id, _register):
        ##Since this works on already defined elements, the __post_init__ is overwritten as otherwise it'd be registered again.
        ##And cause issues since the element __init__ is not called
        return

    def  __init__(self, layout_element : Union[Layout, "_ElementSelect"], elements : dict[Literal["option"], Element], select_multiple : bool = False, allow_deselect : bool = True, on_select : InteractionFunctionType = None,
                active_properties : dict = {"background_color": "active"}, inactive_properties : dict = {"background_color": "inactive"},
                active_color : ColorType = DEFAULT_FOREGROUND_COLOR, inactive_color : ColorType = DEFAULT_ACCENT_COLOR,
                foreground_color : ColorType = DEFAULT_FOREGROUND_COLOR, accent_color : ColorType = DEFAULT_ACCENT_COLOR):

        ##Check if this will work with the setters
        ##Seems not to.

        self = layout_element

        self.__generator = layout_element.generator
        "The generator of the original function"

        class_name = f"{layout_element.__class__.__name__}_select"
        typeDict = {}
        saved = {}

        properties = _ElementSelect.__dict__
        exempt = {"_color_setter", "_reparse_element_colors", "_color_shorthands"}

        self.active_color = active_color
        self.inactive_color = inactive_color
        self.foreground_color = foreground_color
        self.accent_color = accent_color

        for prop in properties:
            if prop[0] == "_" and prop not in exempt: 
                continue
            if prop in _ElementSelect.color_properties:
                saved[prop] = getattr(layout_element,prop, getattr(self, prop, None))
            typeDict[prop] = getattr(_ElementSelect,prop)

        child_class = type(class_name, (_ElementSelect,layout_element.__class__), typeDict)
        layout_element.__class__ = child_class

        self.__selected = None
        self.__option_elements = elements

        for prop, val in saved.items():
            setattr(self,prop,val)

        self.select_multiple = select_multiple
        self.allow_deselect = allow_deselect

        self._active_properties = {}
        self._inactive_properties = {}

        self.active_properties = active_properties
        self.inactive_properties = inactive_properties

        self._on_select_data = {}
        self._on_select_map = {}
        self.on_select = on_select

        for opt, elt in self.__option_elements.items():
            d = {"action": self.async_select_by_element, "data": {"option": opt}}
            elt.tap_action = d

        self._reparse_element_colors()

    #region
    @property
    def option_elements(self) -> dict[Literal["option"],Element]:
        return self.__option_elements

    @property
    def options(self) -> list:
        return list(self.__option_elements.keys())

    @property
    def selected(self) -> Union[str,list[str],None]:
        "The selected option(s), or None if nothing is selected"
        return self.__selected
    
    @property
    def selected_elements(self) -> list[Element]:
        "The elements that are selected"
        if self.selected == None:
            return []
        elif not isinstance(self.selected,list):
            return [self.option_elements[self.selected]]
        else:
            elts = []
            elements = self.option_elements
            for opt in self.selected:
                elts.append(elements[opt])
            return elts

    @property
    def select_multiple(self) -> bool:
        "True if multiple options can be selected at once"
        return self.__select_multiple
    
    @select_multiple.setter
    def select_multiple(self, value):
        self.__select_multiple = bool(value)

    @property
    def allow_deselect(self) -> bool:
        "True if multiple options can be selected at once"
        return self.__allow_deselect
    
    @allow_deselect.setter
    def allow_deselect(self, value):
        self.__allow_deselect = bool(value)

    @property
    def active_properties(self) -> dict:
        "Attributes that are applied to an element when it becomes active (i.e. is selected)"
        ##Do use a parser in here maybe?
        return self._active_properties
    
    @active_properties.setter
    def active_properties(self, value):
        if value == self._active_properties:
            return
        
        self._active_properties = tools.update_nested_dict(value, self._active_properties)
        self._reparse_colors = True

    @property
    def inactive_properties(self) -> dict:
        "Attributes that are applied to an element when it becomes inactive (at the start or when deselected)"
        return self._inactive_properties
    
    @inactive_properties.setter
    def inactive_properties(self, value):
        if value == self._inactive_properties:
            return
        
        self._inactive_properties = tools.update_nested_dict(value, self._inactive_properties)
        self._reparse_colors = True

    @elementaction
    def on_select(self) -> Callable[["Element",Union[list[Literal["selection"]]]],Any]:
        "Function that is called when the selection changes. Passes the element itself and the current selection. Optionally waits for `on_select_delay` seconds before continueing to the function."
        return self._on_select

    @property
    def on_select_delay(self) -> float:
        "An optional delay that the element will wait to pass without any changes in the selection, before calling `on_select`"
        return self.__on_select_delay

    @on_select_delay.setter
    def on_select_dalay(self, value):
        if value == None:
            if self.select_multiple: value = 0.5
            else: value = 0
        
        self.__on_select_delay = tools.parse_duration_string(value)
                
    @colorproperty
    def foreground_color(self) -> Union[ColorType]:
        "Additional color attribute for styling, if not present in the original layout element"
        return self._foreground_color

    @colorproperty
    def accent_color(self) -> Union[ColorType]:
        "Additional color attribute for styling, if not present in the original layout element"
        return self._accent_color

    @colorproperty
    def background_color(self) ->  Union[ColorType,None]:
        return self._background_color


    @colorproperty  ##Can't recall why I redefined these.
    def outline_color(self) ->  Union[ColorType,None]:
        return self._outline_color

    @colorproperty
    def active_color(self) -> ColorType:
        "A color value that can be used to style the active element(s)"
        return self._active_color

    @colorproperty
    def inactive_color(self) -> ColorType:
        "A color value that can be used to style the inactive element(s)"
        return self._inactive_color

    def _color_setter(self,attribute:str, value : ColorType, allows_None : bool = True, cls : type = None):
        
        ##Generally, this one should not be called if the value is the same as per how the color properties are set up
        Layout._color_setter(self, attribute, value, allows_None, cls)
        self._reparse_colors = True

    def _reparse_element_colors(self, element: Union[Literal["option"],list[Literal["option"]],Element, list[Element]] = None):
        """
        Reparses the colors, using the correct attributes for the active and inactive elements.
        Hence it also takes care of updating the attributes when an element is selected/deselected
        """

        active_elts = set(self.selected_elements)

        updated = False
        if element == None:
            elts = set(self.__option_elements.values())
            inactive_elts = elts.difference(active_elts)
            self._reparse_colors = False
        else:
            if element in self.option_elements or isinstance(element, Element):
                if not isinstance(element,Element):
                    element = self.option_elements[element]
                
                if element in active_elts:
                    active_elts = [element]
                    inactive_elts = []
                else:
                    active_elts = []
                    inactive_elts = [element]
            elif element[0] in self.option_elements or isinstance(element[0], Element):
                if not isinstance(element[0],Element):
                    elt_list = set([self.option_elements[elt] for elt in element])
                else:
                    elt_list = set(element)

                ##Intersection: i.e. all elements in active_elements and in elt_list; difference: all elements in elt_list and not in active_elts (meaning they're in inactive_elts)
                active_elts = elt_list.intersection(active_elts)
                inactive_elts = elt_list.difference(active_elts)
            
        if active_elts:
            active_elts = list(active_elts)
            set_props = self.active_properties.copy()
            color_setters = self.__class__._color_shorthands
            color_props = active_elts[0].__class__.color_properties
            for prop in color_props.intersection(set_props):
                if isinstance(set_props[prop],str) and set_props[prop] in color_setters:
                    color_attr = color_setters[set_props[prop]]
                    set_props[prop] = getattr(self,color_attr)
            for elt in active_elts:
                # ##At least for now: no updatelock or generator lock are returned, so all elements think the selector is always updating and generating
                ##Should be able to fix that when copying stuff over from the parentlayout

                elt_upd = elt.update(set_props, skipPrint=self.isUpdating)
                if elt_upd: updated = True

        if inactive_elts:
            inactive_elts = list(inactive_elts)
            set_props = self.inactive_properties.copy()
            color_setters = self.__class__._color_shorthands

            color_props = inactive_elts[0].__class__.color_properties
            for prop in color_props.intersection(set_props):
                if set_props[prop] in color_setters:
                    color_attr = color_setters[set_props[prop]]
                    set_props[prop] = getattr(self,color_attr)
            for elt in inactive_elts:
                elt_upd = elt.update(set_props, skipPrint=self.isUpdating)
                if elt_upd: updated = True
        
        return updated
    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        if self._reparse_colors and not self.isGenerating:
            if self._reparse_element_colors():
                skipNonLayoutGen = False
        return self.__generator(area, skipNonLayoutGen)

    async def async_generate(self, area: PSSMarea = None, skipNonLayoutGen: bool = False) -> Coroutine[Any, Any, Image.Image]:
        async with self._generatorLock:
            if self._reparse_colors:
                if self._reparse_element_colors():
                    skipNonLayoutGen = False
        await asyncio.sleep(0)
        return await super().async_generate(area, skipNonLayoutGen)

    def select(self, option : str):
        "Select or deselect the given option"
        if asyncio._get_running_loop() == None:
            self.parentPSSMScreen.mainLoop.create_task(self.async_select(option))
        else:
            asyncio.create_task(self.async_select(option))

    async def async_select_by_element(self, element, interaction, option : str):
        "Function that can be used as a tap_action, to select the element"
        await self.async_select(option)

    async def async_select(self, option : str, call_on_select : bool = True):
        """
        Select or de select the provided option

        Parameters
        ----------
        option : str
            The option to select
        call_on_select : bool, optional
            If False, `on_select` will not be called when selecting
        """        

        if option not in self.option_elements:
            _LOGGER.warning(f"{self}: {option} is not a valid option")
            return

        coros = []
        if self.select_multiple:
            if self.selected == None:
                self.__selected = [option]
            elif option in self.selected:
                self.__selected.remove(option)
            else:
                self.__selected.append(option)
        else:
            if option == self.selected:
                if not self.allow_deselect:
                    return
                
                self.__selected = None
            else:
                self.__selected = option

        if not self.isUpdating:
            async with self._updateLock:
                self_upd = self._reparse_element_colors()
        else:
            self_upd = self._reparse_element_colors()

        if self_upd:
            await asyncio.sleep(0)
            await self.async_update(updated=True)

        if self.on_select != None and call_on_select:
            coros.append(tools.wrap_to_coroutine(self.on_select, self, self.selected, **self.on_select_kwargs))

        L = await asyncio.gather(*coros, return_exceptions=True)
        for res in L:
            if isinstance(res,Exception):
                _LOGGER.warning(f"Counter error: {res}")        

    def add_option(self, option, element : Element, overwrite = False):
        """
        Adds a new element to the options to be selected and sets the tap_action appropriately

        Parameters
        ----------
        option : _type_
            The option this element is connected to
        element : Element
            The element to use this for
        overwrite : bool, optional
            Overwrite the option if it already exists, by default False
        """
        if option in self.__option_elements and not overwrite:
            _LOGGER.warning(f"{self} already has an option {option}, not adding it.")
            return
        
        self.__option_elements[option] = element
        element.tap_action = {"action": self.async_select_by_element, "data": {"option": option}}
        self._reparse_element_colors(element)

    def remove_option(self, option : str):
        """
        Removes an option from the selectors, and resets the associated element's tap_action (styling is not reset)

        Parameters
        ----------
        option : str
            The option to remove
        """

        if option not in self.__option_elements:
            _LOGGER.warning(f"{self} does not have an option {option}.")
            return
        
        if self.selected == option or (self.selected != None and option in self.selected):
            ##Will have to see if this works or causes race conditions
            ##If so, just make it async
            self.select(option)

        element = self.__option_elements.pop(option)
        element.tap_action = None


class _IntervalUpdate(ABC):
    """
    Base for elements that periodically update. Not an Element, that should be the other super class of the element you're basing this on.
    To disable the interval update, call `stop_wait_loop`, or set both update_interval and update_every to None.
    To manually start the loop, call `start_wait_loop`, which loops until it is either cancelled, or both update_interval and update_every are None (i.e. the wait time between loops is smaller than or equal to 0).


    Parameters
    ----------
    start_on_add : bool, optional
        Start the update loop immediately when this element is added to the screen?, by default True
    restart_on_add : bool, optional
        Restarts the update loop (if running) when this element is added to the screen. This is done by cancelling the update task., by default True
    stop_on_remove : bool, optional
        stops the update loop when the element is removed from the screen., by default True
    update_every : Literal[&quot;hour&quot;, &quot;minute&quot;, &quot;second&quot;,None], optional
        One of [hour, minute, second]. Sets callback to be called at the top of the hour/minute/second, by default None
    update_interval : Union[DurationType,int, float], optional
        Time between each callback in seconds. Only used if update_every is None. , by default 30
    """  

    def __init__(self, start_on_add : bool = True, restart_on_add : bool = True, stop_on_remove : bool = True, update_every:Literal["hour", "minute", "second",None]=None, update_interval : Union[DurationType,int, float] =30, **kwargs):

        self._updateTask = DummyTask()
        self.update_interval = update_interval
        self.update_every = update_every
        self.start_on_add = start_on_add
        self.restart_on_add = restart_on_add

        self.stop_on_remove = stop_on_remove

    #region
    @property
    def loop(self) -> asyncio.BaseEventLoop:
        "The running event loop"
        return Screen.get_screen().mainLoop

    @property
    def updateTask(self) -> asyncio.Task:
        "The task that periodically updates the element"
        return self._updateTask

    @property
    def update_every(self) -> str:
        "Update at the top of the [hour/minute/second]. Can be one of hour, minute or second. If setting it to None, _update_interval will be used to set the wait time between updates."
        return self.__update_every
    
    @update_every.setter
    def update_every(self, value:str):
        shorthands = {"m":"minute", "min": "minute", "s": "second", "sec": "second", "h": "hour"}
        value = shorthands.get(value,value)
        allowed = ["hour","minute","second"]
        if value == None:
            self.__update_every = None
            return
        elif value not in allowed:
            msg = f"Updateinterval must be one of hour, minute or second"
            _LOGGER.error(msg)
            if const.RAISE: raise ValueError(msg)
        else:
            k = f"{value}s" 
            self._delta_dict = {k:1}
            self._replace_dict = {key: 0 for key in allowed[allowed.index(value):] if key != value}
            self.__update_every = value

    @property
    def _waitTime(self) -> float:
        "Automatically returns the amount of time to wait for the next update in seconds, taking into account if update_every is None or not."
        if self.update_every == None:
            return self.update_intervalSeconds
        else:
            if self.update_every == "second":
                return 1 - dt.now().microsecond*10**-6
            else:
                t = dt.now() +  timedelta(**self._delta_dict)
                t = t.replace(**self._replace_dict)
                difft = t - dt.now()
                return difft.seconds + difft.microseconds*10**-6    ##Added microseconds for extra precision, so the > 0 while loop condition holds.
                ##convert from microseconds like t.microsecond*10**-6

    @property
    def update_interval(self) -> Union[DurationType,int, float, None]:
        "interval between updates, if update_every is not None"
        return self.__update_interval
    
    @property
    def update_intervalSeconds(self) -> Optional[float]:
        "update interval parsed to the amount of seconds. Used if update_every is None"
        return self.__update_intervalSeconds

    @update_interval.setter
    def update_interval(self, value):
        if value == None:
            self.__update_interval = value
            self.__update_intervalSeconds = -1
            return
        secs = tools.parse_duration_string(value)
        self.__update_interval = value
        self.__update_intervalSeconds = secs

    @property    
    @abstractmethod
    def id(self) -> str:
        "The unique id of the element"
        pass    
    #endregion

    @abstractmethod
    async def callback(self):
        "The function to callback on after updating"
        pass

    def on_add(self):
        if not self.start_on_add:
            return
        
        if not self.updateTask.done() and self.restart_on_add:
            self.updateTask.cancel()
        
        if self.updateTask.done():
            loop = Screen.get_screen().mainLoop
            self._updateTask = loop.create_task(self._wait())

    def on_remove(self):
        if self.stop_on_remove:
            self.updateTask.cancel()

    async def _wait(self):
        
        asyncio.create_task(
                self.callback())
        while self._waitTime > 0:
            w = self._waitTime
            _LOGGER.verbose(f"{self} waiting for {w} seconds to call {self.callback}")
            await asyncio.sleep(w)
            asyncio.create_task(
                self.callback())

    def start_wait_loop(self):
        """
        Starts the wait loop that calls the callback function every update_interval, and saves the task it in the updateTask attribute.
        **Only** if the loop is not currently running.
        """
        if self.updateTask.done():
            self._updateTask = asyncio.create_task(self._wait())

    def stop_wait_loop(self):
        """
        Stops the wait loop by cancelling updateTask
        """        
        self.updateTask.cancel()

# ########################## -     Tools       - ##############################

def parse_layout_string(layout_string : str, sublayout : Optional[str] = None, hide : list[str] = [],
                        vertical_sizes : dict[str,PSSMdimension] = {"inner": 0, "outer": 0}, horizontal_sizes : dict[str,PSSMdimension] = {"inner": 0, "outer": 0},
                        **elementParse : dict[str,Element]) -> PSSMlayout:
    """
    Parses a layout from a string. Names defined in layout_string should be passed as an element via a keyword in elementParse.

    Example
    ----------
    layout_string = `"icon,[title;text]"`
    And calling the function as `parse_layout_string(layout_string, horizontal_sizes = {"icon": 'w/4'},  vertical_sizes = {"title": 'h*0.65', "text": 'h*0.35'}  ,icon = IconElement, title=TitleElement, text=TextElement)`
    Returns a layout matrix as `['?', (IconElement, 'w/4'), (Layout(['h*0.65', (TitleElement, '?')],['h*0.35', (TextElement, '?')]])]`
    I.e. a `,` denotes horizontal element separation, `;` denotes vertical element seperation, and elements enclosed within `[]` will be put into a sublayout. 

    Using 'None' (string value) as an entry in the layout string will automatically parse an empty space. Its size can be set using the appropriate key in horizontal and vertical sizes, if desires. 

    Parameters
    ----------
    layout_string : _type_
        The string to parse.
    sublayout : Optional[str], optional
        Sublayout string, by default None. Not needed for the initial run of the function, but needed to use the margins at the correct points during recursion
    hide : list[str], optional
        element names in this list are explicitly removed from the layout_string, i.e. they will not be parsed in the returned layout, by default []
    vertical_sizes : dict[str,PSSMdimension], optional
        vertical sizes of elements. Keys inner and outer denote the size of the inner and outer margins, by default {"inner": 0, "outer": 0}
    horizontal_sizes : dict[str,PSSMdimension], optional
        horizontal_sizes sizes of elements. Keys inner and outer denote the size of the inner and outer margins, by default {"inner": 0, "outer": 0}

    Returns
    -------
    PSSMlayout
        A matrix (nested list) to use as an element layout
    """

    elementParse = elementParse
    if layout_string != None:
        layoutstr = layout_string
    else:
        layoutstr = sublayout

    for key in hide:
        if key in layoutstr:
            if key + ";" in layoutstr:
                layoutstr = layoutstr.replace(key + ";","")
            elif key + "," in layoutstr:
                layoutstr = layoutstr.replace(key + ",","")
            else:
                layoutstr = layoutstr.replace(key,"")

    if not layoutstr:
        return [["?"]]

    if layoutstr[-1] in [";", ","]:
        layoutstr = layoutstr[:-1]

    buildlayout = layoutstr
    sublayout_dict = {}
    while s := re.findall("\[([^[\]]*)\]", buildlayout):
        sub_idx = len(sublayout_dict)
        regexlayout_str = s[0]
        p = bool(regexlayout_str)

        if not bool(regexlayout_str):
            buildlayout = buildlayout.replace("[]","")
            continue

        if regexlayout_str[-1] in [";", ","]:
            regexlayout_str = regexlayout_str[:-1]

        if ";" in regexlayout_str or "," in regexlayout_str:
            sub_key = f"sublayout_{sub_idx}"
            sublayout_dict[sub_key] = regexlayout_str
        else:
            sub_key = regexlayout_str
        buildlayout = buildlayout.replace(f"[{s[0]}]",sub_key)
    
    for sl, val in sublayout_dict.items():
        sublayoutList = parse_layout_string(None, val, hide, 
                                                    vertical_sizes, horizontal_sizes, **elementParse)
        ##Figure out how to do this if there's only one thing in the sublayout?
        elementParse[sl] = Layout(sublayoutList, _isSubLayout = True, _register=False)
        _LOGGER.debug(val)

    buildlayout = buildlayout.split(";")
    buildlayout = [row.split(",") for row in buildlayout]
    layout = []

    if vertical_sizes.get("outer", 0) != 0 and sublayout == None:
        s = vertical_sizes.get("outer", 0)
        layout.append([s,(None,"w")])

    for idx, str_row in enumerate(buildlayout):

        if vertical_sizes.get("inner", 0) != 0 and idx != 0:
            s = vertical_sizes.get("inner", 0)
            layout.append([s,(None,"w")])
        
        added_strs = []
        row = ["?"]
        if horizontal_sizes.get("outer", 0) != 0 and sublayout == None:
            s = horizontal_sizes.get("outer", 0)
            row.append((None,s))

        for jdx, eltstr in enumerate(str_row):
            w = "?"

            if horizontal_sizes.get("inner", 0) != 0 and jdx != 0:
                s = horizontal_sizes.get("inner", 0)
                row.append((None,s))

            if eltstr in elementParse:
                elt = elementParse[eltstr]
                w = horizontal_sizes.get(eltstr,w)
                added_strs.append(eltstr)
            elif eltstr == "None":
                elt = None
                w = horizontal_sizes.get(eltstr,w)
                added_strs.append(eltstr)
            else:
                elt = None
                w = horizontal_sizes.get("inner", 0)

            row.append((elt,w))

        if horizontal_sizes.get("outer", 0) != 0 and sublayout == None:
            s = horizontal_sizes.get("outer", 0)
            row.append((None,s))

        if len(added_strs) == 1:
            row[0] = vertical_sizes.get(added_strs[0],"?")

        layout.append(row)


    if vertical_sizes.get("outer", 0) != 0 and sublayout == None:
        s = vertical_sizes.get("outer", 0)
        layout.append([s,(None,"w")])

    return layout

