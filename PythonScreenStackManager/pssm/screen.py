"""
This package holds the PSSMScreen class, which manages the screen printing and elements.
It should be instantiated before any elements.
"""

#!/usr/bin/env python

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import Callable, Union, Optional, Literal, TYPE_CHECKING, Any, Coroutine
from types import MappingProxyType
from contextlib import suppress

from PIL import Image, ImageOps, ImageFile, ImageFilter

from .styles import Style
from .util import elementactionwrapper

from ..tools import DummyTask, get_Color, is_valid_Color
from .. import tools

from ..pssm_types import *
from ..exceptions import *

from ..constants import CUSTOM_FOLDERS, DEFAULT_BACKGROUND
from .. import constants as const

from ..pssm_settings import SETTINGS, settings_type

from ..devices import PSSMdevice, FEATURES
from .. import elements, devices

ImageFile.LOAD_TRUNCATED_IMAGES = True
_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .. import elements
    from ..elements.baseelements import Element


# ########################## - StackManager    - ##############################
class PSSMScreen:
    """
    This is the class which handles most of the logic for printing on the screen etc.
    Check the documentation or the docstrings for the values of various attributes.

    Parameters
    ----------
    device : PSSMdevice
        The device instance to use for printing
    on_interact : Union[Callable[[dict, 'PSSMScreen', CoordType], None], bool,None], optional
        An optional function to call when interacting with the screen, by default None
    on_interact_data : dict, optional
        Keyword arguments to pass to the on_interact function, by default {}
    background : _type_, optional
        Background image or color, by default DEFAULT_BACKGROUND
    background_fit : Literal[&quot;contain&quot;, &quot;cover&quot;, &quot;crop&quot;, &quot;resize&quot;], optional
        When using a background image, the image will be fitted using this method, by default "cover"
        See `set_background_image` for more info.
    background_fit_arguments : dict, optional
        Optional arguments to pass to the background fit function, if appropriate for the method, by default {}
    isInverted : bool, optional
        If True, the entire screen is inverted, by default False
    poll_interval : Union[float, DurationType], optional
        Interval with which the device is polled, by default SETTINGS["screen"]["poll_interval"] (i.e. parsed from settings.json, if applicable)
        Accepts duration strings, which are parsed to seconds
    close_popup_time : Union[float, DurationType], optional
        The time , by default SETTINGS["screen"]["close_popup_time"] (i.e. parsed from settings.json, if applicable)
    backlight_behaviour : Optional[Literal[&quot;Manual&quot;, &quot;On Interact&quot;, &quot;Always&quot;]], optional
        Behaviour of the screen's backlight (screen brightness or otherwise), by default None
        On Interact means it is turned on temporarily when interacting with the screen
        Manual means it has to be manually turned on and off
        Always is basically manual, but turns on the brightness when PSSM starts
    backlight_time_on : Union[float, DurationType], optional
        If backlight_behaviour is 'On Interact', this value determines how long the backlight stays on for after the last interaction, by default None
    """
    
    generatorPool = concurrent.futures.ThreadPoolExecutor(None,const.GENERATOR_THREADPOOL)

    def __new__(cls, *args, **kwargs):
        if not hasattr(PSSMScreen,"_instance"):
            cls._instance = object.__new__(cls)
            return cls._instance
        else:
            screen = cls._instance
            return screen
    
    @staticmethod
    def get_screen() -> "PSSMScreen":
        "Returns the screen instance"
        if not hasattr(PSSMScreen, "_instance"):
            raise AttributeError("No screen instance has been defined yet")
        return PSSMScreen._instance

    def __init__(self, device : PSSMdevice,  
                touch_debounce_time: DurationType = const.DEFAULT_DEBOUNCE_TIME, minimum_hold_time: DurationType = const.DEFAULT_HOLD_TIME, 
                on_interact: Union[Callable[[dict, 'PSSMScreen', CoordType], None], bool,None] = None, on_interact_data : dict = {}, #stack=[], 
                background : Union[str,ColorType] = DEFAULT_BACKGROUND, background_fit : Literal["contain", "cover", "crop", "resize"] = "cover", background_fit_arguments : dict = {}, 
                poll_interval : DurationType = SETTINGS["screen"]["poll_interval"],
                close_popup_time: DurationType =  SETTINGS["screen"]["close_popup_time"],
                backlight_behaviour : Optional[Literal["Manual", "On Interact", "Always"]] = "Manual", backlight_time_on : Union[float, DurationType] = None):

        ##Placeholder loop to have the atttribute set
        Style.screen = self

        try:
            self.__mainLoop = asyncio.get_running_loop()
        except RuntimeError:
            self.__mainLoop = asyncio.new_event_loop()
        self.__eStop : asyncio.Future = self.__mainLoop.create_future()
        self.__mainLoop.set_default_executor(self.generatorPool)

        self.__shorthandFunctions = {
                                    "save-settings" : self.save_settings,
                                    "quit" : self.quit,
                                    "reload": self.reload,
                                    "show-popup": self.show_popup,
                                    "rotate": self.rotate,
                                    "set-background": self.set_background_image
                                    }

        self.__shorthandFunctionGroups = {"element": self.parse_element_function}

        self._printLock = asyncio.Lock()
        "Lock to ensure only one print loop can run"

        self._printGather : asyncio.Future = DummyTask()
        "Gather function used when starting printing. Can be cancelled to stop printing and free up the printLock."

        self._element_checks : dict["elements.Element",dict[str,Any]]= {}
        """
        Keeps track of element checks to perform before printing starts. Works via element keys, and loops over every attribute in key, and sets it to the value.
        Deleted after the check has been performed.
        """

        self.__popupRegister : dict[str,"elements.Popup"] = {}
        self.__elementRegister : dict[str: "elements.Element"] = {}
        self.__elementRegisterCallbacks : list[Callable[["elements.Element"],Any]] = []

        assert isinstance(device, devices.PSSMdevice), f"A device must be a subclass of PSSMdevice, type {type(device)} is not allowed."

        self._device = device
        self._device._Screen = self
        self._device._updateCondition = asyncio.Condition()
        if self._device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self._device.backlight._updateCondition = asyncio.Condition()
        
        self._device._set_screen()

        if self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            if backlight_behaviour != None:
                self.set_backlight_behaviour(backlight_behaviour)
            if backlight_time_on != None:
                self.device.backlight.default_time_on = backlight_time_on
            
            self.__shorthandFunctions["backlight-toggle"] = self.toggle_backlight_tap_action
            self.__shorthandFunctions["backlight-turn-on"] = tools.wrap_to_tap_action(self.device.backlight.turn_on_async)
            self.__shorthandFunctions["backlight-turn-off"] = tools.wrap_to_tap_action(self.device.backlight.turn_off_async)
            self.__shorthandFunctions["backlight-temporary"] = tools.wrap_to_tap_action(self.temporary_backlight_async)
            self.__shorthandFunctions["backlight-set-behaviour"] = tools.wrap_to_tap_action(self.set_backlight_behaviour)

        if self.device.has_feature(FEATURES.FEATURE_POWER):
            self.__shorthandFunctions["power-off"] = self.device.power_off
            self.__shorthandFunctions["reboot"] = self.device.reboot

        self.set_background_image(background, fit_method=background_fit, fit_arguments=background_fit_arguments)

        self._stack = []
        self._isInverted = False
        self._isInputThreadStarted = False

        self._lastCoords = (-1,-1)
        self._interactEvent = asyncio.Event()
        self.__touchDebounceTime = tools.parse_duration_string(touch_debounce_time)
        self.__minimumHoldTime = tools.parse_duration_string(minimum_hold_time)

        if on_interact == True:
            _LOGGER.error("on_interact can only be False if a boolean is passed, setting to False")
            on_interact = False

        self.on_interact = on_interact
        self.on_interact_data = on_interact_data

        ##Can use this property here to set the osk after setting the screen
        self.osk = None

        self._numberEltOnTop = 0
        self._isOSKShown = False

        self._isBatch = True

        self._popupsOnTop = []
        
        self.poll_interval = poll_interval
        self.close_popup_time = close_popup_time

        self._runningTasks = set()
        self._lightupTask = DummyTask()

        elements.StatusBar._statusbar_elements = {}
        elements.DeviceMenu()
        elements.ScreenMenu()

        elements.StatusBar.add_statusbar_element("device", elements.DeviceIcon())
        screen_name = "inkboard" if const.INKBOARD else "screen"
        dashboardIcon = elements.Icon("mdi:view-dashboard", tap_action={"action": "element:show-popup", "element_id": "screen-menu"})
        elements.StatusBar.add_statusbar_element(screen_name, dashboardIcon)
        
    #region Properties
    # -------------------- Properties of the screen and device ------------------- #
    @property
    def device(self) -> "PSSMdevice":
        """The device of the screen. For handling battery, screen printing etc."""
        return self._device

    @property
    def _SETTINGS(self) -> settings_type:
        "The settings instance, use with care"
        return SETTINGS

    @property
    def colorMode(self):
        """The colorMode of the screen, i.e. the final mode the PILLOW image will be converted to."""
        return self.device.colorType
    
    @property
    def imgMode(self):
        """
        Mode to build images in. Generally colorMode+A; Defined by the device.
        Depending on performance on various platforms, imgMode may simply default to RGBA, since PIL gives better results when combining images in this mode.
        """
        return self.device.imgMode
    
    @property
    def width(self) -> int:
        """The width of the screen."""
        return self.device.screenWidth

    @property
    def height(self) -> int:
        """The height of the screen."""
        return self.device.screenHeight
    
    @property
    def size(self) -> tuple[wType,hType]:
        "The size of the screen, i.e. (screen.width, screen.height)"
        return (self.width, self.height)

    @property
    def viewWidth(self):
        """The width of the screen, taking bezels into account."""
        return self.device.viewWidth
    
    @property
    def viewHeight(self):
        """The height of the screen, taking bezels into account"""
        return self.device.viewHeight
    
    @property
    def viewSize(self) -> tuple[wType,hType]:
        "The viewsize of the screen, i.e. (screen.viewWidth, screen.viewHeight)"
        return (self.viewWidth, self.viewHeight)

    @property
    def widthOffset(self):
        """The width offset, i.e. total width - view width"""
        return self.width - self.viewWidth
    
    @property
    def heightOffset(self):
        """The height offset, i.e. total height - view height"""
        return self.height - self.viewHeight

    @property
    def area(self) -> PSSMarea:
        """The area of the screen (device). Returns a list with two typles: the (x,y) origin (0,0) and the (x,y) bounds (view_width, view_height)"""
        return [(0, 0), (self.viewWidth, self.viewHeight)]

    @property
    def rotation(self) -> Literal["UR", "CW", "UD", "CCW"]:
        "The screen rotation. Call screen.rotate() to rotate it."
        return SETTINGS["screen"]["rotation"]

    @property
    def poll_interval(self) -> Union[str,int, DurationType]:
        "Interval inbetween which hardware and the like are polled for updates. Set to 0 to disable polling."
        return SETTINGS["screen"]["poll_interval"]

    @poll_interval.setter
    def poll_interval(self, value):
        secs = tools.parse_duration_string(value)
        SETTINGS["screen"]["poll_interval"] = value
        self._pollSeconds = secs

    @property
    def pollSeconds(self) -> float:
        "The value of poll_interval in seconds"
        return self._pollSeconds

    ###Properties that have to do with the elements and printing 
    @property
    def mainLoop(self) -> asyncio.BaseEventLoop:
        "The main running loop. Can be useful to access when dealing with functions running in threads."
        return self.__mainLoop
    
    @property
    def printing(self) -> bool:
        "Whether printing to the screen has started. False during setup phase, true after starting the print handler"
        return self._printLock.locked()
        # return self.__printing

    @property
    def isBatch(self) -> bool:
        """Whether the screen is processing a batch of elements"""
        return self._isBatch

    @property
    def stack(self) -> list['elements.Element']:
        """The full stack of elements currently on screen"""
        return self._stack
    
    @property
    def mainElement(self) -> Union['elements.Layout','elements.Element']:
        "The first element in the stack. Considered as the main element for rotating etc."
        return self.stack[0]

    @property
    def isInverted(self) -> bool:
        """Is the entire screen currently inverted?"""
        return self._isInverted

    @property
    def numberEltOnTop(self) -> int:
        """
        Number of elements above the OSK? (I'm not fully sure yet what this does)
        Stack level of the OSK (Though it should always be the highest level)
        Not relevant rn since no osk is being tested, but would be useful to ensure popups do not appear above the OSK
        """
        return self._numberEltOnTop

    @property
    def popupsOnTop(self) -> list["elements.Popup"]:
        """The popups currently on top of the screen."""
        return self._popupsOnTop
    
    @property
    def close_popup_time(self) -> Union[str,int, DurationType]:
        """Time without interaction after which popups are automatically removed. Set to 0 to disable autoclose."""
        return SETTINGS["screen"]["close_popup_time"]

    @close_popup_time.setter
    def close_popup_time(self, value : float) -> float:
        """Time without interaction after which popups are automatically removed. Set to 0 to disable autoclose."""
        secs = tools.parse_duration_string(value)
        if secs < 0: 
            _LOGGER.error("Autoclose time smaller than 0, set to 0.")
            value = 0
        
        SETTINGS["screen"]["close_popup_time"] = value
        self._close_popup_seconds = secs

    @property
    def close_popup_seconds(self) -> float:
        "Value of close_popup_time in seconds"
        return self._close_popup_seconds 

    @property
    def popupRegister(self) -> MappingProxyType[Literal["popup_id"],"elements.Popup"]:
        "Links popups to their id (if they have been registered, either by calling register_popup or by adding them to the screen)"
        return MappingProxyType(self.__popupRegister)
    
    @property
    def elementRegister(self) -> MappingProxyType[Literal["element_id"],"elements.Element"]:
        "Returns a dict with element id's and their respective element"
        return MappingProxyType(self.__elementRegister)

    @property
    def isOSKShown(self) -> bool:
        "If the OSK is currently on shown"
        return self._isOSKShown

    ###Properties/setters that have to do with interaction
    @property
    def isInputListenerStarted(self) -> bool:
        """Has the input listener function been started?"""
        return self._isInputListenerStarted

    @property
    def lastCoords(self) -> CoordType:
        """The last pressed coordinates"""
        return self._lastCoords
    
    @property
    def shorthandFunctions(self) -> MappingProxyType[str,Callable[["elements.Element", CoordType],Any],Any]:
        "Dict for global shorthand function names that can be used to set element tap_actions by a string"
        return MappingProxyType(self.__shorthandFunctions)

    @property
    def shorthandFunctionGroups(self) -> MappingProxyType[str,Callable[[str,str,Optional[dict]],Callable]]:
        "Registered identifiers for shorthand functions."
        return MappingProxyType(self.__shorthandFunctionGroups)

    @property
    def on_interact(self) -> Optional[Callable[[dict, 'PSSMScreen', CoordType], None]]:#, bool,None]:
        """
        Function to call whenever the screen is interacted with. Will be passed the screen object, click coordinates and on_interact dict. 
        Called as function(**PSSMScreen.on_interact_data, screen, coords)
        Set to None to reset to default value.
        Does not affect backlight behaviour
        """
        return self._on_interact

    @on_interact.setter
    def on_interact(self, func : Callable):
        if isinstance(func,str):
            if not self.printing:
                self._add_element_attribute_check(self,"on_interact", func)
            else:
                func = self.parse_shorthand_function(func, self.on_interact_data)
        self._on_interact = tools.function_checker(func, default=False)

    @property
    def on_interact_data(self) -> dict:
        """The dict that is passed to the on_interact function, along with the screen itself and clicked coordinates"""
        return self._on_interact_data
    
    @on_interact_data.setter
    def on_interact_data(self, dct : dict):
        self._on_interact_data = dct
    
    ##Properties having to do with asyncio loops and tasks
    @property
    def runningTasks(self) -> set:
        """Set of currently running tasks. Not yet implemented but will contain the gathers from _async_interact_handler"""
        return self._runningTasks
    
    @property
    def deviceUpdateCondition(self) -> asyncio.Condition:
        """
        Asyncio condition that is notified when the device states updates have been called (so every config.device["update_interval"]), or when the backlight changed.
        For usage see: https://superfastpython.com/asyncio-condition-variable/#Wait_to_be_Notified
        """
        return self.device.updateCondition

    @property
    def lightupTask(self) -> Union[asyncio.Task,DummyTask]:
        "The task keeping track of temporary screen turn on"
        return self._lightupTask
    
    @property
    def _eStop(self) -> asyncio.Future:
        """
        An asyncio future that can be used to perform an 'emergency' stop by throwing an exception or setting a result. Don't use if you do not know what you're doing. Instantiated when calling _set_main_loop().
        In general you don't need to touch this, it's better to call the actions reload/quit and let the programme running PSSM handle the error.
        """
        return self.__eStop
    
    @property
    def background(self) -> Union[str,ColorType]:
        "The main screen background. Either a color or an image."
        return self.__background
    
    @background.setter
    def background(self, value : Union[str, ColorType]):
        if Style.is_valid_color(value):
            self.__background = value
            self.__baseBackgroundImage = Image.new(self.imgMode, self.size, color = Style.get_color(value,self.imgMode))
        elif isinstance(value,(str,Path)):
            try:
                img = Image.open(value)
                img = ImageOps.fit(img,self.size)
                if img.mode != self.imgMode:
                    self.__baseBackgroundImage = img.convert(self.imgMode)
                else:
                    self.__baseBackgroundImage = img
            except FileNotFoundError:
                raise FileNotFoundError(f"Could not find an image file {value}")
        else:
            raise ValueError(f"{value} could not be used as a valid background color or image.")
        
        self.__background = value
        self.__backgroundImage = self.__baseBackgroundImage.copy()
    
    @property
    def backgroundImage(self) -> Image.Image:
        """
        Shorthand to access a copy of the background Image, e.g. when needing to paste on it.
        Image always matches the screen size.
        """
        return self.__backgroundImage.copy()

    @property
    def backlight_behaviour(self) -> Optional[Literal["Manual", "On Interact", "Always"]]:
        """
        Behaviour of the screen's backlight. Returns None if the screen has no (controllable) backlight.
        
        Options
        --------
        Manual: 
            backlight is only turned on/off when done so via a function or element tap_action
        On Interact: 
            backlight is automatically turned on when interacting with the screen. After a set amount of seconds it is turned off again.
        Always: 
            backlight is always on by default (But can be turned off via functions/elements)
        """
        if not self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            return None
        return self.device.backlight.behaviour
    
    @backlight_behaviour.setter
    def backlight_behaviour(self, value):
        self.set_backlight_behaviour(value)
        
    @property
    def backlight_time_on(self) -> Optional[Union[int,float]]:
        """
        Default  time to turn the backlight on in seconds for when calling the temporary backlight function
        Set by the device backlight property.
        """
        if not self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            return None
        return self.device.backlight._default_seconds_on
    
    @backlight_time_on.setter
    def backlight_time_on(self, value):
        if not self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            return
        self.device.backlight.default_time_on = value
    #endregion

    #region Bookkeeping functions
    def add_running_task(self,task:asyncio.Task):
        "Add a task to the set of running tasks, and add the callback to remove it when done."
        _LOGGER.debug("Adding task to running set")
        self.runningTasks.add(task)
        task.add_done_callback(self.runningTasks.discard)
        _LOGGER.debug("Tasks added to set")

    def _findEltWithId(self, element_id):
        """
        Returns the element with the associated ID in the element register, or None if that id is not present in the register.
        """
        return self.elementRegister.get(element_id,None)
    
    def _register_element(self,element: "elements.Element"):
        "Registers an element. This function is automatically called when making an element, so it should generally not be necessary to call it."
        id = element.id
        if id in self.elementRegister:
            msg = f"{id} is already registered as an element."
            _LOGGER.error(msg)
            if not self.printing:
                raise DuplicateElementError(msg)
        else:
            self.__elementRegister[id] = element
            if element.isPopup and element.popupID: self._register_popup(element)

            for func in self.__elementRegisterCallbacks:
                func(element)
    
    def add_register_callback(self, func : Callable[["elements.Element"], Any]):
        """
        Adds a callback function that is called whenever a new element is registered.

        Parameters
        ----------
        func : Callable
            The function to call. The new element is passed to it.
        """
        if not isinstance(func,Callable):
            _LOGGER.error(f"Callback functions must be a Callable type. {func} is not valid.")
            return
        if asyncio.iscoroutinefunction(func):
            _LOGGER.error("Callback functions cannot be a coroutine.")
            return

        self.__elementRegisterCallbacks.append(func)

    def add_shorthand_function(self, shorthand : str, func : Callable):
        "Adds a function as a global shorthand function"
        if shorthand in self.__shorthandFunctions:
            _LOGGER.error(f"A function with shorthand {shorthand} is already registered. It will not be added.")
            return

        if ":" in shorthand:
            msg = "Using ':' in a shorthand is not allowed. Register a function group instead to use it."
            raise ValueError(msg)

        self.__shorthandFunctions[shorthand] = func

    def add_shorthand_function_group(self, identifier: str, parser: Callable[[str,str,Optional[dict]],Callable]):
        """Add a group of shorthand functions.
        
        A function from a group is identified when it is prefixed by 'identifier:'. 
        When requested, the screen calls the parser and passes it a string with the shorthand, the attribute called if passed, and a dict with options, i.e. when requested via a `tap_action`, which can be used to validate the input.
        It should return the function to be called.
        It can raise either an AttributeError, ValueError or KeyError, which are caught by the parser and raised if needed.
        """
        if identifier.endswith(":"):
            _LOGGER.debug(f"Function group {identifier} ends with ':'. Will be removed.")
            identifier = identifier.rstrip(":")
        
        if identifier in self.__shorthandFunctionGroups:
            msg = f"Function group identifier {identifier} is already registered"
            raise ValueError(msg)
        
        self.__shorthandFunctionGroups[identifier] = parser


    def parse_shorthand_function(self, shorthand: str, attribute: str = None, options: dict = {}) -> Callable:
        "Parses a shorthand function string to the actual function."

        if ":" in shorthand:
            identifier, func_str = shorthand.split(":")
            if identifier not in self.__shorthandFunctionGroups:
                raise ShorthandGroupNotFound(identifier)
            try:
                parser = self.__shorthandFunctionGroups[identifier]
            except (AttributeError, ValueError, KeyError) as exce:
                raise ShorthandNotFound from exce
            except ShorthandNotFound:
                raise
            return parser(func_str, attribute, options)

        elif shorthand in self.__shorthandFunctions:
            return self.__shorthandFunctions[shorthand]
        
        raise ShorthandNotFound(shorthand)

    def parse_element_function(self, shorthand: str, attribute: str, options: dict = {}):
        if "element_id" not in options:
            raise KeyError("Parsing an element function shorthand requires element_id to be defined")
        
        elt_id = options["element_id"]
        if elt_id not in self.__elementRegister | self.__popupRegister:
            msg = f"No element or popup with id {options['element_id']} is registered."
            raise ElementNotRegistered(msg)
        
        if elt_id in self.__elementRegister:
            elt = self.__elementRegister[elt_id]
        else:
            elt = self.__popupRegister[elt_id]
        
        if shorthand in elt.action_shorthands:
            func_str = elt.action_shorthands[shorthand]
            return getattr(elt,func_str)
        else:
            msg = f"{elt.__class__} elements do not have a shorthand function for {shorthand}."# Cannot set {attribute} for {elt}"
            raise ShorthandNotFound(msg=msg)
            
        return


    def _add_element_attribute_check(self, element : "elements.Element", attribute : str, value : Union[Any, Callable[["elements.Element",Literal["attribute"]],None]]):
        """
        Adds a function to callback the action setter, to ensure it exists and is valid
        Mainly used to check element_id's when printing starts. Function logs to debug, then returns when printing.

        Parameters
        ----------
        element : elements.Element
            The element to test
        attribute : str
            The attribute to set
        value : Any
            The attribute's value. If set to a function, the check will call the function (passing the element object and the attribute as string) instead of setting the attribute.
        """
        
        if self.printing:
            _LOGGER.debug(f"Screen is already printing, not adding attribute check for element {element}, attribute: {attribute}")
            return

        _LOGGER.debug(f"Adding attribute check for element {element}, attribute: {attribute}")
        if element in self._element_checks:
            self._element_checks[element][attribute] = value
        else:
            self._element_checks[element] = {attribute: value}
        return
    
    def _perform_element_attribute_check(self):
        """
        Performs the element attribute check.
        """

        _LOGGER.debug("Performing attribute checks")
        checks_passed = True
        for elt in self._element_checks:
            for attr, val in self._element_checks[elt].items():
                try:
                    if callable(val):
                        val(elt, attr)
                    else:
                        setattr(elt,attr,val)
                except const.FuncExceptions as e:
                    checks_passed = False
                    _LOGGER.error(f"Attribute {attr} check for element {elt} failed: {e}")
                except ElementNotRegistered as e:
                    checks_passed = False
                    _LOGGER.error(f"Attribute {attr} check for element {elt} failed: {e}")

        delattr(self,"_element_checks")
        return checks_passed

    @elementactionwrapper.method
    def save_settings(self, *args):
        "Saves settings for next runs."

        #Settings should be kept up to date when setting the appropriate variables, but just in case.
        sett_map = {'screen': {"rotation" : 'rotation', 
                                },
                    'device' : {'backlight_behaviour': 'backlight.behaviour',
                                'backlight_time_on': 'backlight.default_time_on',
                                'backlight_default_transition': 'backlight.defaultTransition',
                                'backlight_default_brightness': 'backlight.defaultBrightness',
                                }
                    }
        sett_map = SETTINGS.attribute_map
        for setting, attr in sett_map["screen"].items():
            val = eval(f'self.{attr}')
            SETTINGS["screen"][setting] = val

        for setting, attr in sett_map["screen"].items():
            val = eval(f'self.{attr}')
            SETTINGS["screen"][setting] = val

        SETTINGS.save()
        return

    @elementactionwrapper.method
    def reload(self, full: bool = False, *args):
        "Saves settings and sets the _eStop to reload. Reloading must be explicitly implemented in the main script."
        ##Add reload via inkBoard?
        if self.mainLoop.is_running():
            if full:
                exce = FullReloadWarning("Full reload requested")
            else:
                exce = ReloadWarning("Reload requested")
            self.quit(exce=exce)

    @elementactionwrapper.method
    def quit(self, exce: Exception = None, *args):
        "Quits inkBoard by setting the eStop future to SystemExit."
        if not isinstance(exce, Exception) and not (isinstance(exce,type) and issubclass(exce, Exception)):
            exce = SystemExit("Quit called")

        try:
            self.save_settings()
            self.device._quit(exce)
            if self.mainLoop.is_running():
                if not self._printGather.done(): 
                    self._printGather.cancel("Quit was requested")
                self._eStop.set_exception(exce)
        except Exception as e:
            _LOGGER.error(f"Something went wrong quitting inkBoard: {e}")
        finally:
            if not self._printGather.done() and self.mainLoop.is_running():
                _LOGGER.info("Shutting down print loop")
                self._printGather.cancel("Quit was requested")
            if not isinstance(exce, ReloadWarning):
                self.generatorPool.shutdown(False, cancel_futures=True)

        return

    #endregion

    #region Printing functions
    async def print_stack(self, area=None, forceLayoutGen=False):
        """
        Prints the stack Elements in the stack order and sends it to the device to display
        If a area is set, then, we only display
        the part of the stack which is in this area

        Parameters
        ----------
        area : _type_, optional
            The area to print, by default None
        forceLayoutGen : bool, optional
            Regenerates layouts, by default False
        """
        if self.isBatch or not self.printing:
            # Do not do anything during batch mode
            return

        pil_image = await self.generate_stack(area=area, forceLayoutGen=forceLayoutGen)
        
        if area:
            [(x, y), (w, h)] = area
        else:
            [(x, y), (w, h)] = self.area

        if pil_image == None:
            _LOGGER.error("Something went wrong printing the Stack")
            raise ValueError("pil_image for stack print cannot be None")
        
        await asyncio.to_thread(self.device.print_pil, pil_image, x,y, isInverted=self.isInverted)
        _LOGGER.verbose("Printed stack")

    async def generate_stack(self,area=None, forceLayoutGen=False) -> Image.Image:
        """
        Generates the stack in the current stack state.

        Parameters
        ----------
        area : _type_, optional
            The area to capture. Does not bound the generated area, by default None
        forceLayoutGen : bool, optional
            Ensures layout elements are regenerated, by default False

        Returns
        -------
        Image.Image
            The generated image, optionally cropped to area
        """

        img = self.backgroundImage

        if self.stack and self.stack[-1].isPopup and self.stack[-1].blur_background:
            elt = self.stack[-1]
            img = self._stackImage.copy()
            blurfilter = ImageFilter.BoxBlur(3)
            img = img.filter(blurfilter)
            [(x,y), (w,h)] = elt.area

            if elt.isGenerating:
                await elt._await_generator()
            
            if elt.imgData == None:
                elt_img = await elt.async_generate()
            else:
                elt_img = elt.imgData.copy()
            img.paste(elt_img, (x,y,x+w,y+h), mask=elt_img)
        else:
            for elt in self.stack:
                [(x, y), (w, h)] = elt.area
                if elt.isLayout and forceLayoutGen:

                    ##This updates all the layout elements, but grabs all the available element imgData, does not update it. 
                    elt : "elements.Layout"
                    if elt.isGenerating:
                        await elt._await_generator()
                    await elt.async_generate(elt.area, not self.isBatch)
                        
                if elt.isInverted:
                    pil_image = await asyncio.to_thread(tools.invert_Image, img=elt.imgData)
                else:
                    pil_image = elt.imgData

                if pil_image == None:
                    continue
                    
                if isinstance(pil_image, Image.Image):
                    if pil_image.mode == "RGBA" and img.mode == "RGBA":
                        img.alpha_composite(pil_image, (x,y))
                    elif "A" in pil_image.mode: 
                        img.paste(pil_image, (x, y), mask=pil_image)
                    else:
                        img.paste(pil_image, (x, y))
                else:
                    msg = f"Cannot paste type {type(pil_image)} on PIL image."
                    _LOGGER.exception(TypeError(msg))

        self._stackImage = img.copy()
        if area:
            [(x, y), (w, h)] = area
            box = (x, y, x+w, y+h)
            return img.crop(box=box)
        else:
            return img

    def simple_print_element(self, element : "Element", skipGen=False, area: PSSMarea = None, apply_background : bool = False, safe_print : bool = True):
        """
        Prints the Element without adding it to the stack, if not in it.
        Does not honor isBatch (you can simplePrint even during batch mode)

        Parameters
        ----------
        element : Element
            The element to print
        skipGen : bool, optional
            Skip generating this element, by default False
        apply_background : bool, optional
            (tries to) apply the correct background to the element's image, by default False
        safe_print : bool, optional
            Performs a check to see if the element can safely be printed, by seeing if there is no popup overlaying the element, or if the background is blurred by a popup, by default True
        """        
        
        if not skipGen:
            # First, the element must be generated
            if element.isGenerating:
                #Test if this one still works
                #May work with the run_threadsafe otherwise -> eh would not make much difference I suspect as block_run also used that
                tools._block_run_coroutine(element._await_generator(),self.mainLoop)
            else:
                element.generate()
        if element.area == None or element.imgData == None:
            _LOGGER.warning(f"Cannot print element {element.id} before it has  an area set.")
            return
        
        if area:
            [(x, y), (w, h)] = area
        else:
            [(x, y), (w, h)] = element.area

        if not self.printing:
            _LOGGER.warning("Cannot print to screen when not printing")
            return

        if safe_print and element.parentLayouts and element.parentLayouts[0] != self.stack[-1]:
            ##This way elements in the topmost popup should still be able to safely print
            for popup in self.popupsOnTop:
                if tools.get_rectangles_intersection(element.area,popup.area) or popup.blur_background:
                    _LOGGER.debug(f"{element}: Not simple printing as popup {popup} is interfering")
                    return

        if isinstance(skipGen,Image.Image):
            img = skipGen
        else:
            img = element.imgData.copy()

        if apply_background:
            if element.background_color != None:
                pass
            elif element.parentBackground == None:
                crop_box = [x,y,x+w,y+h]
                new_img = self.backgroundImage.crop(crop_box)
                new_img.paste(img, mask=img)
                img = new_img
            else:
                bg = Style.get_color(element.parentBackground, self.imgMode)
                new_img = Image.new(self.imgMode, img.size, bg)
                
                if "A" in self.imgMode and bg[-1] != 255:
                    crop_box = [x,y,x+w,y+h]
                    bg_img = self.backgroundImage.crop(crop_box)
                    bg_img.paste(new_img, mask=new_img)
                    new_img = bg_img
                
                new_img.paste(img, mask=img)
                img = new_img

        self.device.print_pil(
            img,
            x, y,
            isInverted=element.isInverted
        )

    async def _async_simple_print(self, element : "elements.Element", skipGen=False, apply_background : bool = False):
        ##Not removing the code below here. I'd still want to implement this function.
        raise NotImplementedError("async_simple_print is not implemented, please use `simple_print_element()`")

        if not skipGen:
            # First, the element must be generated
            # element.generator()
            if element.isGenerating:
                await element._await_generator()
            else:
                element.async_generate()
        # Then, we print it
        if element.area == None or element.imgData == None:
            _LOGGER.warning(f"Cannot print element {element.id} before it has  an area set.")
            return
        
        [(x, y), (w, h)] = element.area

        if not self.printing:
            _LOGGER.warning("Cannot print to screen when not printing")
            return

        if apply_background:
            img = element.imgData.copy()
            if element.background_color != None:
                pass
            elif element.parentBackground == None:
                crop_box = [x,y,x+w,y+h]
                new_img = self.backgroundImage.crop(crop_box)
                new_img.paste(img, mask=img)
                img = new_img
            else:
                bg = element.parentBackground
                new_img = Image.new(self.imgMode,img.size, bg)
                new_img.paste(img, mask=img)
                img = new_img
        else:
            img = element.imgData.copy()

        ##This doesn't quite work, probably problems with threads or whatever
        self.device.print_pil(imgData=img, x=x, y=y, isInverted=element.isInverted
            )
        return

    def start_batch_writing(self):
        """
        Toggle batch writing: nothing will be updated on the screen until
        you use screen.stop_batch_writing(), or forcibly print something
        """
        _LOGGER.debug("Started screen batch")
        self._isBatch = True

    def stop_batch_writing(self, loop=None):
        """
        Updates the screen after batch writing and generates all elements in the stack.
        """
        self._isBatch = False
        if not self.printing:
            return

        for elt in self.stack:
            if isinstance(elt, elements.Layout):
                for element in elt.create_element_list():
                    if element.isGenerating:
                        _LOGGER.debug("Element is still generating")

        if self.mainLoop.is_running():
            asyncio.run_coroutine_threadsafe(self._end_batch_write(),
                                self.mainLoop)
        else:
            asyncio.run(self._end_batch_write())
                
        _LOGGER.debug("Stopped screen batch")

    async def _end_batch_write(self):
        
        generators = set()
        for elt in self.stack:
            if isinstance(elt, elements.Layout):
                generators.add(elt.async_generate(skipNonLayoutGen=False))
            else:
                generators.add(elt.async_generate())
        
        await asyncio.gather(*generators)
        _LOGGER.debug("Screen batch is done and everything was generated")
        await self.print_stack(self.area,False)
        _LOGGER.debug("Screen batch is done and should be printed")


    def add_element(self, element, skipPrint=False, skipRegistration=False):
        "Add an element to the screen."
        loop = asyncio._get_running_loop()
        if loop == None:
            asyncio.run(self.__async_add_element(element, skipPrint, skipRegistration))
        else:
            asyncio.create_task(self.__async_add_element(element, skipPrint, skipRegistration))

    async def async_add_element(self, element, skipPrint=False, skipRegistration=False):
        await self.__async_add_element(element, skipPrint, skipRegistration)

    async def __async_add_element(self, element : "elements.Element", skipPrint=False, skipRegistration=False):
        """
        Adds Element to the stack and prints it
            element (PSSM Element): The Element you want to add
            skipPrint (bool): True if you don't want to update the screen
            skipRegistration (bool): True if you don't want to add the Element
                to the stack
        """
        
        if not self.stack:
            if element.area != None:
                _LOGGER.warning("The first stack element's size may not be preserved when changing screen settings")
            else:
                element._area = self.area

            _LOGGER.info(f"Element {element.id} is set as the main element")

        if element in self.stack:
            if not skipPrint and self.printing:
                await self.print_stack(area=element.area)
        else:
            # the Element is not already in the stack
                if self.numberEltOnTop > 0:
                    # There is something on top, adding it at position -2
                    # (before the last one)
                    pos = - 1 - self.numberEltOnTop
                    self._stack.insert(pos, element)
                else:
                    self._stack.append(element)
                    
                if not skipPrint and self.printing:
                    if self.numberEltOnTop > 0:
                        await element.async_generate()
                            ##Should this be in a thread?
                        await self.print_stack(area=element.area)
                        if hasattr(element,"is_popup"):
                            _LOGGER.debug("Is this a popup?")
                    else:
                        await element.async_generate()
                        if element.isPopup:
                            await self.print_stack()
                        elif not self.isBatch:
                            self.simple_print_element(element, skipGen=True)
                
        if self.printing: ##If added before printing, they will be called by the start_screen_printing
            add_func = getattr(element,"on_add", False)
            if add_func: 
                _LOGGER.debug("Adding element with add_func")
                if element.isLayout:
                    add_func(call_all = True)
                else:
                    add_func()

    def remove_element(self, element=None, element_id=None, skipPrint=False):
        """
        Remove the given element

        Parameters
        ----------
        element : elements.Element, optional
            Element object, by default None
        element_id : str, optional
            Element id, by default None
        skipPrint : bool, optional
            skip printing of the screen. Means the removal is visible later, by default False
        """
        ##May need to rewrite this to properly handle errors? See add_element I think
        try:
            loop = self.mainLoop
            if loop == None or not loop.is_running(): raise RuntimeError

            loop.create_task(self.__async_remove_element(element, element_id, skipPrint))
        except RuntimeError:
            asyncio.run(self.__async_remove_element(element, element_id, skipPrint))

    async def async_remove_element(self, elt : "elements.Element" =None, eltid : str =None, skipPrint=False):
        """
        Async implementation to remove elements

        Parameters
        ----------
        elt : elements.Element, optional
            Element object, by default None
        eltid : str, optional
            Element id, by default None
        skipPrint : bool, optional
            skip printing of the screen. Means the removal is visible later, by default False
        """
        await self.__async_remove_element(elt, eltid, skipPrint)

    async def __async_remove_element(self, element : "elements.Element" =None, element_id=None, skipPrint=False):
        """
        Removes the Element from the stack and hides it from the screen
        """

        if element != None:
            if element in self._stack:
                if element == self.stack[0]:
                    _LOGGER.warning("Removing the main element from the layout")
                self._stack.remove(element)

            if hasattr(element,"isPopup"):
                if element.isPopup and element in self.popupsOnTop:
                    idx = self.popupsOnTop.index(element)
                    self.popupsOnTop.pop(idx)

            if not skipPrint:
                if element.isPopup:
                    await self.print_stack()
                else:
                    await self.print_stack(area=element.area)
            
        elif element_id != None:
            element = self._findEltWithId(element_id)
            if element:
                self._stack.remove(element)
                if not skipPrint:
                    await self.print_stack(area=element.area)
        else:
            _LOGGER.warning('Cannot remove element, no element given')
            return
        
        if isinstance(element, elements.Layout):
            await asyncio.to_thread(element.remove_element)
        elif callable(f := getattr(element,"on_remove",None)):
            a = tools.wrap_to_coroutine(f)
            asyncio.create_task(a)

    def get_stack_level(self, element):
        elt = self._findEltWithId(element)
        return self.stack.index(elt)

    def invert_element(self, element:"elements.Element", invertDuration=-1,
                useFastPrint=True, skipPrint=False):
        """
        Inverts an Element's area

        Parameters
        ----------
        element : elements.Element
            The PSSM Element to invert
        invertDuration : int, optional
            -1 or 0 if permanent, else a float for the duration in seconds, by default -1
        useFastPrint : bool, optional
            Use hardware inversion. On Eink this is much faster.
            (much faster) instead of generating the new image and printing the whole stack., by default True
        skipPrint : bool, optional
            Save only or save + print? (Only used if inverDuration <= 0), by default False
        """        

        asyncio.create_task(self.async_invert_element(element,invertDuration,useFastPrint, skipPrint))

    async def async_invert_element(self, element:"elements.Element", invertDuration=-1,
                useFastPrint=True, skipPrint=False):
        """
        Inverts an Element's area

        Parameters
        ----------
        element : elements.Element
            The PSSM Element to invert
        invertDuration : int, optional
            -1 or 0 if permanent, else a float for the duration in seconds, by default -1
        useFastPrint : bool, optional
            Use hardware inversion. On Eink this is much faster.
            (much faster) instead of generating the new image and printing the whole stack., by default True
        skipPrint : bool, optional
            Save only or save + print? (Only used if inverDuration <= 0), by default False
        """   

        _LOGGER.verbose(f"Inverting element {element}")
        ##This calls screen refresh etc, so this will have to be handled.
        if element is None:
            _LOGGER.warning("Cannot invert Element, No element given")
            return False
        # First, let's get the Element's initial inverted state
        if invertDuration <= 0:
            ##Inversion is permanent
            element._inverted = not element.inverted
            if not skipPrint: 
                if useFastPrint:
                    await self._invertArea_helper(
                        element.area,
                        invertDuration,
                        True)
                else:    
                    element.update(forceGen=True)
            return
        else:
            Element_initial_state = bool(element.isInverted)
            element._isInverted = not element.isInverted
            element._isTemporaryInverted = True            
            if useFastPrint:
                await self._invertArea_helper(
                    element.area,
                    invertDuration,
                    True)
            else:
                element._inverted = not element.inverted
                element.update(reprintOnTop=True)
                await asyncio.sleep(invertDuration)
                element._inverted = not element.inverted
                element.update(forceGen=True)
            
            element._isTemporaryInverted = False
            element._isInverted = Element_initial_state

    async def _invertArea_helper(self, area, invertDuration : float, isInverted=False):
        """
        Inverts the supplied area for invertDuration seconds.
        args:
            area (list): [(x,y),(w,h)] list of the area to invert
            invertduration (float): time to invert the are for
            isInverted: is this area currently inverted in the screen buffer?
        """
        # [ ] FIX Inverted area seems to get stuck sometimes?
        if invertDuration <= 0:
            _LOGGER.error("Invert duration must be larger than 0.")
            return False
        
        initial_mode = isInverted
        self.device.do_screen_refresh(
            isInverted=isInverted,
            area=area,
            isInvertionPermanent=False,
            isFlashing=True,
            useFastInvertion=True
        )
        await asyncio.sleep(invertDuration)

        ##Do not use FastInvertion when going back. This seems to prevent artefacts from the invertion staying on the screen (Helpful when e.g. an icon changes upon clicking it)
        ##It's a bit less snappy but considering the overall speed of the device not something I mind
        if not self.popupsOnTop:
            self.device.do_screen_refresh(
                isInverted=not initial_mode,
                area=area,
                isInvertionPermanent=False,
                isFlashing=True,
                useFastInvertion=False
            )
        else:
            ## Leaving this code for possible reference purposes
            ## But it is not needed anymore since hardware inversion emulation has been implemented.
            ## If it works weirdly this may need to be enabled again for Ereaders, but on the emulator it looks very similar now to how it worked on the kobo's.

            self.device.do_screen_refresh(
                isInverted=not initial_mode,
                area=area,
                isInvertionPermanent=False,
                isFlashing=True,
                useFastInvertion=False
            )
        return True

    def invert(self):
        """
        Inverts the whole screen
        """
        self._isInverted = not self.isInverted
        self.device.do_screen_refresh(self.isInverted)
        return True

    def refresh(self, regen : bool = False, *args):
        asyncio.create_task(self.async_refresh(regen=regen))

    async def async_refresh(self, regen : bool = False, *args):
        """
        Refresh and reprints the screen.

        Parameters
        ----------
        regen : bool, optional
            Regenerates the full stack, by default False
        """
        self.device.do_screen_refresh(isFlashing=False)
        await self.print_stack(forceLayoutGen=True)
        return True

    def clear(self):
        """
        Clears the screen (Up until the next time stuff is printed)
        Does NOT prevent interaction with elements, seen or unseen.
        """
        asyncio.create_task(self.async_clear())
    
    async def async_clear(self):
        """
        Clears the screen (Up until the next time stuff is printed)
        Does NOT prevent interaction with elements, seen or unseen.
        """
        await asyncio.to_thread(self.device.do_screen_clear)
    #endregion

    #region OSK stuff
    def OSKInit(self, onKeyPress=None, area=None, keymapPath=None):
        if not area:
            x = 0
            y = int(2*self.viewHeight/3)
            w = self.viewWidth
            h = int(self.viewHeight/3)
            area = [(x, y), (w, h)]
        ##Figure out how to do this best without putting it in here.
        self.osk = elements.OSK(onKeyPress=onKeyPress, area=area, keymapPath=keymapPath)

    def OSKShow(self, onKeyPress=None):
        if not self.osk:
            _LOGGER.error("OSK not initialized, it can't be shown")
            return None
        if onKeyPress:
            self.osk.onKeyPress = onKeyPress
        self.add_element(self.osk)   # It has already been generated
        self._numberEltOnTop += 1
        self._isOSKShown = True

    def OSKHide(self):
        if self.isOSKShown:
            self.remove_element(elt=self.osk)
            self._numberEltOnTop -= 1
            self._isOSKShown = False
    #endregion

    #region Popup stuff
    def _register_popup(self, popup: "elements.Popup"):
        "Adds this popup to the popup register"
        id = popup.popupID
        
        if id and id not in self.__popupRegister:
            self.__popupRegister[id] = popup
        elif id:
            msg = f"A popup with id {id} is already registered."
            _LOGGER.error(ValueError(msg))
            if const.RAISE: raise ValueError(msg)
    
    def remove_popup(self,popup: "elements.Popup" = None):
        """
        Creates a task that removes a popup. If None, will default to popup currently on top
        args:
            popup: the popup te remove. If None, will automatically remove the popup on top.
        """
        if popup == None and self.popupsOnTop:
            popup = self.popupsOnTop[-1]
        
        if not popup:
            _LOGGER.warning("There is currently no popup on top, cannot remove")
            return
        
        ##Had some weird error here about no running event loop?
        ##Using UpdateLoop also doesn't seem to work. I assume it has to do with threading
        asyncio.run_coroutine_threadsafe(self.async_remove_popup(popup), self.mainLoop)

    async def async_remove_popup(self,popup: "elements.Popup" = None):
        "Awaitable to remove a popup. If None, will default to popup currently on top"
        if popup == None and self.popupsOnTop:
            popup = self.popupsOnTop[-1]
        
        if not popup:
            _LOGGER.warning("There is currently no popup on top, cannot remove")
            return
        
        await self.__async_remove_element(popup)
        self.refresh()
        if popup in self.popupsOnTop:
            self.popupsOnTop.remove(popup)

    @elementactionwrapper.method
    def show_popup(self, popup_id: str):
        """
        Print a popup on top of the screen

        Parameters
        ----------
        popup_id : Union[str, &quot;elements.Popup&quot;]
            The id of the popup (or if you're cheeky the popup itself)
        """
        if isinstance(popup_id, str):
            if popup_id in self.popupRegister:
                popup = self.popupRegister[popup_id]
            elif popup_id in self.elementRegister and isinstance(self.elementRegister[popup_id], elements.Popup):
                popup = self.elementRegister[popup_id]
            else:
                _LOGGER.warning(f"No popup with popupId {popup_id} is registered")
                return
        else:
            popup = popup_id

        asyncio.run_coroutine_threadsafe(popup.async_show(), 
                                        self.mainLoop)
    #endregion

    #region Interaction Functions
    def start_screen_printing(self):
        "Starts printing the screen. This function is blocking, use async_start_screen_printing if that is not desired."
        
        assert not self.mainLoop.is_running(), "main loop should not be runnning yet"
        return self.mainLoop.run_until_complete(self.async_start_screen_printing())

    async def async_start_screen_printing(self):
        """
        Indicates the device has started printing to the screen. 
        Starts updating device features periodically.
        Also starts listinging for user input if the device is capable of that.

        Parameters
        ----------
        grabInput boolean:
            Do an EVIOCGRAB IOCTL call to prevent any other software from registering touch events (Not implemented everywhere)
        """
        
        assert asyncio.get_running_loop() == self.mainLoop, "Screen printing should be starting in the screen loop"
        
        _LOGGER.info("Starting Screen printing")

        coros = [self.update_device_states()]
        
        ##Works like this for now, but I think it's best to put this into a seperate function, and construct a gather using this and the device feature updater
        if self.device.has_feature(FEATURES.FEATURE_INTERACTIVE):
            coros.append(self.async_touch_handler())
        else:
            coros.append(self.device.event_bindings())

        async with self._printLock:
            assert self._perform_element_attribute_check(), "Element pre-print checks failed"
            self.stop_batch_writing()
            for element in self.stack:
                _LOGGER.debug(f"Calling element {element} on_add")
                if hasattr(element,"on_add"):
                    if element.isLayout:
                        element.on_add(call_all = True)
                    else:
                        element.on_add()
            self._printGather = asyncio.gather(*coros, return_exceptions=True)
            try:
                await self._printGather
            except asyncio.CancelledError as exce:
                _LOGGER.debug("PSSM printLoop has been cancelled")

    async def async_touch_handler(self):
            "Starts up the touch handler and waits for it."
            if not self.device.has_feature(FEATURES.FEATURE_INTERACTIVE):
                _LOGGER.error("Device is does not support interaction.")
                raise InteractionError()
            
            self.interactQueue = asyncio.Queue()
            asyncio.create_task(self.device.event_bindings(self.interactQueue))
            _LOGGER.debug("Touch handles has started")
            await asyncio.sleep(0)

            if self.device.has_feature(FEATURES.FEATURE_PRESS_RELEASE):
                await self.__async_touch_handler(self.interactQueue)
            else:
                await self.__async_simple_touch_handler(self.interactQueue)
            
    async def __async_simple_touch_handler(self, queue: asyncio.Queue):
        "Handles devices that only support taps and optionally long presses."
        while self.printing:
            event: tools.TouchEvent = await queue.get()
            self._interactEvent.clear()

            if event.touch_type == const.TOUCH_TAP:
                asyncio.create_task(self._async_interact_handler(event.x,event.y, "tap"))
            elif event.touch_type == const.TOUCH_LONG:
                asyncio.create_task(self._async_interact_handler(event.x,event.y, "hold"))
            
            await asyncio.sleep(0)
            self._interactEvent.set()

    async def __async_touch_handler(self, queue: asyncio.Queue):
            "Handles devices that can report on touch and release"

            ##Replace this with a setting for the device.
            debounce_time = self.__touchDebounceTime
            min_hold_time = self.__minimumHoldTime
            while self.printing:
                event: tools.TouchEvent = await queue.get()

                if event.touch_type != const.TOUCH_PRESS:
                    continue
                
                release_task = asyncio.create_task(coro=queue.get())
                done, _ = await asyncio.wait([release_task], timeout=debounce_time)
                if done:
                    ##Should not have received a second touch before the debounce time elapsed
                    _LOGGER.debug("Touch Debounced")
                    continue

                self._interactEvent.clear()
                done, _ = await asyncio.wait([release_task], timeout=min_hold_time)

                if done:
                    event = release_task.result()
                    asyncio.create_task(self._async_interact_handler(event.x,event.y, "tap"))
                else:
                    asyncio.create_task(self._async_interact_handler(event.x,event.y, "hold"))
                    event = await release_task
                    asyncio.create_task(self._async_interact_handler(event.x,event.y, "hold_release"))
                    ##Will maybe make a NamedTuple to pass instead of coords and action seperately?
                _LOGGER.debug(f"Click at {(event.x,event.y)} dispatched")
                
                self._interactEvent.set()

            _LOGGER.warning("Touch listener has stopped")

    async def _async_interact_handler(self, x : int, y : int, action: TouchActionType):
        """
        Handles clicks. Builds a list of coroutines and awaits on them in a gather call.

        Parameters
        ----------
        x : int
            x coordinate
        y : int
            y coordinate

        Raises
        ------
        res
            _description_
        """
        _LOGGER.verbose("Handling a click")
        n = len(self.stack)
        coro_list = []
        self._lastCoords = (x,y)

        if self.backlight_behaviour == "On Interact":
            coro_list.append(self.temporary_backlight_async())

        if self.on_interact:        
            try:
                if asyncio.iscoroutinefunction(self.on_interact):
                    coro_list.append(self.on_interact(**self.on_interact_data, screen = self, coords = InteractEvent(x,y, action)))
                else:                    
                    coro_list.append(asyncio.to_thread(self.on_interact, **self.on_interact_data, **{"screen": self, "coords":  InteractEvent(x,y, action)}))
                _LOGGER.verbose("Added screen interact function to click coro list")
            except (TypeError, KeyError, IndexError, OSError) as exce:
                _LOGGER.error(f"adding on_interact function {self.on_interact} raised exception: {exce}")
            
            _LOGGER.debug("Passed on_interact")
        else:
            _LOGGER.debug("on_interact is False")
        
        if self.popupsOnTop:
            _LOGGER.verbose("Passing click to the popup on top")
            popup = self.popupsOnTop[-1]
            if tools.coords_in_area(x, y, popup.area):
                for p in self.popupsOnTop:
                    p._tapEvent.set()

                coro_list.extend(
                    await self._dispatch_click_to_element(InteractEvent(x,y, action), popup))
            elif x == -1 and y == -1:
                for p in self.popupsOnTop:
                    p._tapEvent.set()
            else:
                for p in self.popupsOnTop:
                    if tools.coords_in_area(x,y,p.area):
                        p._tapEvent.set() 
                    elif action != "hold_release":
                        ##Prevents popups being opened via a hold_action to not appear if the click is outside their area
                        await self._interactEvent.wait()
                        await asyncio.sleep(0)
                        coro_list.append(p.async_close())
        else:
            for i in range(n):
                j = n-1-i   # We go through the stack in descending order
                elt = self.stack[j]
                if elt.area is None:
                    # An object without area, it should not happen, but if it does,
                    # it can be skipped
                    continue

                if tools.coords_in_area(x, y, elt.area):
                    if hasattr(elt,"tap_action") and elt != None:
                        _LOGGER.verbose("Got element with tap_action")
                        coro_list.extend(
                            await self._dispatch_click_to_element(InteractEvent(x,y, action), elt) )
                        _LOGGER.debug("tap_action added to coro list")
                        break

        _LOGGER.debug(f"There are {len(coro_list)} coros in the list")
        if coro_list:
            _LOGGER.verbose("Going to await coro list")
            L = await asyncio.gather(*coro_list, return_exceptions=True)
            for i, res in enumerate(L):
                if isinstance(res,Exception): 
                    _LOGGER.error(f"{coro_list[i]} returned an exception: {res} ")
                    if const.RAISE: raise res
            _LOGGER.verbose(f"Click  {x,y} coroutine gather returned with {L}")
            
    def __stop_printing(self):
        "This is not implemnted (And should probably not be used?)"
        self.__printing = False
        self.device.isInputThreadStarted = False
        _LOGGER.warning("[PSSM - Touch handler] : Input thread stopped")

    async def _dispatch_click_to_element(self, interaction: InteractEvent, elt: "elements.Element") -> list[Coroutine]:
        """
        Once given an object on which the user clicked, this function returns a list with coroutines to put into an asyncio.gather
        (ie elt.onclickInside or elt._dispatch_click)
        It also handles element feedback
        """
        coro_list = []
        if elt == None:
            return []

        x,y, action = interaction

        elt_action = elt._get_action(action)
        if isinstance(elt,elements.Layout):
            if elt_action:
                func, kwargs = elt_action
                if asyncio.iscoroutinefunction(func):
                    coro_list.append(
                        func(elt, interaction, **kwargs))
                else:                    
                    coro_list.append(
                        asyncio.to_thread(
                            func,elt, interaction,**kwargs))
                    
            if elt.show_feedback:
                coro_list.append(
                    elt.feedback_function())

            coro_list.extend( 
                await elt._dispatch_click(interaction))

        else:
            if elt.show_feedback:
                coro_list.append(
                    elt.feedback_function())
            
            if elt_action:
                func, kwargs = elt_action
                if asyncio.iscoroutinefunction(func):
                    coro_list.append(
                        func(elt, interaction, **kwargs))
                else:
                    try:
                        coro_list.append(
                                asyncio.to_thread(func,elt, interaction,**kwargs))
                    except (TypeError, KeyError, IndexError, OSError) as exce:
                        msg = f"Something went wrong in {elt} tap_action {elt.tap_action}: {exce}"
                        _LOGGER.error(msg)
                
        _LOGGER.verbose(f"Returning coro list of size {len(coro_list)}")
        return coro_list
    
    
    #endregion

    #region device methods
    async def update_device_states(self):
        """
        Calls the required methods on the device to update states like the network and battery, if the device has those.
        """

        async def monitor_backlight():
            condition = self.device.backlight._updateCondition
            while self.printing:
                try:
                    async with condition:
                        await condition.wait()
                        async with self.deviceUpdateCondition:
                            self.deviceUpdateCondition.notify_all()
                except asyncio.CancelledError:
                    break

        if self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self.mainLoop.create_task(monitor_backlight())

        while self.printing:
            try:
                await asyncio.sleep(self.pollSeconds)
                await self.device.async_pol_features()

                async with self.deviceUpdateCondition:
                    self.deviceUpdateCondition.notify_all()
            except asyncio.CancelledError:
                break

    @elementactionwrapper.method
    def set_background_image(self, background : Union[str, Path, ColorType, Image.Image], fit_method : Literal["contain", "cover", "crop", "resize"] = "cover", fit_arguments : dict = {}) -> bool:
        """
        Sets the screens background image to the provided image file, color, or Image object. 

        Parameters
        ----------
        background : Union[str, Path, ColorType, Image.Image]
            The new background to set. Can be any value that translates to a color, a path to an image file (Any file not starting with ./ will be looked for in the custom pictures folder).
            Can also be a PIL Image object.
        fit_method : Literal[&quot;contain&quot;, &quot;cover&quot;, &quot;crop&quot;, &quot;resize&quot;]
            Method to fit the image to the screen. \n
                Contain: makes the entire image fit on the screen, without changing the width/height ratio. Any leftover screen area is either filled up with the default screen color, or a color specified under 'color' in `fit_arguments`. \n
                Cover: size the image to the smallest size to cover the entire screen without changing the width/height ratio, and crop out anything that is too large. Cropping is generally centered, but can be set using 'centering' in `fit_arguments`\n
                Crop: Crops out a part of the image and resizes it to fit the screen area, without mainting the width/height ratio. Cropped out area defaults to the center area of the image that fits the screen. Otherwise, can be set using 'box' in `fit_arguments` (see documentation of `tools.fit_Image` for usage)\n
                Resize: resizes the entire image to fit the screen area, without maintaining width/height ratio.
        fit_arguments : dict, optional
            Arguments to pass to the fitting function, by default {}
            Some safety nets are in place to ensure each fitting function only gets passed the keywords that it accepts. However validity checks for the values of arguments are not performed.
            When using crop or resize, the box argument takes string values, aking to dimensional strings. In this case, `'w'` and `'h'` evaluate to the new width and height given in new_size. `'W'` and `'H'` evaluate to the width and height of the original img. \n
            For resize, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize \n
            For crop, see: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.crop \n
            For the other methods, see: https://pillow.readthedocs.io/en/stable/reference/ImageOps.html \n
            
        Returns
        -------
        bool
            True if the background was set succesfully, otherwise False (presumably)
        """        
        
        ##For contain: allow centering in the method arguments
        ##Crop is basically the same as resize but with the box argument --> Resize will then resize the whole image without arguments
        if background == None:
            background = self.device.defaultColor

        if background == "default":
            background = DEFAULT_BACKGROUND

        if not isinstance(background, Image.Image):
            if isinstance(background, (str,list,tuple)) and Style.is_valid_color(background):
                self.__background = background

                color = Style.get_color(background, self.imgMode)
                img = Image.new(self.imgMode, self.size, color)
                self.__backgroundImage = img
                return True
            elif (isinstance(background, (list,tuple))):
                msg = f"{background} could not be identified as a valid colour"
                _LOGGER.exception(msg)
                return False
            else:
                if isinstance(background, Path):
                    p = background
                else:
                    if background[0] == "/" or background[0:2] != "./":
                        p = CUSTOM_FOLDERS["picture_folder"] / background
                    else:
                        p = Path(background)
                
                if not p.exists():
                    msg = f"Background Image file {p} does not exist."
                    _LOGGER.error(msg)
                    return False

                img = Image.open(p)
                if img.mode != self.imgMode:
                    img = img.convert(self.imgMode)
                self.__background = background
        else:
            img = background

        method_args = {}
        if fit_method == "contain":
            if "color" in fit_arguments:
                if Style.is_valid_color(fit_arguments["color"]):
                    method_args["color"] = fit_arguments["color"]
            method_args.setdefault("color", self.device.defaultColor)
            if "centering" in fit_arguments: method_args["centering"] = fit_arguments["centering"]
            if "method" in fit_arguments: method_args["method"] = fit_arguments["method"]
        
        elif fit_method == "cover":
            if "bleed" in fit_arguments: fit_method["bleed"] = fit_arguments["bleed"]
            if "centering" in fit_arguments: method_args["centering"] = fit_arguments["centering"]
            if "method" in fit_arguments: method_args["method"] = fit_arguments["method"]
        
        elif fit_method == "crop":
            if "box" not in fit_arguments:
                method_args["box"] = ["0.5*(W-w)", "0.5*(H-h)", "0.5*(W+w)", "0.5*(H+h)"]
            else:
                method_args["box"] =  fit_arguments["box"]
        elif fit_method == "resize":
            if "box" in fit_arguments: method_args["box"] = fit_arguments["box"]
            if "resample" in fit_arguments: method_args["resample"] = fit_arguments["resample"]
            if "reducing_gap" in fit_arguments: method_args["reducing_gap"] = fit_arguments["reducing_gap"]

        img = tools.fit_Image(img, self.size, fit_method, method_args, force_size=True)

        self.__backgroundImage = img.copy()

        if self.printing:
            self.mainLoop.create_task(self.print_stack())
        return True

    @elementactionwrapper.method
    async def rotate(self, rotation : Optional[RotationValues] = None):
        """
        Rotates the screen. If rotation is None, will rotate 90 degrees clockwise.
        Does nothing if the device does not support rotation during runtime.

        Parameters
        ----------
        rotation : Optional[RotationValues], optional
            Orientation to rotate to, by default None 
        """        

        if not self.device.has_feature(FEATURES.FEATURE_ROTATION):
            return
        
        _LOGGER.info("Rotating screen")
        if rotation  != None:
            pass
        else:
            r_list : tuple = RotationValues.__args__
            idx = r_list.index(self.rotation) + 1
            if idx == len(r_list): idx = 0
            rotation = r_list[idx]                
        
        await self.device._rotate(rotation)

        SETTINGS["screen"]["rotation"] = rotation

        return

    async def _screen_resized(self):
        """
        Use this function when the device's screen size has changed (i.e. resizing in windowed mode, for example)
        It will regenerate the main element, and take care of updating any dimensional strings.
        After calling this, screen.print_stack() (or something else) will still need to be called in order to fully print the new configuration.
        """

        self.background = self.__background     
        ##Can't really remember why this is necessary
        ##But, at least in tkinter/windowed (which I think is the only real instance where this can be encountered), not having this causes the screen to stay black.
        ##It may actually be necessary to call the set_background_function to properly resize it

        if not self.stack:
            #This ensures the background is the right size -> but does not apply the settings etc. again
            #Maybe save a reference to that somewhere in the background setter, i.e. just a dict with the passed values such that it can be called again
            await self.print_stack()
            return

        for elt in self.stack:
            if elt.isPopup: 
                await elt.async_close()

        if self.mainElement.isGenerating:
            await self.mainElement._await_generator()

        self.mainElement._area = self.area

        for popup in self.popupRegister.values():
            if not popup.onScreen: popup.make_area()

        for elt in self.stack:
            await elt.async_update(forceGen=True, skipPrint=True)            

    def set_backlight_behaviour(self, option: Optional[Literal["Manual", "On Interact", "Always"]]):
        """
        Manual means it only turns on/off when called explicitly. On Interact means it turns on when interacting with the screen. Always means it is always on by default (can be turned on/off via functions). 
        Initial behaviour is set in configuration.yaml"
            Manual: only turn on/off when called explicitly
            On Interact: turn on when the screen registers a touch. Stay on for a set amount of time after the last registered touch
            Always: The backlight is on by default, but can be turned off (and back on) by calling the function.

        Parameters
        ----------
        option : Optional[Literal[&quot;Manual&quot;, &quot;On Interact&quot;, &quot;Always&quot;]]
            The behaviour option to set
        """

        if not self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            _LOGGER.warning(f"Device {self.device.name} does not support the backlight Feature")
            return

        value = option
        if value == None and self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            value = "Manual"
        
        if value == self.backlight_behaviour:
            return

        self.device.backlight._behaviour = value
        SETTINGS["device"][ "backlight_behaviour"] = value
        if value == "Always":
            self.device.backlight.turn_on()
        
        if self.mainLoop.is_running():
            asyncio.create_task(self.device.backlight.notify_condition())

    async def __async_temporary_backlight_task(self, time_on : Union[float,int] = None, brightness : int = None, transition : float = None):
        
        if time_on == None:
            time_on = self.backlight_time_on

        if not self.device.backlight.state or self.device.backlight.brightness != brightness:
            self.device.backlight.turn_on(brightness, transition)
        
        _LOGGER.verbose(f"Turning backlight off again in {time_on} seconds")
        

        try:
            await asyncio.sleep(time_on)  #@IgnoreException
            _LOGGER.verbose("Done sleeping, turning off backlight")
            self.device.backlight.turn_off(transition)
        except asyncio.CancelledError:
            pass
        finally:
            return

    def temporary_backlight(self, time_on : float = None, reset : bool = True, brightness : int = None, transition : float = None, *args, **kwargs):
        """
        Turns on the backlight and turns it off again after time_on. If reset is true, the timer will reset each time the function is called

        Parameters
        ----------
        time_on : float, optional
            time the backlight will stay on, by default None (Which will default to `screen.backlight_time_on`)
        reset : bool, optional
            Set to true to restart the timer if it is already running, by default True
        brightness : int, optional
            The brightness to set the backlight to, by default None (Translates to `backlight.defaultBrightness`)
        transition : float, optional
            The time it will take (approximately) to transition to `brightness`, by default None (Translates to `backlight.defaultTransition`)
        """
        asyncio.create_task(self.temporary_backlight(time_on, reset, brightness, transition))

    async def temporary_backlight_async(self, time_on : float = None, reset : bool = True, brightness : int = None, transition : float = None, *args, **kwargs): #backlight, time_on : float, reset : bool = True, brightness : int = None, transition : float = None):
        """
        Turns on the backlight and turns it off again after time_on. If reset is true, the timer will reset each time the function is called

        Parameters
        ----------
        time_on : float, optional
            time the backlight will stay on, by default None (Which will default to `screen.backlight_time_on`)
        reset : bool, optional
            Set to true to restart the timer if it is already running, by default True
        brightness : int, optional
            The brightness to set the backlight to, by default None (Translates to `backlight.defaultBrightness`)
        transition : float, optional
            The time it will take (approximately) to transition to `brightness`, by default None (Translates to `backlight.defaultTransition`)
        """
        if not self.lightupTask.done():
            if reset:
                _LOGGER.debug("Cancelling previous light up task")
                self.lightupTask.cancel()
            else: 
                return
        
        if self.device.backlight.state and brightness == None:
            brightness = self.device.backlight.brightness

        _LOGGER.debug(f"Temporarily turning on backlight for {time_on} seconds") 
        self._lightupTask = asyncio.create_task(self.__async_temporary_backlight_task(time_on, brightness, transition))

    async def toggle_backlight_tap_action(self, elt = None, coords = None, brightness : int = None, transition : float = None):
        """
        Helper function that can be used for elements to toggle the backlight, without interfering with the "on interact" setting of the backlight.
        """

        if not self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            _LOGGER.warning(f"Device {self.device} has no backlight feature")
            return

        if self.backlight_behaviour == "On Interact" and not self.device.backlight.state:
            await asyncio.sleep(0)
            if not self._lightupTask.done():
                return

        await self.device.backlight.toggle_async(brightness,transition)

