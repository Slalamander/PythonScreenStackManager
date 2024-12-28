"""
    Some popups that show a general menu.
    Each menu is unique, i.e. while it can be shown from multiple actions, you cannot define multiple version of it.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Literal, Optional, Union
from types import MappingProxyType

from mdi_pil import MDI_VERSION

from ..import tools
from ..tools import Singleton
from ..pssm_types import *
from ..constants import FEATURES

from .constants import DEFAULT_FONT_BOLD
from . import baseelements as base
from . import compoundelements as comps
from . import deviceelements as develts
from . import layoutelements as layouts
from .constants import INKBOARD, DEFAULT_MENU_BUTTON_COLOR, DEFAULT_FONT_BOLD, \
    DEFAULT_BACKGROUND_COLOR, DEFAULT_FOREGROUND_COLOR, DEFAULT_FONT_SIZE

from .baseelements import _LOGGER
if TYPE_CHECKING:
    from ..devices import PSSMdevice

class StatusBar(layouts.GridLayout):
    ##GridLayout cause: makes it easy to set orientation
    ##For space between icons and clock/data: use a None type and set the spacing to '?'
    ##Icon space is r anyways; Just figure out how to reliably get the rest in the right position

    ##Later on: allow users to add devicebuttons/info aside from the default button to here as well, i.e. battery or network status

    _statusbar_elements = {}

    @property
    def _emulator_icon(cls): return "mdi:credit-card-outline"

    @classproperty
    def statusbar_elements(cls) -> MappingProxyType[str, base.Element]:
        "The elements registered as statusbar elements"
        return MappingProxyType(cls._statusbar_elements)

    def __init__(self, orientation : Literal["horizontal","vertical"] = "horizontal", show_clock = True,
                outer_margins = [0, 10], inner_margins = [0,5], hide : list[str] = [], element_size : PSSMdimension = "default",
                element_properties : dict = {}, status_element_properties : dict = {"background_shape": "circle", "background_color": DEFAULT_BACKGROUND_COLOR},
                **kwargs):
        
        ##Considering the amount of things that shouldn't be set (i.e., no sizing etc.) Simply skip the gridLayout init and immediately go to base.Layout
        ##Don't forget to allow for setting inner and outer margins however
        ##And call build_layout

        if "ver" in orientation:
            clock_args = {"text_y_position": "bottom"}
        else:
            clock_args = {"text_x_position": "right"}
        self.__ClockElement = comps.DigitalClock(**clock_args)
        
        self.orientation = orientation
        self.show_clock = show_clock        ##putting this on True if the orientation is vertical is not recommended until rotating text elements in implemented
        self.outer_margins = outer_margins
        self.inner_margins = inner_margins
        self.hide = hide

        self.element_size = element_size
        self.element_properties = element_properties
        self.status_element_properties = status_element_properties

        base.Layout.__init__(self,None, **kwargs)

        self.build_layout()

    #region
    @property
    def elements(self) -> tuple["Element"]:
        "The elements registered in the statusbar"

        elt_list = []
        all_elts = self.statusbar_elements
        for elt_name in sorted(all_elts.keys()):
            if elt_name not in self.hide:
                elt_list.append(all_elts[elt_name])

        if self.show_clock:
            elt_list.append(self.__ClockElement)
        else:
            elt_list.append(None)
        return tuple(elt_list)

    @property
    def hide(self) -> set[str]:
        return self.__hide
    
    @hide.setter
    def hide(self, value : Union[list,tuple,set]):
        if not isinstance(value, set):
            value = set(value)

        for elt in value.copy():
            if elt not in self.statusbar_elements:
                _LOGGER.warning(f"{self}: {elt} is not registered as a statusbar element")
                value.remove(elt)

        self.__hide = value

    @property
    def orientation(self) -> Literal["horizontal","vertical"]:
        """
        The orientation of the slider. Horizontal or Vertical.
        When changed after initialising, this does change the clock's orientation along with it, but not the text alignment of the clock.
        """
        return self.__orientation
    
    @orientation.setter
    def orientation(self, value:str):
        if value.lower() not in ["horizontal", "vertical","hor","ver"]:
            msg = f"Statusbar orientation must be hor(izontal) or ver(tical). {value} is not allower"
            _LOGGER.exception(msg,exc_info=TypeError(msg))
            return
        else:
            if "hor" in value.lower():
                self.__orientation = "horizontal"
            else:
                self.__orientation = "vertical"
            
            self._rebuild_layout = True
        
        self.__ClockElement.update({"orientation": self.__orientation})
    
    @property
    def rows(self) -> Optional[int]:
        "The number of rows in the grid. If None, rows will be set as needed, provided columns is not None"
        if self.orientation == "vertical":
            return len(self.elements)
        else:
            return 1

    @property
    def columns(self) -> Optional[int]:
        "The number of columns in the grid. If None, columns will be set as needed, provided rows is not None"
        if self.orientation == "horizontal":
            return len(self.elements)
        else:
            return 1

    @property
    def column_sizes(self) -> list[PSSMdimension]:
        "Sizes of the columns. Either a list with the values of the corresponding column index, or a single value with the size for all columns"
        if self.orientation == "horizontal":
            elt_size = self.element_size
            if isinstance(elt_size,float) and elt_size < 0:
                elt_size = f"w*{elt_size}"
            l = [elt_size]*(len(self.elements) -1)
            l.append("?")
            return l
        else:
            return "?"
        
    @property
    def row_sizes(self) -> list[PSSMdimension]:
        "Sizes of the columns. Either a list with the values of the corresponding column index, or a single value with the size for all columns"
        if self.orientation == "vertical":
            elt_size = self.element_size
            if isinstance(elt_size,float) and elt_size < 0:
                elt_size = f"h*{elt_size}"
            l = [elt_size]*(len(self.elements) -1)
            l.append("?")
            return l
        else:
            return "?"
    
    @property
    def element_size(self) -> PSSMdimension:
        if self._element_size != "default":
            return self._element_size
        if self.orientation == "horizontal":
            return "r"
        else:
            return "w"
    
    @element_size.setter
    def element_size(self, value):
        if value == "default":
            self._element_size = value
            return
        
        if isinstance(v := tools.is_valid_dimension(value, ["r"]), Exception):
            _LOGGER.exception(v)
            return
        else:
            self._element_size = value

    @property
    def element_properties(self):
        """
        Allows for styling the elements individually, similar to how it is done for Tile Elements. 
        Accepts all the elements registered as a statusbar element, as well as `'clock'` (for the clock element)
        """
        return {}
    
    @element_properties.setter
    def element_properties(self, value):
        if not value:
            return

        all_elements = self._statusbar_elements | {"clock": self.__ClockElement}

        for elt_name, props in value.items():
            if elt_name not in all_elements:
                _LOGGER.warning(f"{self}: No element registerd under {elt_name}, not applying properties")
                continue
            elt : "Element" = all_elements[elt_name]
            elt.update(props)

    @property
    def status_element_properties(self):
        """
        Allows for general styling of the statusbar icons, i.e. any value passed here is applied to all statusbar elements (except the clock)
        """
        return {}
    
    @status_element_properties.setter
    def status_element_properties(self, value):
        if not value:
            return

        for elt in self.statusbar_elements.values():
            elt.update(value)
    #endregion

    ##Check if this overwrites the element's add_element method; it should
    ##Otherwise, simply make the instance's add_element call this
    @classmethod
    def add_statusbar_element(cls, name : str, element : "Element"):
        """
        Adds a new element to the status bar. Don't confuse this with `add_element`.

        Parameters
        ----------
        name : str
            The name to use for this element. For conventions sake, names are converted to lower case and any spaces are removed.
        element : Element
            The element to add.
        """

        name = name.lower().replace(" ","")
        if name in cls._statusbar_elements:
            _LOGGER.error(f"The statusbar already has an element named {name} registered.")
            return
        elif name == "clock":
            _LOGGER.error(f"'clock' is a reserved name and cannot be used for a statusbar element.")
            return
        
        if not isinstance(element, layouts._GridElement):
            layouts._GridElement.wrap_element(element)
        ##Not going to deal with updating this from here, generally, all elements should be registered before printing starts
        cls._statusbar_elements[name] = element

class UniquePopupMenu(base.PopupMenu, metaclass=Singleton):
    "Base class for popups that can only be defined once."
    
    ##Give this a title element, and then the close button in the corner. Everything else is a layout element.
    def __init__(self, popupID : str, title : str, title_font : PSSMdimension = DEFAULT_FONT_BOLD, **kwargs):
        layout = self.build_menu()
        base.PopupMenu.__init__(self,layout,title, title_font, popupID=popupID, **kwargs)

    @abstractmethod
    def build_menu(self):
        pass

class DeviceMenu(UniquePopupMenu): 
    """
    The menu for the pssm device. Only allows one instance (i.e. the same instance is always returned when instantiating it).
    Altering the appearance can be done by calling DeviceMenu().update() in the usual manner. When running inkboard, a lot can be set in the config already, however some values are determined by constants for consistency.
    """

    @property
    def _emulator_icon(cls): return "mdi:tooltip-cellphone"

    def __init__(self, **kwargs):
        self.device = self.parentPSSMScreen.device

        if self.device.name == None:
            title = "PSSM"
        else:
            title = self.device.name

        super().__init__(title=title, popupID = "device-menu", **kwargs)
        return
        
    def build_menu(self):
        fSize = DEFAULT_FONT_SIZE
        buttonSettings = {"text_x_position": "left", "font_size":fSize}
        m = "w*0.02"
        h = "?"
        h_margin = 5

        deviceText = self.device.deviceName if self.device.deviceName != None else "PSSM"
        
        deviceButton = base.Button(deviceText, font_size=buttonSettings["font_size"])

        layout = [[h,(deviceButton,"?"),(None,"r")]]

        if self.device.has_feature(FEATURES.FEATURE_BATTERY) or self.device.has_feature(FEATURES.FEATURE_NETWORK):
            row = [f"{h}*2"]
            if not self.device.has_feature(FEATURES.FEATURE_NETWORK):
                row.append((None,"?"))
            else:
                networkIcon = develts.DeviceIcon(icon_feature=FEATURES.FEATURE_NETWORK, tap_action=None, background_shape="circle")
                wifiButton = develts.DeviceButton(FEATURES.FEATURE_NETWORK,"SSID",**buttonSettings)

                ipIcon = base.Icon("mdi:ip", background_shape="circle")
                ipButton = develts.DeviceButton(FEATURES.FEATURE_NETWORK,"IP",**buttonSettings)
                netwLayout = [[h, (None,m), (networkIcon, "r"), (None,m) , (wifiButton,"?")],[h_margin],
                    [h, (None,m), (ipIcon, "r"), (None,m) , (ipButton,"?")]]
                row.append((base.Layout(netwLayout),"?"))
            
            if self.device.has_feature(FEATURES.FEATURE_BATTERY):
                batteryIcon = develts.DeviceIcon(FEATURES.FEATURE_BATTERY, tap_action=None)
                batteryText = develts.DeviceButton(FEATURES.FEATURE_BATTERY,"charge",suffix="%", font_size=fSize, fit_text = True)
                battery = base.Layout([["h*0.7",(batteryIcon,"w")],["?",(batteryText,"?")]])
                row.append((battery,"w*0.1"))
                
        else:
            row = [h,(None,"?")]

        layout.append(row)
        layout.append(["10"])
        
        col = DEFAULT_MENU_BUTTON_COLOR
        if self.device.has_feature(FEATURES.FEATURE_POWER):
            ##These should be moved to the pssm screen, as I should give that a function for both with a splash screen
            pw = base.Button("Power off",font_size=fSize, tap_action=self.device.power_off, background_color=col, resize=fSize)
            rb = base.Button("Reboot", font_size=fSize, tap_action=self.device.reboot, background_color=col, font_color="black", resize=fSize)
            buttonRow = ["?", (pw,"?"),(None,"?"), (rb,"?"),(None,"?")]
        else:
            buttonRow = ["?", (None,"?"),(None,"?")]        

        restartButton = base.Button("Reload", font_size=fSize, background_color=col, tap_action=self.parentPSSMScreen.reload, resize=fSize)
        buttonRow.append((restartButton,"?"))
        buttonRow = ["h*0.25",(base.Layout([buttonRow], background_color=col),"w")]
        layout.append(buttonRow)
        self.menu_layout = base.Layout(layout)
        return self.menu_layout

class ScreenMenu(UniquePopupMenu):
    """
    Popup Menu to control and set various settings for the screen. 
    Can be stylised by calling ScreenMenu.update().
    """

    if INKBOARD:
        try:
            from inkBoard.constants import __version__
        except ModuleNotFoundError:
            ##Just in case errors happen
            from .. import __version__
    else:
        from .. import __version__

    @classproperty
    def version(cls):
        "The inkBoard or PSSM version running currently."
        return cls.__version__

    @property
    def _emulator_icon(cls): return "mdi:tooltip-image"

    def __init__(self, **kwargs):

        ##The backlight menu (and presumably more?) Need to be declared here, otherwise they don't update.
        ##I suspect any function not used in the menu is garbage collected if I do.
        backlightOps = ["Manual", "On Interact", "Always"]

        if self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self.__backlightMenu = comps.DropDown(backlightOps, selected=backlightOps.index(self.screen.backlight_behaviour.title()), on_menu_select=self._selected_behaviour, font_color=DEFAULT_FOREGROUND_COLOR)

            sliderOps = ["Brightness", "Default Brightness"]
            self.__sliderMenu = comps.DropDown(sliderOps, on_select=self._set_backlight_slider, font_color=DEFAULT_FOREGROUND_COLOR)
            self.__backlightSlider = develts.BacklightSlider("brightness", orientation="hor", style="box", outline_color=None, end_points=("mdi:brightness-7", None), width="h*0.5")

        if INKBOARD:
            title = "inkBoard"
        else:
            title = "Screen"
        id = "screen-menu"

        super().__init__(title = title,  popupID = id, **kwargs)
        return
    
    #region
    @property
    def device(self) -> "PSSMdevice":
        "The device instance connected to the screen"
        return self.parentPSSMScreen.device   

    @property
    def backlightMenu (self) -> comps.DropDown:
        "Menu element used to select the behaviour of the backlight"
        return self.__backlightMenu
    
    @property
    def sliderMenu (self) -> comps.DropDown:
        "Menu element used to select the behaviour of the backlight slider in the inkBoardMenu"
        return self.__sliderMenu
    
    @property
    def backlightSlider (self) -> develts.BacklightSlider:
        "Slider element used to set either the backlight's default brightness or the brightness itself"
        return self.__backlightSlider
    #endregion

    def build_menu(self):
        layout = []
        
        fSize = "0.4*h"

        ##Maybe some properties to set these, for styling the menu
        ##Also apply that for the device menu
        buttonSettings = {"text_x_position": "left", "font_size":fSize}
        m = "w*0.02"
        h = "?"

        ##Also include the mdi version
        if INKBOARD:
            versionIcon = "inkboard" ##This should be the iB version of the logo
            versionText = f"inkBoard release {self.version}"
        else:
            versionIcon = "mdi:language-python"
            versionText = f"PSSM version {self.version}"

        versionButton = base.Button(versionText, **buttonSettings)
        versionIcon = base.Icon(versionIcon)
        row = [h,(None,m),(versionIcon, "r"),(None,m),(versionButton,"?"),(None,"r")]
        layout.append(row)

        mdiIcon = "mdi:drawing-box"
        mdiText = f"MDI release {MDI_VERSION}"
        mdiButton = base.Button(mdiText, **buttonSettings)
        mdiIcon = base.Icon(mdiIcon)
        row = [h,(None,m),(mdiIcon, "r"),(None,m),(mdiButton,"?"),(None,"r")]
        layout.append(row)

        ##A version check using github is also useful
        ##I think it may be useful to do that using a special icon/element like the device status one?
        ##That uses the interval timer to check like, every 12 hours
        if self.device.has_feature(FEATURES.FEATURE_AUTOSTART):
            state = self.device.autoStart
            elt = comps.CheckBox(state, checked_icon="mdi:checkbox-marked", unchecked_icon="mdi:checkbox-blank", on_set = self.device.toggle_autostart)
            button = base.Button("Auto start",font_size=buttonSettings["font_size"], text_x_position="right")
            row1, row2 = layout
            row1.extend([(elt,"r"),(None,"r")])
            row2.extend([(button,"?"),(None,"r")])

        setter_bg = DEFAULT_MENU_BUTTON_COLOR
        buttSett = {"font_color": DEFAULT_FOREGROUND_COLOR}
        iconSett = {"icon_color": DEFAULT_FOREGROUND_COLOR}
        countkwargs = {"background_color":setter_bg, "radius":5, "countProperties": buttSett, "downProperties": iconSett, "upProperties": iconSett}

        if self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            title = base.Button("Backlight", show_feedback=False)
            layout.append([h,(base.Line(),"w*0.1"), (title,"?") ,(base.Line(),"w*0.75")])

            self.backlightMenu._selected = self.backlightMenu.options.index(self.parentPSSMScreen.backlight_behaviour.title())

            self.backlightSlider.inactive_color = setter_bg
            self.backlightMenu.background_color = setter_bg
            self.sliderMenu.background_color = setter_bg

            behvLayout = base.Layout([[h, (base.Button("Behaviour", show_feedback=False),"?")],
                                            [h, (self.backlightMenu,"?"),(None,"w*0.05")]])
            sliderLayout = base.Layout([[h, (base.Button("Slider:", show_feedback=False),"?"),(self.sliderMenu,"w*0.6"), (None,"w*0.05")],
                                            [h, (self.backlightSlider,"?")]])

            layout.append([f"{h}*2",(sliderLayout, "?"), (behvLayout,"w*0.35")])

            trSetter = comps.Counter("default", self.device.backlight.defaultTransition,step=0.1, minimum=0, on_count=self._set_transition, **countkwargs)
            timeSetter = comps.Counter("default",self.parentPSSMScreen.backlight_time_on,step=1, minimum=0, roundDigits=0, on_count=self._set_on_time, **countkwargs)

            countW = "w*0.2"
            layout.append([m])
            layout.append([h, (base.Button("Default Transition",show_feedback=False ),"?"), (trSetter, countW), 
                        (base.Button("Default Time On",show_feedback=False ),"?"), (timeSetter, countW)])


            ##Maybe, when the function is made, include some options for the screensaver

        layout.append([10,(base.Line(width=3, alignment="bottom"),"w")])

        buttonRow = ["?"]

        refreshButton = base.Icon("mdi:image-refresh",
                                tap_action = self._screen_actions, tap_action_data={"action": "refresh"})

        clearButton = base.Icon("mdi:image-remove",
                            tap_action = self._screen_actions, tap_action_data={"action": "clear"})

        buttonRow.extend([(refreshButton,"?"), (clearButton, "?")])


        if self.device.screenType == "E-Ink":
            invIcon = base.Icon("mdi:image-minus-outline",
                                tap_action = self._screen_actions, tap_action_data={"action": "invert"})
            buttonRow.append((invIcon,"?"))

        buttonLayout = base.Layout([buttonRow], background_color=setter_bg)
        layout.append([40,(buttonLayout, "?")])
        self.menu_layout = base.Layout(layout)
        return self.menu_layout
    
    def _set_transition(self, elt, value : float):
        self.device.backlight.defaultTransition = value
        return

    async def _set_on_time(self,elt, value : float):
        self.device.backlight.default_time_on = value
        return

    async def _set_backlight_slider(self, elt, option):
        if option == "Default Brightness":
            attr = "defaultBrightness"
        elif option == "Brightness":
            attr = "brightness"
        self.backlightSlider.monitor_attribute = attr

    async def _selected_behaviour(self, elt, option):
        self.parentPSSMScreen.set_backlight_behaviour(option)
        return
    
    async def async_show(self, *args, **kwargs):
        if self.device.has_feature(FEATURES.FEATURE_BACKLIGHT):
            self.backlightMenu._selected = self.backlightMenu.options.index(self.parentPSSMScreen.backlight_behaviour.title())
            
        return await super().async_show(*args, **kwargs)

    async def _screen_actions(self, *elt_args, action : Literal["refresh", "clear", "invert"]):
        _LOGGER.info(f"performing screen action {action}")
        
        await self.async_close()
        if action == "refresh":
            await self.parentPSSMScreen.async_refresh(True)
        elif action == "clear":
            await self.parentPSSMScreen.async_clear()
        elif action == "invert":
            self.parentPSSMScreen.invert()
        return

