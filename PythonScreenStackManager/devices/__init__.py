"""
Base device module for pssm devices. The `windowed` package is an out of the box, but relatively featureless, working example for desktop devices. 
"""

import asyncio
from typing import TYPE_CHECKING, TypedDict, Literal, Optional, Union
import logging
from functools import cached_property

from PIL import Image
from abc import ABC, abstractmethod
from contextlib import suppress

from .const import *

from ..tools import DummyTask, parse_duration_string

from ..pssm_settings import SETTINGS
from ..pssm_types  import *

_LOGGER = logging.getLogger(__name__)
_LOGGER.debug("Importing Base device")

background_color = "white"
foreground_color = "black"


if TYPE_CHECKING:
    from PythonScreenStackManager.pssm.screen import PSSMScreen
    import asyncio
    from ..pssm_types import ColorType


NetworkDict = TypedDict("NetworkDict",
                        {"connected": bool, "wifiOn":bool, "signal": str, "MAC": Optional[str], "SSID": Optional[str]})

class PSSMdevice(ABC):
    """
    The base PSSMdevice, use as a parent class when making new device platforms.
    Provides support to initialise the features linked to subclasses ('battery', 'network' and 'backlight')

    Parameters
    ----------
    Features : DeviceFeatureMap
        A dict with features this device supports. See DeviceFeatureMap. A value of boolean `True` indicates the device supports it.
    screenWidth : int
        The total width of the screen
    screenHeight : int
        The total height of the screen
    viewWidth : int
        The viewable width of the screen, i.e. taking into account any pixels obscured by bezels for example.
    viewHeight : _type_
        The viewable height of the screen, i.e. taking into account any pixels obscured by bezels for example.
    screenMode : str
        The image mode the final images send to the `print_pil` function should be in. See https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes, 
        Testing has only been done with "L" and "RGB", though the screenMode should not affect functionality as much.
    imgMode : str
        The image mode to construct images in. In general, I'd advice using 'RGBA' as it provides the best results, but the option is there for i.e. performance reasons. Not fully tested with other modes either.
    defaultColor : ColorType
        The default color of the device screen.
    name : str, optional
        Optional name for the device, by default "PSSM Device"
    """ 
    def __init__(self, features: DeviceFeatures, 
                screenWidth: int, screenHeight: int, viewWidth: int, viewHeight: int,
                screenMode: str, imgMode: str, defaultColor : "ColorType",
                name="PSSM Device"):

        _LOGGER.debug("Setting up base device")

        if not isinstance(features, DeviceFeatures):
            raise TypeError("features must be an instance of dataclass DeviceFeatures.")
        
        self._features = features

        ##Use this as a base function to test feature implementations
        if self.has_feature(FEATURES.FEATURE_POWER):
            if self.power_off.__module__ == __package__:
                raise AttributeError("A device with power features needs to define it's own power off function.")
            
            if self.reboot.__module__ == __package__:
                raise AttributeError("A device with power features needs to define it's own reboot function.")

        ##Features -> Move to inkBoard device
        self._screen_width = screenWidth
        self._screen_height = screenHeight
        if not viewWidth: viewWidth = screenWidth
        if not viewHeight: viewHeight = screenHeight

        self._viewWidth = viewWidth
        self._viewHeight = viewHeight
        self._screenMode = screenMode
        self._imgMode = imgMode
        if defaultColor == None:
            defaultColor = "white"
        self._defaultColor = defaultColor
        
        self._name = name
        self._deviceName = "Python Screen Stack Manager Windowed"

        if self.has_feature(FEATURES.FEATURE_ROTATION):
            ##This is here to ensure the rotation is set when initiating the device.
            self.rotation
        
        return

    #region Properties
    @property
    def deviceName(self) -> str:
        "The actual name of the device, as will be shown in the device menu."
        return self._deviceName

    @property
    def name(self) -> str:
        "The name of the device as set by the user."
        return self._name

    @cached_property
    def features(self) -> tuple[str]:
        """Returns a tuple with all the features the device has
        """
        features = []
        for feat, val in self._features._asdict().items():
            if val: features.append(feat)
        return tuple(features)

    @property
    def Screen(self) -> "PSSMScreen":
        "The Screen instance attached to the device"
        return self._Screen

    @property
    def parentPSSMScreen(self) -> "PSSMScreen":
        "The pssm screen objected associated with the device"
        return self._Screen

    @property
    def updateCondition(self) -> asyncio.Condition:
        """Asyncio condition that is notified when the device states updates have been called (so every config.device["update_interval"]), or when the backlight changed.
        
        For usage see: https://superfastpython.com/asyncio-condition-variable/#Wait_to_be_Notified
        """
        return self._updateCondition

    @property
    def path_to_pssm_device(self)-> int:
        "Path to the device file"
        return self._path_to_pssm_device
    
    @property
    def screenWidth(self)-> int:
        "Width of the screen"
        return self._screen_width
    
    @property
    def screenHeight(self)-> int:
        "Height of the screen"
        return self._screen_height

    @property
    def viewWidth(self)-> int:
        "Viewable width of the screen (taking into account possible bezels e.g.)"
        return self._viewWidth
    
    @property
    def viewHeight(self)-> int:
        "Viewable height of the screen (taking into account possible bezels e.g.)"
        return self._viewHeight
    
    @property
    def widthOffset(self) -> int:
        "Viewable height of the screen (taking into account possible bezels e.g.)"
        return self.screenWidth - self.viewWidth
    
    @property
    def heightOffset(self) -> int:
        "Viewable height of the screen (taking into account possible bezels e.g.)"
        return self.screenHeight - self.viewHeight

    @property
    def rotation(self) -> RotationValues:
        "The rotation of the screen"
        return self._rotation

    @property
    def defaultColor(self) -> "ColorType":
        "Default background color of the screen (i.e. pixels that are turned off.)."
        return self._defaultColor

    @property
    def isRGB(self) -> bool:
        "True if this device display in RGB"
        return  "RGB" in self.screenMode

    @property
    def colorType(self) -> str: #Image.ImageMode:
        "Same as screenMode. Implemented for legacy purposes"
        return  self._screenMode

    @property
    def screenType(self) -> Optional[Literal["LCD", "LED", "OLED", "E-Ink"]]:
        "If defined, the screen type of the device. List is not exhaustive."
        ##This needs to be set by the device class itself. Forwarding it to the base device is kinda unneccessary since in general it's not used.
        return getattr(self,"_screenType",None)

    @property
    def screenMode(self) -> str: #Image.ImageMode.ModeDescriptor:
        "Mode of the screen i.e. the mode a PILLOW image must be to be able to be displayed"
        return  self._screenMode

    @property
    def imgMode(self) -> Image.ImageMode:
        "Mode to initialise PILLOW images in for adequate building. Generally screenmode + A"
        return self._imgMode

    @property
    def eventQueue(self) -> "asyncio.Queue":
        "The queue where touch events are put into. Set by PSSM and defined in event_bindings."
        return self._eventQueue

    @property
    def last_printed_PIL(self) -> Image.Image:
        "Image that was last printed"
        #This should not be a copy, since otherwise the image just stays the same when printing
        return self._last_printed_PIL
    
    @last_printed_PIL.setter
    def last_printed_PIL(self, value : Image.Image):
        if not isinstance(value,Image.Image):
            _LOGGER.error(f"last_printed_PIL must be a pillow image instance. {value} is not")
            raise ValueError
        
        self._last_printed_PIL = value
    
    @property
    def network(self) -> "Network":
        "The instance of the network of the device."
        return self._network
    
    @property
    def backlight(self) ->  "Backlight":
        "The instance of the backlight of the device."
        return self._backlight
    
    @property
    def battery(self) -> "Battery":
        "The Battery level and status of the device."
        return self._battery
    #endregion

    #region methods
    def _set_screen(self):
        """Called after the device has been passed to a Screen instance.

        This method sets the screen property. Can be used to set additional settings, or register shorthand functions.
        ScreenInstance is the running PSSMScreen instance.
        """
        #When overwriting this, calling the super() function first is adviced
        #Also backlight shorthands are registered by the screen itself, so those do not need to be done.
        #Setting the attribute will in the furure likely be handled by the screen itself

        return

    def has_feature(self, feature: str) -> bool:
        """Returns true if the device has this feature (i.e. is it true in device.Features)
        
        Parameters
        ----------
        feature: str
            The  feature to check. Use the constants from `FEATURES` to check, although some safeguarding is in place to convert passed values to valid feature strings.
        """        
        with suppress(AttributeError):
            feature = FEATURES.get_feature_string(feature)

        return bool(getattr(self._features,feature,False))
    
    @abstractmethod
    async def async_pol_features(self):
        """This method takes care of polling and updating all necessary features.

        The ScreenInstance takes care of requesting this and notifying the update condition.
        This function should ensure that all necessary features are up to date when it returns.
        If the device has the Backlight feature, this does not need to be polled, as it has it's own condition, which the screen connects to the deviceUpdateCondition. 
        """
        return

    @abstractmethod
    def print_pil(self, imgData : Image.Image,x:int,y:int,isInverted=False):
        """Prints a pillow image onto the screen at the provided coordinates. 

        Ensure the mode of the pillow image matches that of the screen.

        Parameters
        ----------
        imgData : Image.Image
            the image object to be printed
        x : int
            x coordinates on the screen where the top left corner of the image will be placed.
        y : int
            y coordinates on the screen where the top left corner of the image will be placed.
        isInverted : bool, optional
            use hardware invertion on the printed area, by default False (E-reader leftover)
        """
        pass

    def do_screen_refresh(self, isInverted=False, isFlashing=True, isInvertionPermanent=True, area=[(0,0),("W","H")], useFastInvertion=False):
        """DEPRECATED
        Refreshes the screen. On ereaders, this can help get rid of ghosting.
        """
        # args:
        #     isInverted (bool): invert the screen area
        #     isFlashing (bool): flash the screen on refresh
        #     isInvertionPermanent (bool): permanently invert this area
        #     area (list[(x,y),(w,h)]): area to refresh. Defaults to the entire screen.
        #     useFastInversion (bool): perform a fast invertion of this area.
        ##This function is a leftover from the pure Eink version. Will be deprecated
        _LOGGER.debug("This base device function is deprecated")
        pass

    def do_screen_clear(self):
        "Completely clears the screen"
        _LOGGER.debug("This base device function is deprecated")

    async def _rotate(self, rotation : RotationValues):
        """Rotates the screen. 
        
        Check the device features to see if this is possible during runtime.
        Called via screen.rotate(), since there are some software things that need to happen too to reprint the screen correctly.
        
        Parameters
        ----------
        rotation : UR, CW, UD, CCW, optional
            The rotation to set the screen to.
        """
        if not self.has_feature(FEATURES.FEATURE_ROTATION):
            _LOGGER.error(f"Device platform {self.platform} does not support rotation during runtime")
        else:
            _LOGGER.warning(f"Device platform {self.platform} seems to support rotation during runtime but it is not implemented")
        ##When writing a function for this, do not forget to write the new value to the SETTINGS variable too, so that it can be saved if so desired.

    @abstractmethod
    async def event_bindings(self, touch_queue : "asyncio.Queue" = None):
        """async function that starts the print loop on the device as well the touch listerner, if able to.

        Parameters
        ----------
        touch_queue : asyncio.Queue, optional
            asyncio queue where touch events are put into. PSSM waits for items in this queue, by default None (for non interactive devices)
        grabInput : bool, optional
            Prevent any other software from listening to touched, by default False. Not implemented for every device.
        """
        pass

    def power_off(self,*args):
        "Powers off the device. Does nothing if the device does not support the power feature."
        _LOGGER.warning("Device does not support power off. Saving Settings though.")
        self.parentPSSMScreen.save_settings()
        return
    
    def reboot(self,*args):
        "Reboots the device. Does nothing if the device does not support the power feature."
        _LOGGER.warning("Device does not support rebooting")
        self.parentPSSMScreen.save_settings()
        return
    
    def toggle_autostart(self,*args):
        "Toggles autostart. Logs a warning if not implemented"
        _LOGGER.warning("Device does not support the autostart feature")
        ##For the validation: also test if it has the autoStart attribute.
        return

    def _quit(self):
        """"This function is called by pssm when the quit function is called.

        Use it to save any device specific settings or perform other tasks that need doing before quitting. May also be called in power_off/reboot
        """

    #endregion

#region subclasses

class BaseDeviceFeature(ABC):
    """Base class for device features that require a class
    """

    @abstractmethod
    def __init__(self):
        return
    
    @abstractmethod
    def get_feature_state(self) -> dict:
        """Creates a state dict for the feature

        It should return the value of any properties that can update dynamically

        Returns
        -------
        dict
            A dict with the feature's attributes and current value
        """        
        return
    
    def is_feature_updated(self, state_dict: dict) -> bool:
        """Returns if the passed ``state_dict`` is up to date

        ``state_dict`` does not have to be a complete dict of the feature state,
        but it should only contain keys actually present in the feature state.

        Parameters
        ----------
        state_dict : dict
            dict with the currently known states

        Returns
        -------
        bool
        """

        ##may need to check if this works like this, or if the comparison tests the object itself
        current_state = self.get_feature_state()
        for key, val in state_dict.items():
            if current_state[key] != val:
                return True
        return False



class Network(BaseDeviceFeature):
    '''Base class to get information on a device's network.

    Gets IP Adress, network SSID etc.
    Properties: IP, wifiOn, connected, SSID
    '''

    @abstractmethod
    def __init__(self, device : "PSSMdevice"):
        ##Should be replaced, init should call whatever methods get the ip adress etc.
        self._device = device
        _LOGGER.verbose("Setting up base device network class")

    #region Network properties            
    @property
    def state(self) -> networkconnectionstates:
        "State of the wifi radio. Shorthand to combine connected and wifiOn"
        if self.wifiOn:
            state = "connected" if self.connected else "disconnected"
        else:
            state = "off"
        return state
    
    @property
    def IP(self) -> str:
        """Returns the IP adress"""
        return self._IP

    @property
    def wifiOn(self) -> bool:
        """Returns whether wifi is on"""
        return self._wifiOn

    @property
    def connected(self) -> bool:
        """Returns whether the device is connected to a wifi network"""
        return self._connected

    @property
    def signal(self) -> Optional[int]:
        "Wifi signal percentage, from 0-100, or None if unavailable."
        return self._signal

    @property
    def SSID(self) -> Union[str,None]:
        """Returns the SSID of the connected network.
        None if not connected"""
        return self._SSID

    @property
    def macAddress(self) -> str:
        """Returns the mac adress of the device"""
        return self._macAddr

    #endregion

    def get_feature_state(self) -> networkstate:
        """Returns the currently known state of the network feature

        This is a dict with the properties that can change during runtime.

        Returns
        -------
        dict
            The state dict
        """

        state = {
            "state": self.state,
            "IP": self.IP,
            "wifiOn": self.wifiOn,
            "connected": self.connected,
            "signal": self.signal,
            "SSID": self.SSID
        }
        ##Not including the mac address as it does not change anyways
        return state

    @abstractmethod
    async def async_update_network_properties(self):
        "Method that updates the networks properties"
        pass


class Backlight(BaseDeviceFeature):
    '''Baseclass to control a device's backlight, screen brightness and the like.

    The backlight of the device. Provides callbacks to the state, and functions to turn on, off, or toggle it. Upon initialising this class, the light will be set to 0 to ensure the level is correct.
    It should also allow setting the default transition values and the default brightness, although the screen instance will be in charge of managing those.

    Depending on how the device handles, either ``turn_on`` or ``turn_on_async`` should be defined, and the other can simple call the defined function. But be careful with blocking the event loop.
    To keep connected elements in synch with the backlight's state, whenever it is updated the ``notify_condition`` function can be awaited, which will ensure all elements are notified of the new state.    
    '''
    def __init__(self, device: "PSSMdevice", default_brightness : int = 50, default_transition : float = 0):
        ##Ensuring the backlight is off when the dashboard starts, so the brightness and state are correct
        _LOGGER.verbose("Setting up base device backlight class")
        self._updateCondition = asyncio.Condition()
        """
        Asyncio condition that updates when the backlight changes.
        When developing new devices: condition is automatically notified when the default transition/brightness changes. However changing the state or brightness requires should implement _updateCondition.notify_all() at a point that is deemed best (Generally: not while transitioning, only when desired brightness values are reached)
        (Easiest way to do this is to have a transition function in which the actual transition is awaite, and have turn on/off call that waiting function. )
        """
        self._device = device
        "The device instance"

        self._transitionTask : asyncio.Task = DummyTask()
        "Task that tracks if the backlight is currently transitioning."

        self._behaviour = SETTINGS["device"]["backlight_behaviour"]
        self.default_time_on = SETTINGS["device"]["backlight_time_on"]

        self.default_transition = default_transition
        self.default_brightness = default_brightness

        self._lightLock = asyncio.Lock()
        "Lock that is meant to prevent multiple functions setting the light state at the same time."

    #region
    @property
    def brightness(self) -> int:
        """The brightness of the backlight (0 - 100)"""
        ##Maybe switch this to 0-255? Or at least make a brightness percentage setting
        return self._level

    @property
    def state(self) -> bool:
        """The state (on/off) of the backlight as a boolean (True/False)"""
        return True if self._level > 0 else False

    @property
    def default_brightness(self) -> int:
        """The default brightness to turn the backlight on to"""
        return self.__default_brightness

    @default_brightness.setter
    def default_brightness(self, value : int):
        if value >= 0 and value <= 100:
            self.__default_brightness = value
            SETTINGS["device"]["backlight_default_brightness"] = value
            with suppress(RuntimeError):
                asyncio.create_task(self.notify_condition())
        else:
            _LOGGER.error("Default brightness must be between 0 and 100")

    @property
    def minimumLevel(self) -> int:
        """The minimum backlight/brightness level to turn the backlight on at. 

        I.e., if this value is 30, turning on the backlight at 1 will be the same brightness as having this value at 0 and turning it on at 30 brightness.
        Not yet implemented.
        """
        return 0

    @property
    def default_transition(self) -> DurationType:
        """The default transition time (in seconds)"""
        return self.__default_transition

    @default_transition.setter
    def default_transition(self, value : float):
        
        value_secs = parse_duration_string(value)

        if value_secs >= 0:
            self.__default_transition = value_secs
            SETTINGS["device"]["backlight_default_transition"] = value
            asyncio.create_task(self.notify_condition())
        else:
            _LOGGER.error("Default transition time must be 0 or larger")

    @property
    def behaviour(self) -> backlightbehaviours: #Literal["Manual", "On Interact", "Always"]:
        """Backlight behaviour. 
        Since it affects screen interaction, you can set this via the parent screen (set_backlight_behaviour).
        """
        return self._behaviour

    @property
    def default_time_on(self) -> Union[float,int,str]:
        "Default  time to turn the backlight on for when calling the temporary backlight function. Controlled by parent screen"
        return self.__default_time_on
    
    @default_time_on.setter
    def default_time_on(self, value):

        if not isinstance(value, (float,int, str)):
            msg = f"{value} is not a numerical value"
            _LOGGER.error(TypeError(msg))
            return
        
        s = parse_duration_string(value)

        if s == None:
            return

        if s < 0:
            s = 0
        
        SETTINGS["device"]["backlight_time_on"] = value
        self.__default_time_on = value

        self._default_seconds_on : Union[int,float] = s
        "Default time on in seconds. Set automatically when setting default_time_on"
        with suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.notify_condition())
    #endregion

    def get_feature_state(self) -> backlightstate:
        """Returns the currently known state of the backlight feature

        This is a dict with the properties that can change or be set.
        It returns the properties ``state``, ``brightness``, ``behaviour``, ``default_time_on``, ``default_brightness`` and ``default_transition``

        Returns
        -------
        dict
            The state dict
        """

        state = {
            "state": self.state,
            "brightness": self.brightness,
            "behaviour": self.behaviour,
            
            "default_time_on": self.default_time_on,
            "default_brightness": self.default_brightness,
            "default_transition": self.default_transition
        }
        return state

    async def notify_condition(self):
        """Acquires the lock and notifies all awaiting on _updateCondition
        """           
        async with self._updateCondition:
            self._updateCondition.notify_all()

    @abstractmethod
    def turn_on(self, brightness : int = None, transition : float = None):
        """Turn on the backlight to the set level

        Parameters
        ----------
        brightness : int, optional
            brightness (0-100) to set the light to, by default None
        transition : float, optional
            transition time (in seconds) to take to get to brightness (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass
    
    @abstractmethod
    async def turn_on_async(self, brightness : int = None, transition : float = None):
        """Async method for turning on the backlight to the set level

        Parameters
        ----------
        brightness : int, optional
            brightness (0-100) to set the light to, by default None
        transition : float, optional
            transition time (in seconds) to take to get to brightness (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass

    @abstractmethod
    def turn_off(self, transition : float = None):
        """Turns off the backlight to the set level

        Parameters
        ----------
        transition : float, optional
            transition time (in seconds) to take fully turn off (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass
    
    @abstractmethod
    async def turn_off_async(self, transition : float = None):
        """Async method for turning off the backlight

        Parameters
        ----------
        transition : float, optional
            transition time (in seconds) to take fully turn off (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass

    @abstractmethod
    def toggle(self, brightness : int = None, transition : float = None):
        """Toggles the backlight, if it is off turns on to defined brightness

        Parameters
        ----------
        brightness : int, optional
            brightness (0-100) to set the light to if it is off, by default None
        transition : float, optional
            transition time (in seconds) to take to get to brightness or turn off. (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass

    @abstractmethod
    def toggle_async(self, brightness : int = None, transition : float = None):
        """Async method for toggling the backlight, if it is off turns on to defined brightness

        Parameters
        ----------
        brightness : int, optional
            brightness (0-100) to set the light to if it is off, by default None
        transition : float, optional
            transition time (in seconds) to take to get to brightness or turn off. (Ereaders are slow, so be aware that it will likely take longer), by default None
        """
        pass

class Battery(BaseDeviceFeature):
    '''Base class for interfacing with a battery.

    The battery of the device. Provides callbacks to get the battery state and charge level, as well as update it.
    '''
    def __init__(self, device : "PSSMdevice", charge : int, state: batterychargingstates):
        """
        Parameters
        ----------
        charge : int
            the initial charge level
        state : Literal["full","charging","discharging"]
            the initial battery state
        """
        _LOGGER.debug("Setting up base device battery class")
        self._device = device
        self._batteryCharge = charge
        self._batteryState = state

    @property
    def charge(self) -> int:
        """The battery charge, in percentage (from 0 - 100)"""
        return self._batteryCharge
    
    @property
    def state(self) -> batterychargingstates:
        """The state of the battery
        """
        return self._batteryState

    def get_feature_state(self) -> batterystate:
        """Returns the currently known state of the battery feature

        This is a dict with the battery's state and charge level

        Returns
        -------
        dict
            The state dict
        """
        return {"state": self.state, "charge": self.charge}

    def update_battery_state(self):
        """
        Updates the battery state and percentage. Check device if it returns anything.
        """
        self._device.Screen.mainLoop.create_task(self.async_update_battery_state())

    @abstractmethod
    async def async_update_battery_state(self)-> tuple[int,str]:
        """
        Update the battery state. Returns the result.

        Returns
        -------
        tuple[int,str]
            Tuple with [charge percentage, state]
        """
        pass

    def _update_properties(self, battery_state: tuple[int,str]):
        "Use this to update the battery properties (charge and state) after updating updating the state"
        self._batteryCharge = battery_state[0]
        if battery_state[1] in allowedBatteryStates:
            self._batteryState = battery_state[1]
        else:
            _LOGGER.warning(f"{battery_state[1]} is not a valid value for the batteryState")
#endregion

class BaseDeviceFunctionError(Exception):
    "Raise when a function is called on the base device"
    def __init__(self, message):
        super(BaseDeviceFunctionError, self).__init__(message)
