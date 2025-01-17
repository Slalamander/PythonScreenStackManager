"""
Module that contains elements that are specific to monitoring device conditions
"""

from abc import abstractmethod, ABC
import asyncio
from typing import TYPE_CHECKING, Literal, Optional, Union, TypedDict, Callable, Any
from types import MappingProxyType
from contextlib import suppress

from PIL import Image
import mdi_pil as mdi
from mdi_pil import mdiType

from .. import tools
from ..tools import DummyTask
from ..constants import FEATURES, FEATURE_ATTRIBUTES

from . import baseelements as base, compoundelements as comps
from .baseelements import _LOGGER, CoordType, classproperty, colorproperty, Style
from .constants import BatteryIconMapping, DEFAULT_BATTERY_STYLE, DEFAULT_NETWORK_STYLE, ColorType

if TYPE_CHECKING:
    from ..devices import PSSMdevice

class _DeviceMonitor(base.Element):
    """
    Base device monitor class. Provided base properties and function that wait for a device property to update, after which a function is called.
    Does not derive from Element, any child classes need a parent Element class too.

    Parameters
    ----------
    monitor_feature : Literal[&quot;battery&quot;, &quot;network&quot;, &quot;backlight&quot;]
        The device feature to monitor. 
    monitor_attribute : str
        the attribute of the monitored feature to watch
    """
    
    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["base.Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return base.Element.action_shorthands | {"device-feature-update": "feature_update"}

    def __init__(self, monitor_feature : Literal["battery", "network", "backlight"], monitor_attribute : str):
        
        self._monitorTask : asyncio.Task = DummyTask()
        "The task that awaits for a device attribute to update. Started when the element is added to the screen."

        if monitor_feature != None: 
            self.monitor_feature = FEATURE_ATTRIBUTES.get(monitor_feature,monitor_feature)
            self.__monitor = getattr(self.parentPSSMScreen.device, self.monitor_feature)

            val = getattr(self.monitor, monitor_attribute) ##throws an error if it doesn't have the attribute         
            self.monitor_attribute = monitor_attribute   

    @property
    def monitor(self) -> Union["PSSMdevice.Backlight", "PSSMdevice.Battery", "PSSMdevice.Network"]:
        "The object being monitored. Cannot be set. Set monitor feature instead"
        return self.__monitor
    
    @property
    def monitor_feature(self) -> Literal["battery", "network", "backlight"]:
        """The feature being monitored
        """
        return self.__monitor_feature

    @monitor_feature.setter
    def monitor_feature(self, value:Literal["battery", "network", "backlight"]):
        if not self.parentPSSMScreen.device.has_feature(value):
            _LOGGER.error(f"The linked device does not have the {value} feature")
            return
        
        value = FEATURE_ATTRIBUTES.get(value,value)
            
        self.__monitor = getattr(self.parentPSSMScreen.device, value)
        self.__monitor_feature = value

    @property
    def monitor_attribute(self) -> str:
        "The attribute of the feature being monitored"
        return self.__monitor_attribute
    
    @monitor_attribute.setter
    def monitor_attribute(self, value:str):
        if not hasattr(self.monitor, value):
            _LOGGER.error(f"The device {self.monitor_feature} does not have a {value} attribute")
            return
        self.__monitor_attribute = value

    def on_add(self):
        loop = self.parentPSSMScreen.mainLoop
        self._monitorTask = loop.create_task(self._monitor_device())

    async def _monitor_device(self):
        "Async function that awaits the device conditions notifications and updates the element when needed"
        
        condition : asyncio.Condition = self.parentPSSMScreen.deviceUpdateCondition
        testVal = getattr(self.monitor,self.monitor_attribute)
        asyncio.create_task(self.feature_update(testVal))

        while self.onScreen:
            with suppress(asyncio.CancelledError):
                async with condition:
                    await condition.wait_for(lambda : testVal != getattr(self.monitor,self.monitor_attribute))

                    testVal = getattr(self.monitor,self.monitor_attribute)
                    asyncio.create_task(self.feature_update(testVal))

    @abstractmethod
    async def feature_update(self, value):
        """Called when the the monitored value changes, or called manually to force an update.
        Passed is the new value of the monitored attribute.
        Can be accessed as a shorthand to forcibly update
        """
        return
                
class DeviceButton(_DeviceMonitor, base.Button):
    """Button that shows the state of a device feature.
    
    Updates automatically.

    Parameters
    ----------
    monitor_feature : Literal[&quot;battery&quot;, &quot;network&quot;, &quot;backlight&quot;]
        The feature to monitor. 
    monitor_attribute : str
        the attribute of monitored feature to display
    prefix : str, optional
        optional string to prefix to the attribute, by default ""
    suffix : str, optional
        optional string to append to the attribute, by default ""
    typing : type, str
        The type the monitored value is converted to, before applying the suffic and prefix. Can allow for removing e.g. trailing zeros. strings are evaluated to a type.
    """

    @property
    def _emulator_icon(cls): return "mdi:cellphone-text"
    
    def __init__(self, monitor_feature : Literal["battery", "network", "backlight"], monitor_attribute : str, prefix : str = "", suffix : str = "", typing : Optional[Union[type, str]] = None, **kwargs):
        
        _DeviceMonitor.__init__(self, monitor_feature=monitor_feature, monitor_attribute=monitor_attribute)
        base.Button.__init__(self, text=None, **kwargs)


        self.prefix = prefix
        "The text put in front of the state of the monitored feature"

        self.suffix = suffix
        "The text put in behind of the state of the monitored feature"
        
        self.typing = typing

        ##Here to initiate the text
        val = getattr(self.monitor, monitor_attribute)
        if self.typing != None:
            val = self.typing(val)
        self._Button__text = f"{self.prefix}{val}{self.suffix}"

    #region
    @property
    def text(self) -> str:
        "The text to display. Cannot be set for the DeviceButton."
        return self._Button__text
    
    @base.Button.text.setter
    def text(self, value):
        _LOGGER.warning("DeviceButton does not allow setting the text property directly")
    
    @property
    def typing(self) -> Optional[type]:
        "The type the monitored value is converted to, before applying the suffic and prefix. Can allow for removing e.g. trailing zeros. Set to None for no conversion"
        return self.__typing 
    
    @typing.setter
    def typing(self, value : Optional[Union[type, str]]):
        if value == None:
            self.__typing = None
            return

        if isinstance(value, str):
            try:
                value = eval(value)
            except NameError as exce:
                msg = f"Cannot convert {value} to a python type"
                _LOGGER.exception(TypeError(msg))
                return
        
        if not isinstance(value, type):
            msg = f"Cannot convert {value} to a python type. It evaluates as a {type(value)} (Should evaluate to type)"
            _LOGGER.exception(TypeError(msg))
        else:
            self.__typing = value
    #endregion

    async def feature_update(self, value):
        if self.typing != None:
            value = self.typing(value)

        new_text= f"{self.prefix}{value}{self.suffix}"
        self.screen.mainLoop.create_task(
            self.async_update({"_Button__text": new_text})
        )

_backlightDict = TypedDict("backlightDict", {"on": mdiType, "off": mdiType}, total=True) 

class DeviceIcon(_DeviceMonitor, base.Icon):
    """Icon element that can be linked to a device Feature, like for example showing the charge of the battery.

    Parameters
    ----------
    icon_feature : _type_, optional
        The device feature to monitor, or just an icon, by default "mdi:cog"
    badge_feature : Optional[Union[Literal[&quot;battery&quot;,&quot;network&quot;,&quot;backlight&quot;], mdiType]], optional
        Additional feature to monitor, and reflect in the icon badge, by default None
    battery_style : Literal[&quot;filled&quot;,&quot;bars&quot;], optional
        Styling for the icon reflecting the battery state, by default "filled"
    battery_icon_states : BatteryIconMapping, optional
        Specific icons to show when the battery is in said state, by default DEFAULT_BATTERY_STYLE
        states are: 'default', 'charging', 'discharging', 'full'
    network_style : Literal[&quot;lines&quot;,&quot;signal&quot;], optional
        Styling for the network icon (to reflect signal strength), by default DEFAULT_NETWORK_STYLE
    backlight_icons : _type_, optional
        Icons to reflect that state of the backlight, by default {"on": "mdi:lightbulb-on", "off": "mdi:lightbulb"}
    color_from_brightness : bool, optional
        color the icon based on the backlight brightness, by default True
    icon_states : dict, optional
        Additional styling options for the element mapping to the states of all possible device features, by default {}
    """   

    @property
    def _emulator_icon(cls): return "mdi:cellphone-information"

    def __init__(self, icon_feature : Union[Literal["battery","network","backlight"], mdiType] ="mdi:cog", badge_feature : Optional[Union[Literal["battery","network","backlight"], mdiType]] = None, 
                battery_style : Literal["filled","bars"] = "filled", battery_icon_states : BatteryIconMapping = DEFAULT_BATTERY_STYLE,
                network_style : Literal["lines","signal"] = DEFAULT_NETWORK_STYLE, 
                backlight_icons : _backlightDict = {"on": "mdi:lightbulb-on", "off": "mdi:lightbulb"}, color_from_brightness : bool = True,
                icon_states : dict = {}, ##give keys network, battery, backlight. Unordered so last key overwrites.
                tap_action = "show_client_popup",
                **kwargs):

        if tap_action == "show_client_popup" and "tap_action_data" not in kwargs:
            tap_action = {"action": "element:show-popup", "element_id": "device-menu"}

        base.Icon.__init__(self, icon = "mdi:cog", tap_action = tap_action, **kwargs)
        self.icon_feature = icon_feature 
        self.badge_feature = badge_feature
        
        self.battery_style = battery_style
        self.battery_icon_states : BatteryIconMapping = battery_icon_states

        self.network_style = network_style

        self.backlight_icons = backlight_icons
        self.color_from_brightness = color_from_brightness
    
        if icon_feature not in ({FEATURES.FEATURE_BATTERY, FEATURES.FEATURE_NETWORK, FEATURES.FEATURE_BACKLIGHT} | {"battery","network", "backlight"}):
            self._icon = icon_feature
        elif icon_feature in {FEATURES.FEATURE_BATTERY, "battery"}:
            self._icon = "mdi:battery"
        elif icon_feature in {FEATURES.FEATURE_NETWORK, "network"}:
            self._icon = "mdi:wifi-refresh"
        elif icon_feature in {FEATURES.FEATURE_BACKLIGHT, "backlight"}:
            self._icon = "mdi:lightbulb"
    
        self.icon_states = icon_states

        startAttributes = self.build_newAttributes()
        for attr, value in startAttributes.items():
            setattr(self,attr,value)
        
    #region
    @base.Icon.icon.setter
    def icon(self, value) -> Union[str,Image.Image]:
        "Status icon. Cannot be set here,  as it is taken care of by the element itself."
        if value != "mdi:cog": _LOGGER.warning("DeviceStatus does not allow setting the icon property directly")

    @property
    def monitor(self) -> "PSSMdevice":
        "Monitored feature. The device instance for Device Icons"
        return self.parentPSSMScreen.device

    @property
    def monitor_feature(self) -> list:
        "List with the strings of features being monitored"
        return self._monitor_features

    ##Not sure if a setter has to be applied here too
    @base.Icon.icon_color.getter
    def icon_color(self) -> ColorType:
        "Icon color. Returns the dynamic color due to backlight brightness if that setting is active"
        if self.icon_feature != "backlight" or self.color_from_brightness == False:
            return self._icon_color
        else:
            return self.get_brightness_color(self._icon_color)

    @base.Icon.badge_settings.getter
    def badge_settings(self) -> dict:
        "Settings applied to the badge. Alters correct coloring if the badge_feature is the backlight"
        if self.badge_feature != "backlight" or self.color_from_brightness == False:
            return self._badge_settings.copy()
        else:
            settings = self._badge_settings.copy()
            if "icon_color" in settings:
                color = settings["icon_color"]
            else:
                color = self._icon_color
            
            if "background_color" in settings:
                bg_color = settings["background_color"]
            else:
                bg_color = self.background_color

            new_color = self.get_brightness_color(color, bg_color)
            settings["icon_color"] = new_color

            return settings.copy()
    
    @property
    def icon_feature(self) -> str:
        "Either a direct icon, or a feature of the device to monitor"
        return self._icon_feature
    
    @icon_feature.setter
    def icon_feature(self, value):

        if self.screen.device.has_feature(value):
            self._icon_feature = FEATURES.get_feature_string(value)
            return
        else:
            self._icon = value
            self._icon_feature = value

    @property
    def badge_feature(self) -> str:
        "Either a direct icon, or a feature of the device to monitor"
        return self._badge_feature
    
    @badge_feature.setter
    def badge_feature(self, value):
        if value and not self.screen.device.has_feature(value):
            raise AttributeError(f"{self}: Device does not have feature {value}")
        elif value:
            self._badge_feature = FEATURES.get_feature_string(value)
        else:
            self._badge_feature = value

    @property
    def battery_style(self) -> Literal["filled","bars"]:
        "Style of the battery icons, i.e. the mdi icon to use. Uses one of either styles: mdi:battery-50 or mdi:battery-medium"
        return self._battery_style
    
    @battery_style.setter
    def battery_style(self, value):
        if value not in {"filled","bars"}:

            raise ValueError(f"{self}: battery_style must be one of 'filled' or 'bars")
        self._battery_style = value

    @property
    def network_style(self) -> Literal["lines","signal"]:
        "Style of the network icon. Signal shows the signal strength, if available. Styles look like mdi:wifi mdi:wifi-strength-1 "
        return self._network_style

    @network_style.setter
    def network_style(self, value):
        if value not in {"lines","signal"}:
            raise ValueError(f"{self}: network_style must be one of 'lines' or 'signal")
        self._network_style = value

    @property
    def backlight_icons(self) -> _backlightDict:
        "Icons to reflect the backlight state, dict with keys 'on' and 'off'"
        return self._backlight_icons
    
    @backlight_icons.setter
    def backlight_icons(self, value):
        if not "on" and "off" in value:
            raise KeyError(f"{self}: backlight_icons must have both an on and off key defined")
        self._backlight_icons = value

    @property
    def color_from_brightness(self):
        "color the icon based on the backlight brightness, by default True, but not implemented"
        return self._color_from_brightness
    
    @color_from_brightness.setter
    def color_from_brightness(self, value):
        self._color_from_brightness = bool(value)

    @property
    def icon_states(self) -> dict:
        "Additional styling options for the element mapping to the states of all possible device features, by default {}"
        return self._icon_states
    
    @icon_states.setter
    def icon_states(self, value):
        if not isinstance(value, (dict, MappingProxyType)):
            raise TypeError(f"{self}: icon_states must be a dict")
        self._icon_states = value
    #endregion

    def get_brightness_color(self, color : ColorType, background_color : Optional[ColorType]=None) -> tuple[int,int,int,int]:
        """Returns a new color based on the icon color, with it's transparency set depending on the brighntess of the backlight

        Parameters
        ----------
        color : ColorType
            The color of the icon at 100% brightness
        background_color : ColorType, None
            optional background color to take into account

        Returns
        -------
        tuple[int,int,int,int]
            The brightness altered color, as an RGBA tuple
        """
        min_alpha = 155
        alpha_mult = (255-min_alpha)/100

        if isinstance(color, bool):
            color = background_color if background_color != None else self.background_color
            if color == None:
                color = self.parentBackground

            new_color = tools.invert_Color(color, "RGBA")
        else:
            new_color = Style.get_color(color,"RGBA")
        
        new_color = list(new_color)
        alpha = min_alpha + round(self.monitor.backlight.brightness*alpha_mult)
        new_color[3] = alpha

        return new_color

    async def _monitor_device(self):
        condition = self.monitor.updateCondition
        ##Should rewrite these to use features.
        battery = getattr(self.monitor,"battery",None)
        network = getattr(self.monitor,"network",None)
        backlight = getattr(self.monitor,"backlight",None)

        asyncio.create_task(self.feature_update()) #Call the update function when starting
        while self.onScreen:
            try:
                async with condition:
                
                    if battery:
                        battLevel = battery.charge
                        battState = battery.state
                    if network:
                        connected = network.connected
                        wifiState = network.wifiOn
                        signal = network.signal

                    if backlight:
                        lightState = backlight.state
                        brightness = backlight.brightness

                    def condition_test():
                        ##Should automate this function I think, to take into account the features being monitored and be flexible with the features in general
                        conditions = []
                        if battery:
                            conditions.append(battLevel != battery.charge)
                            conditions.append(battState != battery.state)
                        
                        if network:
                            conditions.append(connected != network.connected)
                            conditions.append(signal != network.signal)
                        
                        if backlight:
                            conditions.append(lightState != backlight.state)
                            conditions.append(brightness != backlight.brightness)

                        return any(conditions)
                    
                    await condition.wait_for(condition_test)

                    asyncio.create_task(self.feature_update())
            except asyncio.CancelledError:
                break

    def generator(self, area=None, skipNonLayoutGen=False):
        return super().generator(area, skipNonLayoutGen)

    def build_newAttributes(self):
        "Gathers the new states of the device features and updates itself accordingly."
        ##Don't need to monitor if anything did change. This function is only called by monitor_device which means it needs to be updated anyhow
        _LOGGER.debug("Updating DeviceStatus Icon")
        newAttributes = {}
        if self.icon_feature == FEATURES.FEATURE_BATTERY:
            _icon = self.make_battery_icon()
        elif self.icon_feature == FEATURES.FEATURE_NETWORK:
            _icon = self.make_network_icon()
        elif self.icon_feature == FEATURES.FEATURE_BACKLIGHT:
            _icon = self.make_backlight_icon()
        else:
            _icon = self.icon_feature

        newAttributes["_icon"] = _icon

        if self.badge_feature == FEATURES.FEATURE_BATTERY:
            badge_icon = self.make_battery_icon()
        elif self.badge_feature == FEATURES.FEATURE_NETWORK:
            badge_icon = self.make_network_icon()
        elif self.badge_feature == FEATURES.FEATURE_BACKLIGHT:
            badge_icon = self.make_backlight_icon()
        else:
            badge_icon = self.badge_feature

        newAttributes["badge_icon"] = badge_icon

        iconDict = {}
        for key,states in self.icon_states.items():
            if key == "network":
                state = self.parentPSSMScreen.device.network.state
            elif key == "battery":
                state = self.parentPSSMScreen.device.battery.state
            else:
                continue

            if state in states:
                iconDict.update(states[state])
        newAttributes.update(iconDict)
        return newAttributes

    async def feature_update(self):
        newAttributes = self.build_newAttributes()
        asyncio.create_task(self.async_update(newAttributes))

    def make_battery_icon(self) -> Image.Image:
        """
        Makes the battery icon for the device status icon.
        Does not take arguments, uses the element attributes for.

        Returns
        -------
        Image.Image
            Battery image, build using mdi_pil.make_battery_icon
        """
        if self.screen.device.has_feature(FEATURES.FEATURE_BATTERY):
            charge = self.parentPSSMScreen.device.battery.charge
            state = self.parentPSSMScreen.device.battery.state
        else:
            charge = 0
            state = None
        batDict = {"style": self.battery_style}
        batDict.update(self.battery_icon_states.get("default", {}))
        batDict.update(self.battery_icon_states.get(state, {}))                
        return mdi.make_battery_icon(charge, **batDict)

    def make_network_icon(self) -> mdiType:
        if self.screen.device.has_feature(FEATURES.FEATURE_NETWORK):
            state = self.parentPSSMScreen.device.network.state
        else:
            state = "off"

        if self.network_style == "signal":
            base = "wifi-strength"
            if state == "off":
                wifiIcon = f"mdi:{base}-off-outline"
            elif state == "disconnected":
                wifiIcon = f"mdi:{base}-off"
            else:
                s = self.parentPSSMScreen.device.network.signal
                if s > 85:
                    wifiIcon = "mdi:wifi-strength-4"
                elif s > 60:
                    wifiIcon = "mdi:wifi-strength-3"
                elif s > 35:
                    wifiIcon = "mdi:wifi-strength-2"
                elif s > 10:
                    wifiIcon = "mdi:wifi-strength-1"
                else:
                    wifiIcon = "mdi:wifi-strength-outline"
        else:
            base = "wifi"
            if state == "off":
                wifiIcon = f"mdi:{base}-off"
            elif state == "disconnected":
                wifiIcon = f"mdi:{base}-remove"
            else:
                wifiIcon = f"mdi:{base}"
        return wifiIcon

    def make_backlight_icon(self, color=True) -> tuple[mdiType, ColorType]:
        
        state = self.monitor.backlight.state

        icon = self.backlight_icons["on"] if state else self.backlight_icons["off"]

        if state:
            icon = self.backlight_icons["on"]
        else:
            icon = self.backlight_icons["off"]
        
        icon

        if not self.color_from_brightness:
            color = self.icon_color
        else:
            min_alpha = 155
            alpha_mult = (255-min_alpha)/100

        ##Apparently this does not continue. Implement later maybe
        return icon
        

class BacklightSlider(_DeviceMonitor, comps.Slider):
    """A slider that controls the device's backlight.

    Not available on devices without the appropriate feature.

    Parameters
    ----------
    monitor_attribute : Literal[&quot;brightness&quot;, &quot;default_brightness&quot;], optional
        Either brightness or default_brightness, by default "brightness"
        If brightness, the brightness is directly changed to the new value
    """  

    @property
    def _emulator_icon(cls): return "mdi:brightness-percent"

    def __init__(self, monitor_attribute : Literal["brightness", "default_brightness"]= "brightness", **kwargs):

        comps.Slider.__init__(self,position=50, minimum=0, maximum=100, value_type=int, **kwargs)

        if not self.screen.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            raise FeatureError("BacklightSlider is only available for devices with a backlight Feature.")

        _DeviceMonitor.__init__(self,monitor_feature=None, monitor_attribute=monitor_attribute)
        
        self.tap_action = self._tap_action_backlight

        self.__monitor = self.parentPSSMScreen.device.backlight
        self.monitor_attribute = monitor_attribute

        pos = getattr(self.monitor, self.monitor_attribute)
        self.position = pos

    def generator(self, area=None, skipNonLayoutGen=False):
        return comps.Slider.generator(self,area, skipNonLayoutGen)

    #region
    @property
    def monitor(self) -> "PSSMdevice.Backlight":
        "The object being monitored. Cannot be set. Set monitor feature instead"
        return self.__monitor

    @property
    def monitor_feature(self) -> Literal["battery", "network", "backlight"]:
        "String with the device feature being monitored"
        return "backlight"
    
    @property
    def monitor_attribute(self) -> Literal["brightness", "default_brightness"]:
        "The attribute of the feature being monitored"
        return self.__monitor_attribute
    
    @monitor_attribute.setter
    def monitor_attribute(self, value:Literal["brightness", "default_brightness"]):
        if value not in ["brightness", "default_brightness"]:
            _LOGGER.error("BacklightSlider can only monitor brightness or default_brightness")
            return
        self.__monitor_attribute = value
        val = getattr(self.monitor, value)
        if self.onScreen:
            asyncio.create_task(self.feature_update(val))

    #endregion

    async def feature_update(self, value):
        newAttributes = {"position": value}

        ##Maybe it'll when cancelling this if the other task is running?
        asyncio.create_task(self.async_update(updateAttributes=newAttributes))

    async def _tap_action_backlight(self, elt, coords):
        
        ##Not fully sure why, but control needs to go back to the event loop twice, probaly due to some other await in the lightuptask?
        ##Anyhow this works, it only doesn't turn off anymore, but ill give an option for that.
        ##Also don't forget to implement the option for the default_brightness
        if self.monitor_attribute == "default_brightness":
            ##This changes the default brightness, which means the backlight (if it turns on by interact) will turn on to the new value
            ##Also changes if the backlight is already on since it restarts the task
            ##Should actually change that to prevent the brightness from changing constantly
            ##Simple to do by just passing the current value if it is already on.
            self.monitor.default_brightness = self.position
        else:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.parentPSSMScreen.lightupTask.cancel()
            await self.monitor.turn_on_async(self.position)

class FeatureError(AttributeError):
    "Thrown if the device does not have a certain feature"
    pass