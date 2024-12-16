"""
    PSSM elements that aren't considered building blocks, but more specialised elements, like clocks. 
    Includes elements which are compounded layouts for example, or have special update cycles.
"""

import logging
import asyncio
from datetime import datetime as dt, timezone as tz, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import partial
from math import pi, sin, cos, ceil, floor
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union, Optional, Callable, Literal, TypeVar, Any, TypedDict, Coroutine
from types import MappingProxyType
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFile, ImageFilter #ImageChops
import mdi_pil as mdi
from mdi_pil import mdiType as MDItype, ALLOWED_MDI_IDENTIFIERS

from ..pssm_types import *

from . import constants as const
from .constants import INKBOARD, DEFAULT_FONT_CLOCK, DEFAULT_FONT_SIZE, MISSING_ICON, DEFAULT_FOREGROUND_COLOR, DEFAULT_BACKGROUND_COLOR,  DEFAULT_FONT_HEADER

from .. import tools
from ..tools import DrawShapes, DummyTask

from . import baseelements as base
from .baseelements import _LOGGER, IMPLEMENTED_ICON_SHAPES, colorproperty, elementaction, Style

BoolDict = TypedDict("BoolDict", {True: dict, False: dict})

_LOGGER = logging.getLogger(__package__)

class Tile(base._TileBase):
    """
    Element that combines an icon, text and optional title into a versatile element. A lot of defaults are present, such that making custom layout elements combining icons and text is generally not needed.

    Parameters
    ----------
    icon : Union[mdiType,str]
        Tile Icon. Set to None for no icon
    text : str
        Tile Text. Set to None for no text
    title : str, optional
        Tile Title, set to None for no title. by default None
    tile_layout : Union[Literal[&quot;vertical&quot;, &quot;horizontal&quot;], str], optional
        tile_layout. Has preset values for vertical and horizontal, but it is also possible to make custom layouts.
        This can be done by using comma's to seperate columns, and semi-colons to seperate rows. Elements can be grouped by enclosing them in square  brackets.
        Defaults to "vertical", which is equivalent to 'icon,title,text'. Horizontal is equivalent to 'icon,[title;text]'
    hide : dict, optional
        explicitly hides elements from the tile_layout, by removing them when parsing from the layoutstring.
        Does not alter the layout string, just the resulting layout.
    horizontal_sizes : Union[`'Tile._EltSizeDict'`,Literal[&quot;default&quot;]], optional
        Horizontal sizes of the elements, by default "default" which sets it according to the value of tile_layout.
        Expects values for icon, title, text and inner and outer, the latter two setting the margins.
        Any keys left out during init will be set to their default values.
    vertical_sizes : Union[`'Tile._EltSizeDict'`,Literal[&quot;default&quot;]], optional
        Vertical sizes of the elements, by default "default" which sets it according to the value of tile_layout.
        Expects values for icon, title, text and inner and outer, the latter two setting the margins.
        Any keys left out during init will be set to their default values.
    foreground_color : ColorType, optional
        Default color for the icon and title and text text, by default DEFAULT_FOREGROUND_COLOR (Set by user or device)
    background_color : ColorType, optional
        Background color of the Tile, by default DEFAULT_BACKGROUND_COLOR
    background_shape : Optional[Union[drawShapes.shapeTypes,Literal[&quot;default&quot;]]], optional
        Shape of the tile enclosure, by default "default"
        Set to None for no background enclosure. Default maps to rounded_square for vertical layouts, and rounded_rectangle for horizontal layouts. Otherwise None.
    shape_settings : dict, optional
        Optional settings to apply to the background_shape, i.e. the arguments applied to the PIL ImageDraw  function, by default {}
    badge_icon : Optional[Union[mdiType,str]], optional
        Icon to use for the icon element badge, by default None
    badge_settings : dict, optional
        settings to apply to the badge, by default {}
    badge_location : Optional[BadgeLocationType], optional
        Location of the badge, by default None
    element_properties : dict, optional
        Properties to apply to the tile elements. Takes options 'icon', 'text' and 'title'. The defaults below are applied to each element if they're not explicitly overwritten.
        default: {"icon": {"icon_color": 'foreground'}, "text": {"font_color": "foreground"}, "title": {"font": DEFAULT_FONT_HEADER, "font_color": "foreground"}}. Additionally, the text elements have a default alignment value set depending on the tile_layout.
        Restricted properties for the icon are 'icon', 'badge_icon' and 'badge_settings'. For 'text' and 'title', the 'text' property is restricted.
    """

    _restricted_element_properties : dict[str,set[str]] = {"icon": {"icon", "badge_icon", "badge_settings"}, "text": {"text"}, "title": {"text"}}
    "Properties of the elements that are not allowed to be set."

    @property
    def _emulator_icon(cls): return "mdi:image-text"

    class _elements(TypedDict):
        icon : base.Icon
        text : base.Button
        title : base.Button

    _resricted_properties = {"icon": {"icon", "badge_icon", "badge_settings"}, "text": {"text"}, "title": {"text"}}
    "Properties not allowed to be set in element_properties. Not in use, preferably use `_restricted_element_properties`"

    class _HideDict(TypedDict):
        "Type hint for the hide Dict"
        icon : bool
        text : bool
        title : bool

    class _EltSizeDict(TypedDict):
        "Type hint for the vSize and hSize dicts"
        icon: PSSMdimension
        text: PSSMdimension
        title: PSSMdimension
        outer: PSSMdimension
        inner: PSSMdimension

    _default_horizontal_sizes = {"horizontal": _EltSizeDict(icon="h", text="?", title="?", outer="h*0.05", inner="h*0.1"),
                "vertical": _EltSizeDict(icon="?", text="?", title="?", outer="h*0.02", inner=0),
                "custom": _EltSizeDict(icon="?", text="?", title="?", outer=0, inner=0)}
    
    _default_vertical_sizes = {"horizontal": _EltSizeDict(icon="?", text="?/2", title="?/2", outer="h*0.15", inner=8),
                "vertical": _EltSizeDict(icon="?*5", text="?", title="?", outer="?", inner=8),
                "custom": _EltSizeDict(icon="?", text="?", title="?", outer=0, inner=0)}

    def __init__(self, icon : Union[mdiType,str], text : str , title : str = None, 
                tile_layout : Union[Literal["vertical", "horizontal"], PSSMLayoutString] = "vertical", hide : 'Tile._HideDict' = (),
                horizontal_sizes : Union['Tile._EltSizeDict',Literal["default"]] = "default", vertical_sizes : Union['Tile._EltSizeDict',Literal["default"]] = "default",
                foreground_color : ColorType = DEFAULT_FOREGROUND_COLOR,  background_color : ColorType = DEFAULT_BACKGROUND_COLOR, outline_color : Optional[ColorType] = None,
                background_shape : Optional[Union[DrawShapes.shapeTypes,Literal["default"]]]  = "default", shape_settings : dict = {},
                badge_icon : Optional[Union[mdiType,str]] = None, badge_settings : dict = {}, badge_location : Optional[BadgeLocationType] = "UR",
                element_properties : dict = {"icon": {"icon_color": 'foreground'}, "text": {"font_color": "foreground"}, "title": {"font": DEFAULT_FONT_HEADER, "font_color": "foreground"}},
                _IconElement : base.Icon = None, _TextElement : base.Button = None, _TitleElement : base.Button = None, 
                
                **kwargs):

        if background_shape == "default":
            if tile_layout == "vertical": 
                background_shape = "rounded_rectangle"
            if tile_layout == "horizontal": background_shape = "rounded_rectangle"

            if background_shape == "default": background_shape = None

        self.__tile_layout = tile_layout

        self.background_shape = background_shape
        self.shape_settings = shape_settings

        setList = {"setIcon" : True, "setText" : True, "setTitle": True}

        for set_key in setList:
            if set_key in kwargs:
                v = kwargs.pop(set_key)
                setList[set_key] = v

        if _IconElement == None:
            self.__IconElement = base.Icon(icon, _register = False)
        else:
            self.__IconElement = _IconElement

        if _TextElement == None:
            self.__TextElement = base.Button(text, text_x_position="m", _register = False)
        else:
            self.__TextElement = _TextElement

        if _TitleElement == None:
            if title == None:
                title = str(None)
                if "title" not in hide:
                    hide = list(hide)
                    hide.append("title")
            self.__TitleElement = base.Button(title, text_x_position="m", _register = False)
        else:
            self.__TitleElement = _TitleElement

        self.__elements = MappingProxyType({'icon': self.__IconElement, 'text': self.__TextElement, 'title': self.__TitleElement})
        
        default_properties = {"icon": {"icon_color": 'foreground', 'background_color': 'accent', "background_shape": "circle"}, "text": {"font_color": "foreground"}, "title": {"font": DEFAULT_FONT_HEADER, "font_color": "foreground"}}

        for elt in default_properties:
            set_props = element_properties.get(elt, {})
            default_properties[elt].update(set_props)

        element_properties = default_properties

        text_x_position = "m"
        if tile_layout in ["vertical", "ver"]:
            size_key = "vertical"
        elif tile_layout in ["horizontal", "hor"]:
            size_key = "horizontal"
            text_x_position = "l"
        else:
            size_key = "custom"

        element_properties["text"].setdefault("text_x_position", text_x_position)
        element_properties["title"].setdefault("text_x_position", text_x_position)

        if horizontal_sizes != "default":
            horizontal_sizes = dict(horizontal_sizes)
            for key, value in Tile._default_horizontal_sizes[size_key].items():
                horizontal_sizes.setdefault(key, value)

        if vertical_sizes != "default":
            vertical_sizes = dict(vertical_sizes)
            for key, value in Tile._default_vertical_sizes[size_key].items():
                vertical_sizes.setdefault(key, value)

        super().__init__(tile_layout="None", horizontal_sizes=horizontal_sizes, vertical_sizes=vertical_sizes,
                        foreground_color=foreground_color, background_color=background_color, outline_color=outline_color,
                        element_properties=element_properties,  **kwargs)

        self.horizontal_sizes = horizontal_sizes
        self.vertical_sizes = vertical_sizes
        self.hide = hide

        if setList["setIcon"]:
            self.icon = icon
        
        self.badge_icon = badge_icon
        self.badge_settings = badge_settings
        self.badge_location = badge_location

        if setList["setText"]:
            self.text = text
        
        if setList["setTitle"]:
            self.title = title

        self.tile_layout = tile_layout
        
        self._layoutstr: str
        "The string representing the layout to parse, also the default values for horizontal/vertical, accounting for title being present or not"
        return
    #region
    @colorproperty
    def background_color(self) -> Union[ColorType,None]:
        "Background color of the element. Automatically set to None if background_shape is used."
        return self._background_color

    @property
    def _shapeColor(self) -> Union[ColorType,None]:
        "Color of the background shape. Set using background color."
        return self.background_color

    @property
    def radius(self) -> PSSMdimension:
        "Corner radius of the element's background. Only applicable when no background shape is used, otherwise 0."
        if self.background_shape != None:
            return 0
        else:
            return self._radius

    @radius.setter
    def radius(self, value):
        base.Layout.radius.fset(self, value)

    @property
    def background_shape(self) -> Optional[DrawShapes.shapeTypes]:
        """
        The shape to apply to the button background. Keep in mind some square shapes won't automatically fit the shape.
        The shape takes the background colour.
        """        
        ##Look into how this works with radius etc.
        return self.__background_shape

    @background_shape.setter
    def background_shape(self, value : str):
        if value in {None, "default"}:
            pass
        elif value.lower() not in DrawShapes.shapeTypes.__args__ and value != "ADVANCED":
            msg = f"{value} is not recognised as a valid background shape."
            _LOGGER.exception(ValueError(msg))
            return
        
        self.__background_shape = value

    @property
    def shape_settings(self) -> dict:
        """
        Settings to apply to the tile background. background_color and outline_color/width are set from the properties if not present. 
        If backgroundshape is ADVANCED, you are responsible for all settings yourself, as well as specifying the drawing method to use.
        """
        d = self.__shape_settings.copy()

        if self.background_shape == "ADVANCED":
            return d

        d.setdefault("fill", self._shapeColor)
        
        if self.outline_color != None:
            d.setdefault("outline", self.outline_color)

        if self.outline_width != 0:
            d.setdefault("width", self.outline_width)

        return d
    
    @shape_settings.setter
    def shape_settings(self, value : dict):
        self.__shape_settings = value.copy()

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
        self._icon : Union[mdiType,Image.Image]
        base.Icon._icon_setter(self, "_icon", value, allow_none=True)        
        
        self._IconElement.update({"icon": self.icon}, skipPrint=self.isUpdating, skipGen=self.isGenerating)

    @property
    def badge_icon(self) -> Optional[mdiType]:
        """
        Icon to use as a badge for the Tile's Icon element. Must be None or an mdi icon
        """
        return self._badge_icon

    @badge_icon.setter
    def badge_icon(self, value: Optional[str]):
        if value != None and not isinstance(value, (str, Image.Image)):
            _LOGGER.error(f"{value} cannot be used as a badge icon, setting to error icon.")
            self._badge_icon = MISSING_ICON
        else:
            self._badge_icon = value
            self._IconElement.badge_icon = value

    @property
    def badge_settings(self) -> dict:
        """
        Dict with settings to apply to the badge. background_color needs to be defined explicitly, otherwise it is automatically set to the background color or default color.
        """
        return self._badge_settings.copy()
    
    @badge_settings.setter
    def badge_settings(self, value : dict):
        value = value.copy()
        for key in value:
            if key not in base.ALLOWED_BADGE_SETTINGS: _LOGGER.warning(f"{key} is not an allowed badge setting")
        
        value.setdefault("background_color", self.background_color if self.background_color != None else DEFAULT_BACKGROUND_COLOR)
        self._badge_settings = value
        self.__IconElement.update({"badge_settings": value}, skipPrint=self.isUpdating)

    @property
    def badge_location(self) -> BadgeLocationType:
        """
        The location of the badge. 
        Can be Can be one of UR, LR, UL or LL (Upper Right, Lower Right, Upper Left, Lower Left). Also accepts the fully written strings, but will be set to  the abbreviated location.
        """
        return self._badge_location
    
    @badge_location.setter
    def badge_location(self, value):
        base.Icon.badge_location.fset(self._IconElement, value)
        return

    @property
    def text(self) -> Optional[str]:
        "The text displayed on the Tile"
        return self.__text
    
    @text.setter
    def text(self, value : str):
        if value == None:
            pass
        elif not isinstance(value, str):
            value = str(value)
        
        self.__text = value
        self.__TextElement.update({"text": self.text}, skipPrint=self.isUpdating)

    @property
    def title(self) -> Optional[str]:
        "The title text displayed on the above the Tile text. Set to None to not include it."
        return self.__title
    
    @title.setter
    def title(self, value : str):
        if value == None:
            pass
        elif not isinstance(value, str):
            value = str(value)
        
        self.__title = value
        self.__TitleElement.update({"text": self.title}, skipPrint=self.isUpdating)

    @property
    def tile_layout(self) -> Union[Literal["vertical", "horizontal"], PSSMLayoutString]:
        return self.__tile_layout
    
    @tile_layout.setter
    def tile_layout(self, value : Union[Literal["horizontal", "vertical", "hor", "ver"],PSSMLayoutString]):
        if not isinstance(value,str):
            ##Maybe do allow for this but call the is_layout_valid
            msg = f"tile_layout must be a string. Set the layout itself to alter it directly?"
            _LOGGER.error(TypeError(msg))
            return
        
        if value not in ["horizontal", "vertical", "hor", "ver"]:
            self.__tile_layout = value
            self._layoutstr = value
        else:
            if "hor" in value:
                self.__tile_layout = "horizontal"
            else:
                self.__tile_layout = "vertical"
            
            self._layoutstr = self._build_tile_layout_str(value)
        self._reparse_layout = True

    def _build_tile_layout_str(self, value : str):
        """
        Determines the layoutstring for the tile for the default layouts (horizontal/vertical)

        Parameters
        ----------
        value : str
            the layoutstring to process (generally horizontal or vertical, but accepts any string)

        Returns
        -------
        str
            the actual string that can be used _parse_tile_layout
        """
        if value in ["horizontal", "vertical", "hor", "ver"]:
            ##Make this automatically omit the title if it is not set
            if self.title == None:
                t = ""
            else:
                t = "title;"
            
            if "hor" in value:
                layoutstr = f"icon,[{t}text]"
            else:
                layoutstr = f"icon;{t}text"
        else:
            layoutstr = value
        return layoutstr

    @property
    def vertical_sizes(self) -> 'Tile._EltSizeDict':
        "Vertical sizes for the elements. Returns the default values when set to default, not 'default'"
        if self._vertical_sizes != "default":
            return self._vertical_sizes
        else:
            size_key = self.tile_layout if self.tile_layout in {"horizontal", "vertical"} else "custom"

            return Tile._default_vertical_sizes[size_key].copy()
    
    @vertical_sizes.setter
    def vertical_sizes(self, value : dict):
        if value == self._vertical_sizes:
            return
        
        self._reparse_layout = True
        if value == "default":
            self._vertical_sizes = value
            return
        base._TileBase.vertical_sizes.fset(self,value)

    @property
    def horizontal_sizes(self) -> 'Tile._EltSizeDict':
        "Horizontal sizes for the elements. Returns the default values when set to default, not 'default'"
        if self._horizontal_sizes != "default":
            return self._horizontal_sizes
        else:
            size_key = self.tile_layout if self.tile_layout in {"horizontal", "vertical"} else "custom"
            return Tile._default_horizontal_sizes[size_key].copy()

    @horizontal_sizes.setter
    def horizontal_sizes(self, value : dict):
        if value == self._horizontal_sizes:
            return
        self._reparse_layout = True
        if value == "default":
            self._horizontal_sizes = value
            return
        base._TileBase.horizontal_sizes.fset(self,value)

    #region subelements
    @property
    def elements(self) -> MappingProxyType[Literal['icon', 'text', 'title'],base.Element]:
        "Elements of the tile. Contains 'icon', 'text' and 'title'."
        return self.__elements
    
    @property
    def IconElement(self) -> Optional[base.Icon]:
        "The element containing the icon. Returns None if the icon value is None."
        if self.icon == None:
            return None
        else:
            return self.__IconElement
    
    @property
    def _IconElement(self) -> base.Icon:
        "The element containing the icon."
        return self.__IconElement

    @property
    def TextElement(self) -> Optional[base.Button]:
        "The element containing the text. Returns None if the text value is None."
        if self.text == None:
            return None
        else:
            return self.__TextElement

    @property
    def _TextElement(self) -> base.Button:
        "The element containing the text."
        return self.__TextElement
        
    @property
    def TitleElement(self) -> Optional[base.Icon]:
        "The element containing the title. Returns None if the title value is None."
        if self.title == None:
            return None
        else:
            return self.__TitleElement
        
    @property
    def _TitleElement(self) -> base.Button:
        "The element containing the title."
        return self.__TitleElement
    #endregion

    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):

        if area==None:
            area = self.area
        
        if area == None:
            return
        
        if not self.isGenerating:
            #This ensures the layout is fully dealt with in case the generator is called, or generate is called without an event loop.
            if self.__tile_layout in {"horizontal", "vertical"}:
                if (l := self._build_tile_layout_str(self.__tile_layout)) != self._layoutstr:
                    self._layoutstr = l
                    self._reparse_layout = True

            if self._layoutstr != None and self._reparse_layout:
                old_layout = self.layout

                new_layout = base.parse_layout_string(self._layoutstr, None, self.hide, self.vertical_sizes, self.horizontal_sizes, **self.elements)
                if new_layout != old_layout:
                    self._layout = new_layout
                    skipNonLayoutGen=False
                    self._rebuild_area_matrix = True
                    self.set_parent_layouts(old_layout, self.layout)

                self._reparse_layout = False

        [(x,y),(w,h)] = self.area

        img = super().generator(area, skipNonLayoutGen)
        
        self._feedbackImg = None

        if self.background_shape != None:
            background_shape = self.background_shape
            if self.background_shape == "default":
                if self.tile_layout == "vertical": background_shape = "rounded_rectangle"
                if self.tile_layout == "horizontal": background_shape = "rounded_rectangle"

                if background_shape == "default": background_shape = None

            draw_func = DrawShapes.get_draw_function(background_shape)
            draw_args = self.shape_settings
            if self.background_shape == "ADVANCED":
                method = draw_args.pop("method")
                shape_img, _ = DrawShapes.draw_advanced(img,method,draw_args, paste=False)
            else:    
                shape_img, _ = draw_func(img, draw_args, paste=False)

            if self.show_feedback and self.background_shape != "ADVANCED":
                fb_scale = 0.85
                fb_scaled = ImageOps.scale(img, fb_scale)

                fb_bg = shape_img.copy()

                draw_args["outline"] = Style.get_color(self.parentBackgroundColor,"RGBA")
                draw_args.pop("fill", None)
                if "width" not in draw_args:
                    draw_args["width"] = self._convert_dimension("h*0.2")

                fb_shape, _ = draw_func(fb_bg, draw_args, paste=False)
                
                dest = (int(0.5*w*(1-fb_scale)),int(0.5*h*(1-fb_scale)))

                fb_shape : Image.Image
                fb_shape.alpha_composite(fb_scaled, dest)

                self._feedbackImg = fb_shape
            
            shape_img.alpha_composite(img)
            self._imgData = shape_img

        return self.imgData

    async def async_generate(self, area = None, skipNonLayoutGen=False):

        async with self._generatorLock:
            if area==None:
                area = self.area
            
            if area == None:
                return

            if self.__tile_layout in {"horizontal", "vertical"}:
                if (l := self._build_tile_layout_str(self.__tile_layout)) != self._layoutstr:
                    self._layoutstr = l
                    self._reparse_layout = True

            if self._layoutstr != None and self._reparse_layout:
                old_layout = self.layout
                new_layout = base.parse_layout_string(self._layoutstr, None, self.hide, self.vertical_sizes, self.horizontal_sizes, **self.elements)
                if new_layout != old_layout:
                    self._layout = new_layout
                    skipNonLayoutGen=False
                    self.set_parent_layouts(old_layout,self._layout)
                    self._rebuild_area_matrix = True

                self._reparse_layout = False

        return await super().async_generate(area, skipNonLayoutGen)

    async def feedback_function(self) -> Coroutine[Any, Any, Callable[..., None]]:
        
        if self._feedbackImg == None: ##show_feedback is already called in the screen dispatch
            self._feedbackTask = asyncio.create_task(self.parentPSSMScreen.async_invert_element(self,self.feedback_duration))
        else:
            self._feedbackTask = asyncio.create_task(self.tile_feedback())
        await self.feedbackTask
        return
    
    async def tile_feedback(self):
        [(x, y), (w, h)] = self.area

        self.parentPSSMScreen.device.print_pil(
            self._feedbackImg,
            x, y,
            isInverted=self.isInverted
        )

        await asyncio.sleep(self.feedback_duration)

        if self.parentPSSMScreen.popupsOnTop:
            eltarea = self.area
            popuparea = self.parentPSSMScreen.popupsOnTop[-1].area
            _LOGGER.debug(f"Element is {eltarea} popup is {popuparea}")
        
        self.parentPSSMScreen.device.print_pil(
            self.imgData,
            x, y,
            isInverted=self.isInverted #self.isInverted
        )

#region datetime element
class dateTimeElementInterval(base._IntervalUpdate):
    "A base class for constructing datetime related elements, provides some general properties for example"
    def __init__(self, date_format : str, timezone : str, update_every : Literal["hour", "minute", "second"]):
        self.date_format = date_format
        self.timezone = timezone
        super().__init__(update_every=update_every)

    #region
    @property
    def timezone(self) -> Union[str,None]:
        "The timezone attached to this clock"
        return self.__timezone
    
    @timezone.setter
    def timezone(self, value):
        if value == None:
            self.__timezone = value
            self.__zoneInfo = None
        else:
            try:
                tz = ZoneInfo(value)
            except ZoneInfoNotFoundError:
                _LOGGER.exception(f"{value} is not a valid timezone key")
            else:
                self.__timezone = value
                self.__zoneInfo = tz

    @property
    def zoneInfo(self) -> Union[ZoneInfo,None]:
        """
        The timezone object to be used when constructing datetime objects
        Can be set by setting timezone
        """
        return self.__zoneInfo

    @property
    def date_format(self) -> str:
        "The format string of the time"
        return self.__date_format
    
    @date_format.setter
    def date_format(self, value):
        try:
            dt.now().strftime(value)
            self.__date_format = value
        except ValueError as exce:
            _LOGGER.error(exce)
    #endregion

class AnalogueClock(base.Element, dateTimeElementInterval):
    #[ ] Make outline width also possible as a tuple?
    """
    An analogue clock that updates at the start of each minute

    Parameters
    ----------
    timezone : str, optional
        the timezone to associate this clock with. Uses system time by default, by default None
    clock_fill_color : Optional[ColorType], optional
        color of the inside circle of the clock. Defaults to none (copies background), by default None
    outline_color : Optional[ColorType], optional
        color of the clock outline, by default "black"
    outline_width : int, optional
        outline width of the clocks circle. Defaults to one, by default 5
    hour_hand_color : Optional[ColorType], optional
        Color of the hour hand, by default None
    minute_hand_color : Optional[ColorType], optional
        Color of the minute hand, by default None
    show_ticks : bool, optional
        Whether to show ticks at the hour positions on the clock, by default True
    tick_color : Optional[ColorType], optional
        The color of the ticks, by default None
    show_digital : bool, optional
        Whether to show the time in digital format too, by default False
    digital_format : str, optional
        time format string of the digital time, by default "%a"
    digital_font : str, optional
        Font for the digital time, by default DEFAULT_FONT_CLOCK
    digital_color : Optional[ColorType], optional
        Color of the digital time, by default None
    background_color : Optional[ColorType], optional
        Background color of the clock, by default None
    tap_action : _type_, optional
        Clock tap action, by default None
    """

    @property
    def _emulator_icon(cls): return "mdi:clock"

    def __init__(self, timezone=None, clock_fill_color : Optional[ColorType]=None, outline_color : Optional[ColorType]="black", outline_width = 5, 
                hour_hand_color : Optional[ColorType] =None, minute_hand_color : Optional[ColorType] =None, 
                show_ticks : bool = True, tick_color : Optional[ColorType] =None, 
                show_digital:bool=False, digital_format : str = "%a", digital_font : str = DEFAULT_FONT_CLOCK, digital_color : Optional[ColorType] =None, 
                background_color : Optional[ColorType] =None, tap_action=None, **kwargs):

        base.Element.__init__(self, **kwargs)
        dateTimeElementInterval.__init__(self,digital_format,timezone=timezone, update_every="minute")

        self._genClock = True
        "Generates the entire clock image upon the next call to the generator, instead of just the hands (and possible time text). Is always reset to False after regenerating the clock image."

        self.show_digital = show_digital

        self.digital_format = digital_format
        self.digital_font = digital_font
        self.digital_color = digital_color

        ##These and show_ticks should regen the clock when set
        self.clock_fill_color = clock_fill_color
        self.hour_hand_color = hour_hand_color
        self.minute_hand_color = minute_hand_color

        self.show_ticks = show_ticks
        self.tick_color = tick_color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.background_color = background_color

        self.tap_action = tap_action

    #region
    @colorproperty
    def clock_fill_color(self) -> Optional[ColorType]:
        "Background color of the clock"
        return self._clock_fill_color

    @colorproperty
    def outline_color(self) -> Optional[ColorType]:
        "Color of the clock's outline"
        return self._outline_color

    @property
    def outline_width(self) -> PSSMdimension:
        "Width of the clock's outline"
        return self._outline_width

    @outline_width.setter
    def outline_width(self,value: PSSMdimension):
        self._dimension_setter("_outline_width",value)
        self._outline_width : PSSMdimension
        self._genClock = True

    @colorproperty
    def hour_hand_color(self):
        "The color of the hour hand. Defaults to the outline color"
        if self._hour_hand_color == None:
            return self.outline_color
        return self._hour_hand_color

    @colorproperty
    def minute_hand_color(self):
        "The color of the minute hand. Defaults to the outline color"
        if self._minute_hand_color == None:
            return self.outline_color
        return self._minute_hand_color

    @property
    def show_ticks(self) -> bool:
        return self.__show_ticks
    
    @show_ticks.setter
    def show_ticks(self, value):
        if not isinstance(value, bool):
            msg = "Show Ticks must be boolean"
            _LOGGER.error(msg)
            if const.RAISE: raise TypeError(msg)
        
        self._genClock = True
        self.__show_ticks = value

    @colorproperty
    def tick_color(self) -> ColorType:
        "The color of the hour ticks. If None, will return the outline color"
        if self._tick_color == None:
            return self.outline_color
        return self._tick_color

    @property
    def show_digital(self) -> bool:
        "Show a text element on the clock showing a formatted time string based on the current time and date"
        return self.__show_digital
    
    @show_digital.setter
    def show_digital(self, value):
        if not isinstance(value, bool):
            msg = "Show digital must be boolean"
            _LOGGER.error(msg)
            if const.RAISE: raise TypeError(msg)
        
        self.__show_digital = value    

    @property
    def digital_format(self) -> str:
        """
        Datetime format string to apply to the digital time. Default to %a (abbreviated day of the week)
        """
        return self.date_format
    
    @digital_format.setter
    def digital_format(self, value):
        self.date_format = value

    @property
    def digital_font(self) -> str:
        "The font used for the digital time indicator"
        return self.__digital_font
    
    @digital_font.setter
    def digital_font(self, value : str):
        try:
            f = tools.parse_known_fonts(value)
            f = ImageFont.truetype(f)
        except OSError:
            msg = f"Could not open font from value {value}"
            _LOGGER.exception(OSError(msg))
        else:
            self.__digital_font = value

    @colorproperty
    def digital_color(self):
        "Color of the digital time indicator"
        if self._digital_color == None:
            return self.outline_color
        return self._digital_color

    #endregion

    def _style_update(self, attribute: str, value):
        "Called when a style property is updated"
        if attribute in {"clock_fill_color", "outline_color", "tick_color"}:
            self._genClock = True

    async def callback(self):
        await self.async_update(updated=True)

        if self.parentPSSMScreen.device.screenType == "E-Ink" and dt.now(self.zoneInfo).minute % 5 == 0:
            self.parentPSSMScreen.device.do_screen_refresh(area=self.area)

    def generator(self, area=None, skipNonLayoutGen=False):
        if area is not None:
            self._area = area
        (x, y), (w, h) = self.area

        colorMode = self.parentPSSMScreen.imgMode
        img_background = Style.get_color(self.background_color,colorMode)
        clock_fill = Style.get_color(self.clock_fill_color, colorMode)
        clock_line = Style.get_color(self.outline_color, colorMode)
        timedt = dt.now(self.zoneInfo)

        hour_width = round(self.outline_width*2.5)  ##Want to change these to be settable
        mnt_width = round(self.outline_width*1.5)

        if self._genClock:
            min_resolution = DrawShapes.MINRESOLUTION
            s = max(w,h,min_resolution)
            img = Image.new(
                colorMode,
                (s, s),
                color=img_background
            )
            img = ImageOps.cover(img, size=(min_resolution,min_resolution))
            (wc,hc) = img.size
            draw = ImageDraw.Draw(img)

            clock_radius = floor(min(wc,hc)*0.495)
            hour_length = clock_radius*0.6
            minute_length = clock_radius*0.9

            center = (int(wc/2), int(hc/2))
            coo = [center[0] - clock_radius, center[1] - clock_radius, center[0] + clock_radius, center[1] + clock_radius]
            coo = [ floor(elem) for elem in coo ]

            draw.pieslice(
                coo,
                start=0,end=360,
                fill=clock_fill,
                width=0,
            )

            if self.show_ticks:
                tick_length = floor(clock_radius*0.14)
                tick_O = [(center[0], center[1]-clock_radius+tick_length),(center[0], center[1]-clock_radius)]
        
                for t in range(0,12):
                    th = 2*pi*(t/12)
                    tick_coords = tools.rotation_matrix(tick_O,th,center)
                    draw.line(
                        tick_coords, 
                        fill=self.tick_color, 
                        width=hour_width
                    )

            draw.pieslice(
                coo,
                start=0,end=360,
                outline=clock_line,
                width=self.outline_width,
            )
            self._clockImg = img
            self._genClock = False
        
        img = self._clockImg.copy()
        draw = ImageDraw.Draw(img)
        (wc,hc) = img.size
        
        clock_radius = floor(min(wc,hc)*0.495)
        hour_length = clock_radius*0.6
        minute_length = clock_radius*0.9

        center = (int(wc/2), int(hc/2))
        coo = [center[0] - clock_radius, center[1] - clock_radius, center[0] + clock_radius, center[1] + clock_radius]
        coo = [ floor(elem) for elem in coo ]

        if self.show_digital:
            font = tools.parse_known_fonts(self.digital_font)
            font = ImageFont.truetype(font, int(clock_radius*0.2))
            
            t_coo = (center[0],center[1]+int((hour_length+clock_radius)/2))

            txt = timedt.strftime(self.digital_format)
            draw.text(
                t_coo,text=txt, anchor="ms", font = font, fill=self.digital_color
            )

        
        minute = timedt.minute
        minute_pct = minute/60
        minute_angle = minute_pct*2*pi

        (mnt_x, mnt_y) = (sin(minute_angle)*minute_length, cos(minute_angle)*minute_length)
        minute_l = [center, round(mnt_x + center[0]), round(center[1] - mnt_y)]

        draw.line(
            minute_l,
            fill=self.minute_hand_color,
            width=mnt_width
        )
        
        
        hour = timedt.hour
        hour_pct = hour/12 if hour < 12 else hour/12 - 1
        hour_angle = (hour_pct + minute_pct/12)*2*pi

        (hour_x, hour_y) = (sin(hour_angle)*hour_length, cos(hour_angle)*hour_length)
        hour_coo = [center, round(hour_x + center[0]), round(center[1] - hour_y)]

        draw.line(
            hour_coo,
            # fill=clock_line,
            fill=self.hour_hand_color,
            width=hour_width
        )

        md_r = int(hour_width*1)
        coo = [(center[0]-md_r,center[1]-md_r),(center[0]+md_r,center[1]+md_r)]
        draw.pieslice(
            coo,
            fill=self.hour_hand_color,
            start=0,
            end=360
        )

        _LOGGER.verbose(f"Clock updated for {timedt.strftime('%H:%M')}")
        self._imgData = ImageOps.pad(img,(w,h), color=img_background)
        return self.imgData

class DigitalClock(base.Button, dateTimeElementInterval):
    """
    A digital clock that updates at the start of each minute.

    Parameters
    ----------
    time_format : str, optional
        the format to display the time in. See https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes for python formats, by default "%H:%M"
        This site https://www.dateformatgenerator.com/?lang=Python can generate a format string based on an input time.
    timezone : str, optional
        IANA Timezone. See https://docs.python.org/3/library/zoneinfo.html#using-zoneinfo, by default None (Which should use the system timezone)
        timezone list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    orientation : Literal[&quot;horizontal&quot;,&quot;vertical&quot;], optional
        The orientation of the clock, by default "horizontal"
        Setting this to vertical will have the time_format altered to make use of multiline text. See the property description for more info.
    font : str, optional
        The font to use, by default DEFAULT_FONT_CLOCK
    font_size : str, optional
        The size of the font, by default "h*0.9"
    resize : _type_, optional
        If not `False`, this will resize the button's font up to a minimum of this value, by default DEFAULT_FONT_SIZE
    fit_text : bool, optional
        True if the text is to be automatically fitted into the text box, by default True
    """   

    @property
    def _emulator_icon(cls): return "mdi:clock-digital"

    def __init__(self, time_format="%H:%M", timezone=None, orientation: Literal["horizontal","vertical"] = "horizontal",
                font=DEFAULT_FONT_CLOCK, font_size="h*0.9", resize=DEFAULT_FONT_SIZE, fit_text=True,  **kwargs):

        base.Button.__init__(self, text=None, font=font, fit_text=fit_text, font_size=font_size, resize=resize, **kwargs)
        dateTimeElementInterval.__init__(self, date_format=time_format, timezone=timezone, update_every="minute")

        self.orientation = orientation
        self.timezone = timezone
        self.time_format = time_format
        self._text = dt.now(self.zoneInfo).strftime(self.time_format)
        self.__added = False

    #region
    @property
    def text(self) -> str:
        "The current time string being displayed on the clock"
        return self._text
    
    @property
    def time_format(self) -> str:
        """
        Datetime format string to apply to the digital time. Default to %a (abbreviated day of the week)
        """
        if self.orientation == "horizontal":
            return self.date_format
        else:
            new_str = self.date_format.replace(":","\n")
            new_str = new_str.replace(" ", "\n")
            return new_str
    
    @time_format.setter
    def time_format(self, value):
        ##date_format is from the datetimeinterval class
        self.date_format = value

    @property
    def orientation(self) -> Literal["horizontal","vertical"]:
        """
        The orientation of the clock. If vertical, the time format string is altered to use be multiline.
        Any ':' and spaces (' ') are automatically replaced by a linebreak. 
        So format %H:%M will become `'%H\\n%M'`, i.e. the top line will be the hour and the bottom line will be the minute. Similarly, using '%-I:%M %p' will become `'%-I\\n%M\\n%p'`, with the hour, minute and am/pm each on a new line.
        """
        return self._orientation
    
    @orientation.setter
    def orientation(self, value):
        if "ver" in value:
            self._orientation = "vertical"
        elif "hor" in value:
            self._orientation = "horizontal"
        else:
            raise ValueError(f"{self}: orientation must be horizontal or vertical (or a shorthand), {value} is not valid.")
        
        if self._orientation == "vertical":
            self._multiline = True
        else:
            self._multiline = False

    #endregion

    async def callback(self):
        if not self.__added:
            ##This ensures the font size should immediately a size that should fit all possible times
            dtime = dt.strptime("00:00","%H:%M")
            text = dtime.strftime(self.time_format)

            ##Call the fit function before generating the first time to set the (likely) correct font_size
            self.fit_text_func(text=text,area=self.area,font=self.font)
            self.__added = True

        text = dt.now(self.zoneInfo).strftime(self.time_format)
        await self.async_update({"_text": text})

        if self.parentPSSMScreen.device.screenType == "E-Ink" and dt.now().minute % 15 == 0:
            self.parentPSSMScreen.device.do_screen_refresh(area=self.area)

class DateElement(base.Button, dateTimeElementInterval):
    """
    This element shows a date and updates at the top of every hour.

    Parameters
    ----------
    date_format : str, optional
        the format to display the date in. See https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes for python formats.
        This site https://www.dateformatgenerator.com/?lang=Python can generate a format string based on an input time., by default "%H:%M"
    timezone : str, optional
        IANA Timezone. See https://docs.python.org/3/library/zoneinfo.html#using-zoneinfo;
        timezone list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones, by default None
    font : str, optional
        font to display the date in, by default 'default-bold'
    font_size : str, optional
        Font size. On default settings (using resize) this is taken care of automatically, by default "h*0.9"
    resize : PSSMdimension, optional
        Set this to a dimensional string, integer or float to automatically resize the clock display to fit the current time up to a minimum size of [resize]., by default DEFAULT_FONT_SIZE
    fit_text : bool, optional
        try and fit the clock into the box? (Not a dynamic function, will use font_size as a minimum value, but not change it. resize takes precendent over it as well.), by default True
    """

    @property
    def _emulator_icon(cls): return "mdi:calendar-week"

    def __init__(self, date_format="%Y-%m-%-d", timezone=None, font='default-bold', font_size: PSSMdimension ="h*0.9", resize: PSSMdimension=DEFAULT_FONT_SIZE, fit_text: bool = True,  **kwargs):

        base.Button.__init__(self, text=None, font=font, fit_text=fit_text, font_size=font_size, resize=resize, **kwargs)
        dateTimeElementInterval.__init__(self, date_format=date_format, timezone=timezone, update_every="hour")

        self.timezone = timezone
        self.__added = False
        self._text = dt.now(self.zoneInfo).strftime(self.date_format)

    #region
    @property
    def text(self) -> str:
        "The current time string being displayed on the clock"
        return self._text    
    #endregion

    async def callback(self):
        if not self.__added and self.area != None:
            ##This ensures the font size should immediately a size that should fit all possible times
            ##Hopefully. October is a pretty long month letter wise at least?
            ##Otherwise, in this case text changing size is not as much of a problem at least
            dtime = dt(year=1984,month=10,day=30)
            
            text = dtime.strftime(self.date_format)
            self.fit_text_func(text=text,area=self.area,font=self.font)
            self.__added = True
        # else:
        text = dt.now(self.zoneInfo).strftime(self.date_format)
        self.update({"_text": text})

#endregion        

#region Sliders
class LineSlider(base._BaseSlider):
    """
    Makes an (interactive) slider with a thumb and a line. See _BaseSlider for all slider specific parameters.

    Parameters
    ----------
    color : ColorType, optional
        Color of the slider line, by default "black"
    width : PSSMdimension, optional
        width of the slider line, by default None, which translates to "h/4" or "w/4" depending on orientation.
    orientation : str, optional
        slider orientation, horizontal or vertical. by default "horizontal"
    tap_action : Optional[Callable[[base.Element,tuple[int,int]],None]], optional
        Action to call when tapping it, by default None
    thumb : Optional[str], optional
        Type of thumb to use. Can be circle, rounded_rectangle or rectangle. by default "rounded_rectangle"
    thumb_width : Optional[PSSMdimension], optional
        Width of the thumb, by default None which automatically sets the best size for the thumb type. Can use 'l' for the length of the slider line in dimension strings
    thumb_height : Optional[PSSMdimension], optional
        Height of the thumb, by default None which automatically sets the best size for the thumb type. Can use 'l' for the length of the slider line in dimension strings
    thumb_color : Optional[ColorType], optional
        Color of the thumb, by default None which sets it to the same color as the slider
    thumb_icon : Optional[str], optional
        MDI icon to put in the thumb, by default None
    thumb_icon_color : Optional[ColorType], optional
        Color of the thumb icon, by default None, which uses the inverted color of the thumb
    end_points : Optional[Union[str,tuple[str,str]]], optional
        MDI icons to set at the endpoints. If supplying to values, they will be set at the (min, max) ends respectively, by default None
    end_colors : Optional[ColorType], optional
        Color of the endicons, by default None, which uses the same color as the slider.
    end_point_size : DimensionType, optional
        Size of the endicons, by default None, which means its set to a half of the element height/width for orientations horizontal/vertical respectively.
    """
    
    @property
    def _emulator_icon(cls): return "mdi:vector-line"

    def __init__(self, color : 'ColorType' = "black", width : PSSMdimension = None, orientation : Literal["horizontal", "vertical"] ="horizontal", tap_action : Optional[Callable[[base.Element,tuple[int,int]],None]]=None,
                thumb : Literal["circle", "rectangle", "rounded_rectangle", None] ="rounded_rectangle", thumb_width : Optional[PSSMdimension] =None, thumb_height : Optional[PSSMdimension] = None, thumb_color : Optional[ColorType]=None, 
                thumb_icon: MDItype=None, thumb_icon_color : Optional[ColorType] = None, end_points : Optional[Union[MDItype,tuple[str,str]]]=None, end_colors : Optional[ColorType]=None, end_point_size : PSSMdimension = None, **kwargs):

        
        super().__init__(orientation=orientation, tap_action=tap_action, **kwargs)
        self.color = color
        if width != None:
            self.width = width
        else:
            self.width = "h/4" if orientation == "horizontal" else "w/4"

        self.thumb = thumb
        self.thumb_color = thumb_color
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.thumb_icon = thumb_icon

        self.thumb_icon_color = thumb_icon_color  
        self.end_points = end_points
        self.end_colors = end_colors
        self.end_point_size = end_point_size

    #region
    @colorproperty
    def color(self) -> ColorType:
        "The color of the slider line"
        return self._color
    
    @property
    def width(self) -> PSSMdimension:
        "The width of the slider line"
        return self._width
    
    @width.setter
    def width(self, value):
        if v := isinstance(tools.is_valid_dimension(value), Exception):
            _LOGGER.error("Invalid width value", exc_info=v)
        else:
            self._width = value

    @property
    def thumb(self) -> str:
        "The type of thumb (slider handle)"
        return self._thumb
    
    @thumb.setter
    def thumb(self, value:str):
        imp = ["circle", "rectangle", "rounded_rectangle"]
        if value not in imp:
            msg = f"thumb must be one of {imp}, {value} is not valid/implemented"
            _LOGGER.exception(msg,ValueError(msg))
        else:
            self._thumb = value

    @property
    def thumb_width(self) -> PSSMdimension:
        """
        The width of the slider thumb. Parameter l for the length of the slider is additionally passed for dimensional strings.
        Set to None for automatic sizing based on shape
        """
        if self.__thumb_width != None:
            return self.__thumb_width
        else:
            d = "h" if self.orientation == "horizontal" else "w"

            if self.thumb == None:
                return 0
            elif self.thumb == "circle":
                return f"{d}/3"
            else:
                return f"{d}/6"
    
    @thumb_width.setter
    def thumb_width(self, value):
        if value == None:
            self.__thumb_width = value
        else:
            self._dimension_setter("__thumb_width",value,["l"])

    @property
    def thumb_height(self) -> PSSMdimension:
        """
        The height of the slider thumb. Parameter l for the length of the slider is additionally passed for dimensional strings.
        Set to None for automatic sizing based on shape
        """
        if self.__thumb_height != None:
            return self.__thumb_height
        else:
            d = "h" if self.orientation == "horizontal" else "w"

            if self.thumb == None:
                return 0
            elif self.thumb == "circle":
                return f"{d}/3"
            else:
                return f"{d}*0.45"
    
    @thumb_height.setter
    def thumb_height(self, value):
        if value == None:
            self.__thumb_height = value
        else:
            self._dimension_setter("__thumb_height",value,["l"])


    @colorproperty
    def thumb_color(self) -> Optional[ColorType]:
        if self._thumb_color == None:
            return self.color
        else:
            return self._thumb_color

    @property
    def thumb_icon(self) -> Optional[str]:
        """
        Icon to put on the thumb, set to None for no icon.
        Size is set according to thumb_height, so ensure your thumb fits an icon.
        """
        return self.__thumb_icon
    
    @thumb_icon.setter
    def thumb_icon(self, value:Optional[str]):
        if value == None:
            self.__thumb_icon = value
        elif value[:4] not in ALLOWED_MDI_IDENTIFIERS:
            msg = f"thumb_icon must be an mdi icon. Cannot parse {value} as such"
            _LOGGER.error(msg,exc_info=ValueError(msg))
        else:
            self.__thumb_icon = value

    @colorproperty
    def thumb_icon_color(self) -> ColorType:
        "The color of the thumb icon. If None a color is automatically applied."
        return self._thumb_icon_color

    @property
    def end_points(self) -> Optional[Union[str,tuple[str,str]]]:
        "MDI icons located on both ends of the slider. Set to a string to use the same icon for both endpoints, otherwise set to a 2 element tuple or list with the end points on [min,max] respectively."
        return self.__end_points
    
    @end_points.setter
    def end_points(self,value):
        if value == None:
            self.__end_points = value
            return
        
        if isinstance(value,str):
            points = (value,value)
        elif isinstance(value,(list,tuple)):
            if len(value) != 2:
                msg = f"List with endpoints must be exactly of 2 length"
                _LOGGER.error(msg,exc_info=ValueError(msg))
                return
            else:
                points = value

        for point in points:
            if point == None:
                continue
            if point[:4] not in ALLOWED_MDI_IDENTIFIERS:
                msg = f"endPoint icon must be an mdi icon. Cannot parse {value} as such"
                _LOGGER.error(msg,exc_info=ValueError(msg))
                return
        self.__end_points = tuple(points)
    
    @colorproperty
    def end_colors(self) -> Optional[ColorType]:
        "The colors applied to the end icons. If None, will use the same color as the slider."
        return self._end_colors

    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        if area is not None:
            self._area = area

        if self.area == None:
            return

        (x, y), (w, h) = self.area
        colorMode = self.parentPSSMScreen.imgMode

        img_background = self.background_color
        
        v_length = self.valueRange[1] - self.valueRange[0]
        if v_length == 0:
            position_perc = 0
        else:
            position_perc = (self.position - self.valueRange[0])/(v_length)

        #Setting up relative line and circle coordinates
        ##Using w or h here as length for l, should be relatively close and regardless at most yield some margins
        if self.orientation == "horizontal":
            half_tw = self._convert_dimension(self.thumb_width,{"l":w})/2
            if self.end_points == None:
                ##Icon size is set to half the height
                coo = [(int(half_tw), int(h/2)), (int(w-half_tw), int(h/2))]
            else:
                endP_size = int(h/2) if self.end_point_size == None else self._convert_dimension(self.end_point_size)
                coo = [(int(endP_size+half_tw), int(h/2)), (int(w-endP_size-half_tw), int(h/2))]
                
            line_length = coo[1][0] - coo[0][0]
            thumb_center = (line_length*position_perc + coo[0][0], h/2)

        elif self.orientation == "vertical":
            half_tw = self._convert_dimension(self.thumb_width,{"l":h})/2
            if self.end_points == None:
                coo = [(int(w/2),int(half_tw)),(int(w/2), int(h-half_tw))]
            else:
                endP_size = int(w/2) if self.end_point_size == None else self._convert_dimension(self.end_point_size)
                coo = [(int(w/2),int(endP_size+half_tw)),(int(w/2), int(h-endP_size-half_tw))]
                
            line_length = coo[1][1] - coo[0][1]
            active_length = int(position_perc*line_length)
            thumb_center = (w/2, coo[1][1]-active_length)

        self._lineCoords = coo

        self._lineLength = line_length
        "Length of the line in pixels"

        drawcolor = Style.get_color(self.color, colorMode)
        rectangle = Image.new(
            colorMode,
            (w, h),
            color=Style.get_color(img_background, colorMode)
        )
        draw = ImageDraw.Draw(rectangle)
        draw.line(
            coo,
            fill=drawcolor,
            width=self._convert_dimension(self.width,{"l":line_length})
        )

        if self.end_points != None:
            col = drawcolor if self.end_colors == None else Style.get_color(self.end_colors)
            for idx, icon in enumerate(self.end_points):
                if icon == None:
                    continue

                if self.orientation == "vertical":
                    coords = (w/2, self.lineCoords[1-idx][1] + ((-1)**idx)*(w/4))
                    size = int(w/2)
                else:
                    coords = (self.lineCoords[idx][0] - ((-1)**idx)*(h/4), h/2)
                    size = int(h/2)                
                rectangle = mdi.draw_mdi_icon(rectangle, icon, icon_coords=coords, icon_size=size, icon_color=col )

        self._lineImage = rectangle.copy()


        thumbsize = (self.thumb_width,self.thumb_height)
        ##Will probably need to check if this still functions with the drawing and parsing
        shape = self.thumb
        if shape == "rectangle":
            _, relSize = IMPLEMENTED_ICON_SHAPES["rounded_rectangle"]
        else:
            drawFunc, relSize = IMPLEMENTED_ICON_SHAPES[shape]
        
        color = None
        thumb_color = self.thumb_color if self.thumb_color != None else drawcolor
        thumb_color = Style.get_color(thumb_color,colorMode)
        if shape == "circle":
            drawArgs = {"fill":thumb_color}
        elif shape == "rounded_rectangle":
            drawArgs = {"fill":thumb_color}

        elif shape == "rectangle":
            color = thumb_color

        ##Allow for more shapes
        if self.orientation == "vertical":
            thumbsize = self._convert_dimension((self.thumb_height,self.thumb_width),{"l": line_length})
        else:
            thumbsize = self._convert_dimension((self.thumb_width,self.thumb_height),{"l": line_length})
        c = Image.new(colorMode,thumbsize,color)

        if shape != "rectangle":
            (c, drawImg) = drawFunc(c, drawArgs=drawArgs, paste=False)
        
        if self.thumb_icon != None:
            size = int(self._convert_dimension(self.thumb_height,{"l":line_length})*relSize)
            if self.thumb_icon_color == None:
                iconCol = tools.invert_Color(thumb_color, colorMode)
            else:
                iconCol = Style.get_color(self.thumb_icon_color)
            c = mdi.draw_mdi_icon(c, self.thumb_icon, icon_size=size, icon_color=iconCol)

        self._thumbImage = c.copy()

        paste_coords =(floor(thumb_center[0]-c.width/2), floor(thumb_center[1]-c.height/2))
        rectangle.alpha_composite(c,paste_coords)

        if self.inverted:
            rectangle = tools.invert_Image(rectangle)
        self._imgData = rectangle
        return self.imgData
    
    def _fast_position_update(self, new_position):
        """
        Generates a new area quickly from the new_position set, without generating a lot of new images.
        Do not set the position before calling this function, the function takes care of that.
        """

        if self.area == None or self.imgData == None:
            self.position = new_position
            return

        [(x,y),(w,h)] = self.area


        coo = self._lineCoords
        line_length = self._lineLength

        ##Determine if the slider will shift a percentage/pixel here.
        v_length = self.valueRange[1] - self.valueRange[0]
        if v_length == 0:
            old_position = 0
            position_perc = 0
        else:
            old_position = (self.position - self.valueRange[0])/(v_length)
            position_perc = (new_position - self.valueRange[0])/(v_length)
        self.position = new_position

        active_length = int(position_perc*line_length)
        old_active_length = int(old_position*line_length)

        if old_active_length == active_length:
            ##No need to update if the active length hasn't changed, since the thumb does not shift position
            return

        if self.orientation == "horizontal":
            thumb_center = (active_length + coo[0][0], h/2)
        elif self.orientation == "vertical":
            thumb_center = (w/2, coo[1][1]-active_length)

        line = self._lineImage.copy()
        thumb = self._thumbImage.copy()
        paste_coords =(floor(thumb_center[0]-thumb.width/2), floor(thumb_center[1]-thumb.height/2))

        ##How to deal with endpoints?
        line.alpha_composite(thumb,paste_coords)

        self._imgData = line

        self.parentPSSMScreen.simple_print_element(self, skipGen=True, apply_background=True)
        return

class BoxSlider(base._BaseSlider):
    """
    Makes an (interactive) slider that fills a box. See _BaseSlider for all slider specific parameters.

    Parameters
    ----------
    width : PSSMdimension, optional
        The  width of the slider, by default a quarter of the element's height/width (depends on orientation)
    active_color : ColorType, optional
        The color that fills the bar as it gets closer towards the maximum value, by default 'black'
    inactive_color : ColorType, optional
        The color that fills up the rest of the box, by default None
    outline_color : ColorType, optional
        The outline color of the box, by default None
    outline_width : int, optional
        The width of the box's outline, by default 5
    radius : int, optional
        Optional corner radius of the box, by default 5

    tap_action : Optional[Callable[[base.Element,tuple[int,int]],None]], optional
        _description_, by default None
    thumb_color : Optional[ColorType], optional
        Show a small line at the end of the active bar with color thumb_color, by default None (No thumb)
    end_points : Optional[Union[str,tuple[str,str]]], optional
        mdi Icon(s) to show at the endpoints, by default None
    end_colors : Optional[ColorType], optional
        Color of the endpoints, by default None
    end_point_size : PSSMdimension, optional
        Size of the endpoints, by default the same as the slider width.
    """

    @property
    def _emulator_icon(cls): return "mdi:arrow-right-bold-box"

    def __init__(self, active_color : ColorType = DEFAULT_FOREGROUND_COLOR, inactive_color: Optional[ColorType] = None, outline_color : Optional[ColorType] = DEFAULT_FOREGROUND_COLOR,   width : 'PSSMdimension' = None, outline_width = 5, radius=5, orientation : Literal["horizontal", "vertical"] ="horizontal", tap_action : Optional[Callable[[base.Element,tuple[int,int]],None]]=None,
            thumb_color : Optional[ColorType]=None, 
            end_points : Optional[Union[MDItype,tuple[str,str]]]=None, end_colors : Optional[ColorType]=None, end_point_size : PSSMdimension = None, **kwargs):

        
        super().__init__(orientation=orientation, tap_action=tap_action, **kwargs)
        
        
        self.outline_color = outline_color
        self.active_color = active_color
        self.inactive_color = inactive_color
        
        if width != None:
            self.width = width
        else:
            self.width = "h/4" if self. orientation == "horizontal" else "w/4"
        
        self.radius = radius
        self.outline_width = outline_width

        ##width is the direction parallel to the slider
        self.thumb_color = thumb_color
        self.end_points = end_points
        self.end_colors = end_colors
        self.end_point_size = end_point_size
    
    #region
    @colorproperty
    def active_color(self) -> ColorType:
        "The color of the bar indicating the value"
        return self._active_color

    @colorproperty
    def inactive_color(self) -> ColorType:
        "The color of the inside part of the slider that is not covered by the active part"
        return self._inactive_color

    @colorproperty
    def outline_color(self) -> ColorType:
        "Color of the box's outline"
        return self._outline_color

    @colorproperty
    def thumb_color(self) -> ColorType:
        "Show a small line at the end of the active bar with color thumb_color. Set to None for no thumb"
        return self._thumb_color

    # @thumb_color.setter
    # def thumb_color(self, value : ColorType):
    #     self._color_setter("_thumb_color", value=value)

    @colorproperty
    def end_colors(self) -> ColorType:
        "Colors of the icons at the box's end"
        return self._end_colors

    @property
    def outline_width(self) -> PSSMdimension:
        "Width of the box's outline"
        return self._outline_width
    
    @outline_width.setter
    def outline_width(self, value : PSSMdimension):
        self._dimension_setter("_outline_width", value=value)

    @property
    def radius(self) -> ColorType:
        "Corner radius of the box"
        return self._radius
    
    @radius.setter
    def radius(self, value : ColorType):
        self._dimension_setter("_radius", value=value)

    @property
    def end_point_size(self) -> ColorType:
        "Size  of the end point icons"
        return self._end_point_size
    
    @end_point_size.setter
    def end_point_size(self, value : ColorType):
        if value == None:
            self._end_point_size = value
            return
        
        self._dimension_setter("_end_point_size", value=value)

    @property
    def end_points(self) -> Optional[Union[str,tuple[str,str]]]:
        "MDI icons located on both ends of the slider. Set to a string to use the same icon for both endpoints, otherwise set to a 2 element tuple or list with the end points on [min,max] respectively."
        return self.__end_points
    
    @end_points.setter
    def end_points(self,value):
        if value == None:
            self.__end_points = value
            return
        
        if isinstance(value,str):
            points = (value,value)
        elif isinstance(value,(list,tuple)):
            if len(value) != 2:
                msg = f"List with endpoints must be exactly of 2 length"
                _LOGGER.error(msg,exc_info=ValueError(msg))
                return
            else:
                points = value

        for point in points:
            if point == None:
                continue
            if point[:4] not in ALLOWED_MDI_IDENTIFIERS:
                msg = f"endPoint icon must be an mdi icon. Cannot parse {value} as such"
                _LOGGER.error(msg,exc_info=ValueError(msg))
                return
        self.__end_points = tuple(points)
    #endregion

    def generator(self, area: list[tuple] = None, skipNonLayoutGen = False) -> Image.Image:
        if area is not None:
            self._area = area

        if self.area == None:
            return

        (x, y), (w, h) = self.area
        colorMode = self.parentPSSMScreen.imgMode
        
        img_background = self.background_color

        v_length = self.valueRange[1] - self.valueRange[0]
        if v_length == 0:
            position_perc = 0
        else:
            position_perc = (self.position - self.valueRange[0])/(v_length)

        boxW = self._convert_dimension(self.width)
        endP_size = boxW if self.end_point_size == None else self._convert_dimension(self.end_point_size)
        margin = int(boxW/6)
        if self.orientation == "horizontal":            
            if self.end_points == None:
                coo = [(0, int((h-boxW)/2)), (w, int((h+boxW)/2))]
            else:
                coo = [(floor(0+margin+endP_size), int((h-boxW)/2)), (floor(w-margin-endP_size), int((h+boxW)/2))]

            line_length = coo[1][0] - coo[0][0]
            active_length = int(position_perc*line_length)
            act_coo = [coo[0], (active_length+coo[0][0],coo[1][1])]

        elif self.orientation == "vertical":
            if self.end_points == None:
                coo = [(int((w-boxW)/2), 0), (int((w+boxW)/2),h)]
            else:
                coo = [(int((w-boxW)/2), floor(0+margin+boxW)), (int((w+boxW)/2),floor(h-margin-boxW))]
            
            line_length = coo[1][1] - coo[0][1]
            active_length = int(position_perc*line_length)
            act_coo = [(coo[0][0],coo[1][1]- active_length), coo[1]]

        self._lineCoords = coo
        self._lineLength = line_length

        rectangle = Image.new(
            colorMode,
            (w, h),
            color=Style.get_color(img_background, colorMode)
        )
        radius = self._convert_dimension(self.radius,{"l":line_length})
        drawArgs = {"xy": coo,
                    "radius": radius,
                    "fill": Style.get_color(self.inactive_color,colorMode)
                    }
        (rectangle, _) = DrawShapes.draw_rounded_rectangle(rectangle,drawArgs,rescale=["xy","radius","width"])

        if self.end_points != None:
            col = Style.get_color(self.active_color,colorMode) if self.end_colors == None else Style.get_color(self.end_colors, colorMode)
            for idx, icon in enumerate(self.end_points):
                if icon == None:
                    continue

                if self.orientation == "vertical":
                    coords = (w/2, self.lineCoords[1-idx][1] + ((-1)**idx)*(boxW/2))
                else:
                    coords = (self.lineCoords[idx][0] - ((-1)**idx)*(boxW/2), h/2)
                rectangle = mdi.draw_mdi_icon(rectangle, icon, icon_coords=coords, icon_size=endP_size, icon_color=col )

        self._sliderBaseImg = rectangle.copy()

        if active_length > 0:
            actArgs = {"xy": act_coo,
                        "radius": radius,
                        "fill": Style.get_color(self.active_color,colorMode),
                        "outline": None,
                        "width": 0
                        }
            (paste_rectangle, _) = DrawShapes.draw_rounded_rectangle(rectangle,actArgs,rescale=["xy","radius","width"], paste=False)
            rectangle.alpha_composite(paste_rectangle)

            thumb_width = margin
            if self.thumb_color != None:
                if self.orientation == "horizontal":
                    thumbX = (act_coo[1][0] - margin - thumb_width,)*2
                    thumbY = (act_coo[0][1] + margin, act_coo[1][1] - margin)
                else:
                    thumbX = (act_coo[0][0] + margin, act_coo[1][0] - margin)
                    thumbY = (act_coo[0][1] + margin + thumb_width,)*2
                xy=[(thumbX[0],thumbY[0]),(thumbX[1],thumbY[1])]
                col = Style.get_color(self.thumb_color,colorMode)
                draw = ImageDraw.Draw(rectangle)
                draw.line(
                    xy=xy,
                    fill= col,
                    width= thumb_width,
                    joint="curve"
                )
        
        ##Draws the outline
        drawArgs = {"xy": coo,
                    "radius": radius,
                    "outline": Style.get_color(self.outline_color,colorMode),
                    "width": self._convert_dimension(self.outline_width,{"l":line_length})
                    }
        (paste_rectangle, _) = DrawShapes.draw_rounded_rectangle(rectangle,drawArgs,rescale=["xy","radius","width"],paste=False)
        
        rectangle.alpha_composite(paste_rectangle)

        if self.inverted:
            rectangle = tools.invert_Image(rectangle)
        self._imgData = rectangle
        return self.imgData

    def _fast_position_update(self, new_position : float):
        """
        Generates a new area quickly from the new_position set, without generating a lot of new images.
        Do not set the position before calling this function, the function takes care of that.
        """

        if self.area == None or self.imgData == None:
            self.position = new_position
            return

        [(x,y),(w,h)] = self.area

        coo = self._lineCoords
        line_length = self._lineLength

        v_length = self.valueRange[1] - self.valueRange[0]
        if v_length == 0:
            old_position = 0
            position_perc = 0
        else:
            old_position = (self.position - self.valueRange[0])/(v_length)
            position_perc = (new_position - self.valueRange[0])/(v_length)
        
        self.position = new_position

        active_length = int(position_perc*line_length)
        old_active_length = int(old_position*line_length)

        if old_active_length == active_length:
            ##No need to update if the active length hasn't changed, since the thumb does not shift position
            return

        if self.orientation == "horizontal":
            act_coo = [coo[0], (active_length+coo[0][0],coo[1][1])]
        elif self.orientation == "vertical":
            act_coo = [(coo[0][0],coo[1][1]- active_length), coo[1]]

        colorMode = self.parentPSSMScreen.imgMode
        baseImg = self._sliderBaseImg.copy()

        radius = self._convert_dimension(self.radius,{"l":line_length})
        
        if active_length > 0:
            actArgs = {"xy": act_coo,
                "radius": radius,
                "fill": Style.get_color(self.active_color,colorMode),
                "outline": None,
                "width": 0
                }
            (img, _) = DrawShapes.draw_rounded_rectangle(baseImg,actArgs,rescale=["xy","radius","width"], paste=False)
            

            if self.thumb_color != None:
                margin = int(self._convert_dimension(self.width)/6)
                thumb_width = margin
                if self.orientation == "horizontal":
                    thumbX = (act_coo[1][0] - margin - thumb_width,)*2
                    thumbY = (act_coo[0][1] + margin, act_coo[1][1] - margin)
                else:
                    thumbX = (act_coo[0][0] + margin, act_coo[1][0] - margin)
                    thumbY = (act_coo[0][1] + margin + thumb_width,)*2
                xy=((thumbX[0],thumbY[0]),(thumbX[1],thumbY[1]))
                draw = ImageDraw.Draw(img)
                draw.line(
                    xy=xy,
                    fill=Style.get_color(self.thumb_color,colorMode),
                    width=thumb_width,
                )

            baseImg.paste(img,mask=img)
        img = baseImg

        if self.outline_color != None:
            drawArgs = {"xy": coo,
            "radius": radius,
            "outline": Style.get_color(self.outline_color,colorMode),
            "width": self._convert_dimension(self.outline_width,{"l":line_length})
            }
            (outl_img, _) = DrawShapes.draw_rounded_rectangle(img,drawArgs,rescale=["xy","radius","width"])
            img.paste(outl_img, mask=outl_img)

        ##Euuhhh performance of this is surprisingly very good lol
        self._imgData = img
        self.parentPSSMScreen.simple_print_element(self, skipGen=True, apply_background=True)

        return

class Slider(LineSlider, BoxSlider):
    """
    Element combining all the different sliders to be used in a single element. Set the type of slider by setting the style property.
    Properties for any style can be passed as kwargs.
    
    Parameters
    ----------
    style : Literal[&quot;line&quot;, &quot;box&quot;], optional
        Slider style. Current has BoxSlider and LineSlider elements implemented, by default "line"
    orientation : Literal[&quot;horizontal&quot;, &quot;vertical&quot;], optional
        Slider orientation, by default "horizontal"
    """

    @property
    def _emulator_icon(cls): return "mdi:tune-variant"

    def __init__(self, style : Literal["line", "box"] = "line", orientation : Literal["horizontal", "vertical"] ="horizontal", **kwargs):

        self.style = style

        ##This may work in at least having everything working?
        if self.style == "box":
            LineSlider.__init__(self, orientation=orientation,_register=False)
            BoxSlider.__init__(self, orientation=orientation,**kwargs)
        elif self.style == "line":
            BoxSlider.__init__(self, orientation=orientation, _register=False)
            LineSlider.__init__(self, orientation=orientation, **kwargs)

    #region
    @property
    def style(self) -> Literal["line", "box"]:
        """
        The style of the slider, i.e. whether it displays a box or line slider. 
        When changing this after initiating the instance object, it should work out of the box, but be mindful things may work wonky.
        """
        return self.__style
    
    @style.setter
    def style(self, value : Literal["line", "box"]):
        styles = ["line", "box"]
        if value not in styles:
            msg = f"Slider style must be one of {styles}, not {value}"
            _LOGGER.exception(ValueError(msg))
        else:
            self.__style = value

        return

    @property
    def thumb_color(self):
        if self.style == "line":
            return LineSlider.thumb_color.fget(self)
        elif self.style == "box":
            return BoxSlider.thumb_color.fget(self)
    
    @thumb_color.setter
    def thumb_color(self, value : ColorType):
        if self.style == "line":
            val = LineSlider.thumb_color.fset(self, value)
        elif self.style == "box":
            val =  BoxSlider.thumb_color.fset(self, value)
        return val

    @property
    def SliderClass(self) -> Union[type[LineSlider], type[BoxSlider]]:
        "Quickhand function to get the correct class"
        if self.style == "line":
            return LineSlider
        elif self.style == "box":
            return BoxSlider
    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        if self.style == "box":
            img = BoxSlider.generator(self, area, skipNonLayoutGen)
        elif self.style == "line":
            img = LineSlider.generator(self, area, skipNonLayoutGen)
        return img

    def _fast_position_update(self, new_position : float):
        
        if hasattr(self.SliderClass, "_fast_position_update"):
            self.SliderClass._fast_position_update(self, new_position)
        else:
            asyncio.create_task(self.async_update({"position": new_position},forceGen=True))

class TimerSlider(Slider):
    """
    A slider that can be used as a timer. 
    Minimum and Maximum will be assumed to be in seconds.

    Parameters
    ----------
    count : Literal[&quot;up&quot;,&quot;down&quot;]
        Whether to do a count up or count down (i.e. move from minimum to maximum or vice versa)
    style : Literal[&#39;line&#39;] | Literal[&#39;box&#39;], optional
        Slider style, by default "line"
    orientation : Literal[&#39;horizontal&#39;] | Literal[&#39;vertical&#39;], optional
        Slider orientation, by default "horizontal"
    """

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["base.Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return Slider.action_shorthands | {"start-timer": "start_timer", "pause-timer": "pause_timer", "cancel-timer": "cancel_timer", "toggle-timer": "toggle_timer"}

    @property
    def _emulator_icon(cls): return "mdi:timeline-clock"

    def __init__(self, count : Literal["up","down"], style: Literal['line','box'] = "line", orientation: Literal['horizontal','vertical'] = "horizontal",
                interactive=False, **kwargs):
        
        self.__area = None
        self._lineLength = None

        self._timerTask : asyncio.Task = DummyTask()
        "Task running the timed slider update loop"

        self.__timerLock = asyncio.Lock(loop=self.mainLoop)

        super().__init__(style, orientation, interactive=interactive, **kwargs)
        
        self.count = count
        if self.count == "up":
            self.position = self.minimum
        elif self.count == "down":
            self.position = self.maximum

    #region
    @property
    def count(self) -> Literal["up","down"]:
        return self.__count
    
    @count.setter
    def count(self, value):
        if value not in {"up","down"}:
            msg = f"Counter value must be either up or down, {value} is not valid."
            _LOGGER.exception(ValueError(msg))
            return
        
        if not self._timerTask.done() and value != self.count:
            _LOGGER.warning(f"{self.id} changed count value. Don't forget to restart the timer.")
        self.__count = value

    @property
    def running(self) -> bool:
        "True if the timer is currently running"
        if self._timerTask.done() or not self.__timerLock.locked():
            return False
        else:
            return True

    @property
    def _area(self):
        """
        Private area property. Has a setter to restart the timerTask when the area changes. Generally don't touch this.
        """
        return self.__area

    @_area.setter
    def _area(self, value):
        ##See if this works
        if value == self.__area:
            return
        
        self.__area = value

        ##This should restart the task when it changes
        if not self._timerTask.done():
            self._timerTask.cancel()
            self.start_timer()

    @Slider.minimum.setter
    def minimum(self, value):
        if value == getattr(self,"minimum",None):
            return
        Slider.minimum.fset(self, value)
        if not self._timerTask.done():
            self._timerTask.cancel()
            self.start_timer()

    @Slider.maximum.setter
    def maximum(self, value):
        if value == getattr(self,"maximum",None):
            return
        Slider.maximum.fset(self, value)
        if not self._timerTask.done():
            self._timerTask.cancel()
            self.start_timer()
    #endregion

    async def _timed_update(self):
        if self.area == None:
            _LOGGER.info("A timer cannot be started before it has been generated, will keep time for now.")
            wait_time = 1
            if hasattr(self,"on_add"):
                old_add = self.on_add
                def wrapped_add(*args):
                    old_add()
                    self._timerTask.cancel()
                    self.start_timer()
                    self.on_add = old_add
            else:
                def wrapped_add(*args):
                    if not self._timerTask.done():
                        self._timerTask.cancel()
                        self.start_timer()
                    delattr(self,"on_add")
            self.on_add = wrapped_add            
        else:
            if self.imgData == None and self._lineLength == None:
                await asyncio.sleep(0)
                if self.isGenerating:
                    _LOGGER.debug(f"Waiting to start timer {self.id} until generating is finished")
                    await self._await_generator()
                else:
                    await asyncio.wait_for(
                        self.async_generate(),5)
                    _LOGGER.debug("Done waiting for slider gen")

            _LOGGER.debug(f"Starting timer of {self.id}")
            pixel_length = self._lineLength
            total_seconds = self.maximum - self.minimum
            wait_time = total_seconds/pixel_length
        incr = wait_time*(1 if self.count == "up" else -1)
        
        if self.onScreen:
            await asyncio.to_thread(
                self.parentPSSMScreen.simple_print_element,element=self,skipGen=True,apply_background=True)

        async with self.__timerLock:
            while (self.minimum <= self.position <= self.maximum):
                try:
                    await asyncio.sleep(wait_time) #@IgnoreExceptions
                    new_position = self.position + incr
                    if self.onScreen:
                        await self.async_set_position(new_position) #@IgnoreExceptions
                        continue
                    else:
                        self.position = new_position
                except asyncio.CancelledError:
                    _LOGGER.debug(f"Timer {self.id} stopped before being done")
                    return False

    def start_timer(self, reset=False, *args):
        " Starts the timer. If the timer previously reached its end, it will be restarted."

        ##Second condition ensures the timer can be restart if it is paused
        d = self._timerTask.done()
        c = self._timerTask.cancelled()
        if (self._timerTask.done() and not self._timerTask.cancelled()) or reset:
            if self.count == "up":
                self.position = self.minimum
            elif self.count == "down":
                self.position = self.maximum

        loop = self.parentPSSMScreen.mainLoop
        self._timerTask = loop.create_task(self._timed_update())

    async def await_timer(self, reset=True, *args) -> bool:
        """
        Starts the timer, and returns when it finishes

        Parameters
        ----------
        reset : bool, optional
            Reset the timer if it not running  currently, by default True
        
        Returns
        ----------
        bool :
            True if the timer finished, False if it was paused or cancelled.
        """
        if self._timerTask.done() and not self._timerTask.cancelled() and reset:
            if self.count == "up":
                self.position = self.minimum
            elif self.count == "down":
                self.position = self.maximum

        if self._timerTask.done():
            loop = self.parentPSSMScreen.mainLoop
            self._timerTask = loop.create_task(self._timed_update())

        try:
            await self._timerTask #@IgnoreExceptions
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0)
        if self._timerTask.cancelled():
            return False
        else:
            return True

    def pause_timer(self, *args):
        "Pauses the timer without resetting its position."
        self._timerTask.cancel()
        _LOGGER.debug(f"Timer {self.id} paused")

    def cancel_timer(self, *args):
        "Stops the timer from running, and resets the position to its minimum/maximum (for count up/down respectively)"
        self._timerTask.cancel()
        if self.count == "up":
            new_position = self.minimum
        elif self.count == "down":
            new_position = self.maximum

        self.set_position(new_position)
        _LOGGER.debug(f"Timer {self.id} cancelled")

    def toggle_timer(self, *args):
        "Toggles the timer between running and paused"
        if self.running:
            self.pause_timer()
        else:
            self.start_timer()

#endregion


class CheckBox(base._BoolElement, base.Icon):
    """
    Checkbox element. Derived from the base icon, accepts every option from Icon except icon, which is controlled by the state.

    Parameters
    ----------
    checked : bool, optional
        Initial state of the element, by default False (unchecked)
    checked_icon : _type_, optional
        icon to indicate the box is checked (i.e. element state is true), by default "mdi:check"
    unchecked_icon : Optional[MDItype], optional
        icon to indicate the element is not checked, by default None
    on_set : Callable[[&quot;CheckBox&quot;, bool],Any], optional
        function to call when the element is checked/unchecked, by default None
    state_attributes : dict[True : dict, False : dict], optional
        When calling set_state, these attributes will be changed to the value in the corresponding state, by default {True:{},False: {}}
    background_shape : str, optional
        background shape of the box, by default "rounded_rectangle". Accepts None for no background
    background_color : ColorType, optional
        element background(shape) color, by default "white"
    show_feedback : bool, optional
        show on screen feedback when interacting with the element (aside from toggling the element), by default False
    """
    
    @property
    def _emulator_icon(cls): return "mdi:checkbox-multiple-outline"

    def __init__(self, checked : bool = False, checked_icon : Optional[MDItype] = "mdi:check", unchecked_icon : Optional[MDItype] = None, 
                on_set : Callable[["CheckBox", bool],Any] = None, state_attributes : base.CheckStateDict ={True:{},False: {}},
                background_shape = "rounded_rectangle", background_color : ColorType= "white", show_feedback : bool = True, **kwargs):

        base.Icon.__init__(self, icon=None, show_feedback=show_feedback, background_color = background_color, background_shape=background_shape, **kwargs)
        base._BoolElement.__init__(self, checked,on_set,state_attributes)
        
        self.checked_icon = checked_icon
        self.unchecked_icon = unchecked_icon

    #region
    @property
    def icon(self) -> Union[MDItype, str]:
        "The current icon of the element"
        if self.state:
            return self.checked_icon
        else:
            return self.unchecked_icon
    
    @icon.setter
    def icon(self, value):
        if self.onScreen:
            msg = f"CheckButton does not allow icon to be set directly."
            _LOGGER.error(AttributeError(msg))

    @property
    def checked(self) -> bool:
        "True if the box is considered checked. Returns the elements state."
        return self.state

    @property
    def checked_icon(self) -> Optional[Union[MDItype,str]]:
        "The icon that indicates the CheckBox is checked"
        return self.__checked_icon
    
    @checked_icon.setter
    def checked_icon(self, value):
        self._icon_setter("__checked_icon",value,allow_none=True)
    
    @property
    def unchecked_icon(self) -> Optional[Union[MDItype,str]]:
        "The icon that indicates the CheckBox is not checked"
        return self.__unchecked_icon
    
    @unchecked_icon.setter
    def unchecked_icon(self, value):
        self._icon_setter("__unchecked_icon",value,allow_none=True)
    #endregion

    def generate_feedback_icon(self, img: Image.Image, background_color: ColorType, size: tuple[wType, hType]) -> Optional[Image.Image]:
        
        if self.state:
            fb_icon = self.unchecked_icon
        else:
            fb_icon = self.checked_icon
        
        if fb_icon == None:
            return None
        
        imgMode = img.mode

        
        if self.background_color == None:
            bg = self.parentBackground
        else:
            bg = self.background_color
        
        icon_size = None
        icon_coords = None

        if self.background_shape != None:

            ##Can't use the bg from the else statement since the sizing would get messed up
            fb_img = Image.new(img.mode,img.size,self.background_color)
            fb_img.putalpha(img.getchannel("A"))

            draw_size = min(img.size)
            relSize = DrawShapes.get_relative_size(self.background_shape)
            icon_size = self.shape_settings.get("icon_size",floor(draw_size*relSize))

            if "icon_coords" in self.shape_settings:
                icon_coords = self.shape_settings["icon_coords"]

        else:
            fb_img = Image.new(img.mode, img.size, None)
            icon_size = None
            
            if  bg == None:
                [(x,y),(w,h)] = self.area[:]
                box = [x,y,x+w,y+h]
                bg_img = self.parentPSSMScreen.backgroundImage.crop(box)
            else:
                bg_img = Image.new(img.mode, size, bg) 
        
        fb_img = mdi.draw_mdi_icon(fb_img,fb_icon, icon_coords, icon_size, self._iconColorValue)
        fb_img = ImageOps.pad(fb_img,size)
        
        if self.background_shape != None:
            ##Don't need to paste if there is a background
            return fb_img
        else:
            if imgMode == "RGBA":
                bg_img.alpha_composite(fb_img)
            elif "A" in imgMode:
                bg_img.paste(fb_img,mask=fb_img.getchannel("A"))
            else:
                bg_img.paste(fb_img,mask=fb_img.getchannel("A"))

            return bg_img

class Toggle(CheckBox):
    """
    CheckBox element, but with a toggle switch as icon. (I.e. the same as a CheckBox with checked_icon = mdi:toggle-switch and unchecked_icon = mdi:toggle-switch-off)

    Parameters
    ----------
    state : bool, optional
        Initial element state, by default False
    on_set : Callable[[&quot;CheckBox&quot;, bool],Any], optional
        function to call when the element is checked/unchecked, by default None
    state_attributes : _type_, optional
        When calling set_state, these attributes will be changed to the value in the corresponding state, by default {True:{},False: {}}
    show_feedback : bool, optional
        show on screen feedback when interacting with the element (aside from toggling the element), by default False
    """

    @property
    def _emulator_icon(cls): return "mdi:toggle-switch"

    def __init__(self, state : bool =False, on_set : Callable[["CheckBox", bool],Any] =None, state_attributes : base.CheckStateDict = {True:{},False: {}}, show_feedback : bool = True, **kwargs):
        base.Icon.__init__(self, icon=None, show_feedback=show_feedback, **kwargs)
        base._BoolElement.__init__(self, state,on_set,state_attributes)

    @property
    def checked_icon(self) -> Optional[Union[MDItype,str]]:
        "The icon that indicates the CheckBox is checked"
        return "mdi:toggle-switch"
    
    @property
    def unchecked_icon(self) -> Optional[Union[MDItype,str]]:
        "The icon that indicates the CheckBox is not checked"
        return "mdi:toggle-switch-off"

class CheckButton(base._BoolElement, base.Button):
    "Boolean Text Element (Changes settings based on state. Defaults to coloring in the background.)"
    pass

class DropDown(base.Button):
    """
    Text element which opens a dropdown menu showing options to select.

    Parameters
    ----------
    options : list[str]
        List of options that will show up in the menu popup
    selected : int, optional
        Index of the initial option to select, by default 0
    on_select : Callable[[base.Element,str],Any], optional
        A function that will be called when an item is selected from the menu. Needs to accept an element and the value of the selected option, by default None
    closed_icon : MDIicon, optional
        Icon shown when the menu is closed. Set to None to hide, by default "mdi:menu-down"
    opened_icon : MDIicon, optional
        Icon shown when the menu is opened. Set to None to hide, by default "mdi:menu-up"
    margins : PSSMdimension, optional
        margins to apply, same as button margins. By default None, which will automatically set them to correctly align the text and the icon.
    radius : PSSMdimension, optional
        Radius of the button corners, by default "h*0.2"
    outline_color : str, optional
        Color of the button outline, by default "black"
    outline_width : PSSMdimension, optional
        Width of the button outline, by default 5
        """

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["base.Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return base.Button.action_shorthands | {"select": "_async_select", "open-menu": "open_menu", "close-menu": "close_menu"}

    @property
    def _emulator_icon(cls): return "mdi:form-select"

    def __init__(self, options : list[str], selected : int=0, on_select : Callable[[base.Element,str],Any] = None,
                closed_icon : MDItype = "mdi:menu-down", opened_icon : MDItype = "mdi:menu-up", 
                margins : PSSMdimension = None, radius : PSSMdimension="h*0.2",
                background_color : ColorType = DEFAULT_BACKGROUND_COLOR,  outline_color : ColorType = None, outline_width : PSSMdimension = 5, **kwargs):
        set_margins = True if margins == None else False
            
        super().__init__(text = None, background_color=background_color, **kwargs)
        if not isinstance(options, (list,tuple)):
            options = list(options)

        self.__text = options[selected]
        self._selected = selected
        self.text_anchor_alignment = ("l","m")

        self.options = options
        "The options that can be chosen from"

        self.closed_icon = closed_icon
        self.opened_icon = opened_icon

        self.outline_color = outline_color
        self.outline_width = outline_width
        self.radius = radius

        self.tap_action = self.select
        self.show_feedback = True
        self._menuInvertTime = 0.3
        "Time to invert menu items for"

        if "tap_action" not in kwargs:
            self.tap_action = self.open_menu

        self._on_select_data = {}
        self._on_select_map = {}
        self.on_select = on_select

        if set_margins and self.outline_width != 0:
            if isinstance(self.outline_width,str):
                bottom_margin = f"-1*({self.outline_width})"
            else:
                bottom_margin = -1*self.outline_width

            self.margins = (0,0,bottom_margin)
        self.__menuOpen = False

    #region
    @property
    def text(self) -> str:
        "The text shown on the main button. Cannot be changed, instead set selected to the right integer, or call the select method"
        return self.options[self.selected]

    @property
    def selected(self) -> int:
        "The current index of the selected option"
        return self._selected
    
    @property
    def selected_option(self) -> str:
        "The value of the currently selected option"
        return self.options[self.selected]

    @property
    def menuOpen(self) -> bool:
        "Returns true if the menu popup is currently considered opened"
        return self.__menuOpen  

    @elementaction
    def on_select(self) -> Callable[["DropDown",str],Any]:
        """
        Function to call when an option is selected from the menu.
        
        2 Parameters are passed to the function:

        ----------
        element : Element
            The DropDown element this is attached to
        option : str
            The string with the selected option
        """
        return self._on_select

    @property
    def closed_icon(self) -> MDItype:
        "The icon shown at the right hand of the element when the dropdown menu is not open"
        return self.__closed_icon
    
    @closed_icon.setter
    def closed_icon(self, value : MDItype):
        if value != None:
            if not mdi.is_mdi(value):
                _LOGGER.error(f"Could not set closed_icon to {value}")
                return
        self.__closed_icon = value

    @property
    def opened_icon(self) -> MDItype:
        "The icon shown at the right hand of the element when the dropdown menu is open"
        return self.__opened_icon
    
    @opened_icon.setter
    def opened_icon(self, value : MDItype):
        if value != None:
            if not mdi.is_mdi(value):
                _LOGGER.error(f"Could not set opened_icon to {value}")
                return
        self.__opened_icon = value
    #endregion

    def generator(self, area=None, skipNonLayoutGen=False):
        img = super().generator(area, skipNonLayoutGen)
        if img == None:
            return
        
        if self.closed_icon != None and not self.menuOpen:
            icon_coords = (int(img.width-img.height/2),int(img.height/2))
            img = mdi.draw_mdi_icon(img, self.closed_icon, icon_coords=icon_coords, icon_color=self.font_color)
        elif self.opened_icon != None and self.menuOpen:
            icon_coords = (int(img.width-img.height/2),int(img.height/2))
            img = mdi.draw_mdi_icon(img,self.opened_icon, icon_coords=icon_coords, icon_color=self.font_color)
        self._imgData = img
        
        return img
    
    def select(self, select : Union[int,str], update : bool =True, *args):
        """
        Select an option in the menu item. 

        Parameters
        ----------
        select : Union[int,str]
            index of the option to select or a string corresponding to it.
        update : bool
            call the element update after selecting
        """
        self.parentPSSMScreen.mainLoop.create_task(self._async_select(select, update))
        
    async def _async_select(self, select : Union[int,str], update : bool =True):    
        """
        Async function that handles selecting an option in the menu item. 

        Parameters
        ----------
        select : Union[int,str]
            index of the option to select or a string corresponding to it.
        update : bool
            call the element update after selecting
        """
        if isinstance(select,int):
            self._selected = select
        else:
            if select not in self.options:
                msg = f"{select} is not a possible option in this menu. Options are: {self.options}"
                _LOGGER.exception(msg,ValueError(msg))
                return
            i = self.options.index(select)
            self._selected = i

        if self.on_select != None:
            await tools.wrap_to_coroutine(self.on_select,self,self.selected_option, **self.on_select_kwargs)
    
        if update:
            await self.async_update(updated=True)

    async def _select_from_menu(self,elt : base.Button, coords : tuple):
        "Function that is called when an option in the menu is tapped"

        await asyncio.sleep(self._menuInvertTime)
        await asyncio.gather(
            self._menuPopup.async_close(),
            self._async_select(elt.text),
            loop=self.parentPSSMScreen.mainLoop
        )

    async def _menu_closed(self):
        _LOGGER.debug("Closing popup")
        self.__menuOpen = False

    async def open_menu(self, elt : base.Element = None, coords : tuple = None):
        "Open the menu"
        ##Add a radius parameter to the popup class? If necessary, maybe the layout one already works.
        ##Pass it by converting the radius to an integer btw.
        [(x,y),(w,h)] = self.area
        yPop = y + h
        outW = self._convert_dimension(self.outline_width)
        r = self._convert_dimension(self.radius)

        hPop = len(self.options)*(self._convert_dimension(self.font_size))*1.5 + outW
        if yPop+hPop > self.parentPSSMScreen.height:
            yPop = y - hPop 

        menu_layout = []
        margins = (0,0,0,"w*0.05")
        bHeight = f"h/{len(self.options)*1.025}"
        for op in self.options:
            button = base.Button(op, self.font, self.font_size,self.font_color, 
                                text_anchor_alignment=("l","m"), margins=margins,
                                tap_action=self._select_from_menu, show_feedback=True, feedback_duration=self._menuInvertTime, _register=False)
            row = [bHeight,(button,"w")]
            menu_layout.append(row)
        self.__menuOpen = True 
        
        popupbg = self.background_color
        if popupbg == None:
            popupbg = DEFAULT_BACKGROUND_COLOR
        self._menuPopup = base.Popup(menu_layout,w,hPop,x,yPop,
                                    outline_width=outW, outline_color=self.outline_color, radius=r,
                                    on_remove=self._menu_closed, popupID=None, background_color=popupbg, blur_background=False)

        await asyncio.gather(
            self._menuPopup.async_show(),
            self.async_update(forceGen=True)
        )

    async def close_menu(self, *args):
        await self._menuPopup.async_close()

class Counter(base._TileBase):
    """
    Tile based element that can increment a numeric value with two buttons.

    Parameters
    ----------
    value : float, optional
        The starting value, by default 0
    step : float, optional
        The value to increase/decrease the counter by when pressing the respective button, by default 1
    minimum : float, optional
        Minmum counter value, by default None (No minimum)
    maximum : float, optional
        Maximum counter value, by default None (No maximum)
    on_count : Callable, optional
        Optional function to call when the counter value is changed, defaults to None
    counter_layout : str, optional
        The counter layout, as a string. See the description of the property for more explanation on how to use it. By default "count,[up;down]"
    downIcon : MDItype, optional
        Mdi icon of the decrementing button, by default "mdi:minus-box"
    upIcon : MDItype, optional
        Mdi icon of the incrementing button, by default "mdi:plus-box"
    horizontal_sizes : dict[str,PSSMdimension], optional
            horizontal sizes for the tile elements, by default None, which applies default values depending on the value of counter_layout
    vertical_sizes : dict[str,PSSMdimension], optional
            vertical sizes for the tile elements, by default None, which applies default values depending on the value of counter_layout
    element_properties : dict[str,dict[str,str]], optional
            Properties for the counter elements, by default {"count": {}, "up": {"icon_color": "foreground"},"down": {"icon_color": "foreground"}}
    """

    @classproperty
    def action_shorthands(cls) -> dict[str,Callable[["base.Element", CoordType],Any]]:
        "Shorthand values mapping to element specific functions. Use by setting the function string as element:{function}"
        return base._TileBase.action_shorthands | {"set-value": "interact_set_counter", "increment": "increment", "decrement": "decrement"}

    _restricted_element_properties : dict[str,set[str]] = {"count": {"text"}, "up": {"icon", "tap_action"}, "down": {"icon", "tap_action"}}
    "Properties of the elements that are not allowed to be set."

    @property
    def _emulator_icon(cls): return "mdi:counter"

    def __init__(self, counter_layout : Union[Literal["default", "horizontal"], PSSMLayoutString] = "default", value : float = 0, step : float = 1, roundDigits : int = None, minimum : float = None, maximum : float = None, 
                on_count : Callable[["Counter",Union[float,int]],Any] = None,  downIcon : MDItype = "mdi:minus-box", upIcon : MDItype = "mdi:plus-box", 
                horizontal_sizes : dict[str,PSSMdimension] = None, vertical_sizes : dict[str,PSSMdimension] = None, 
                element_properties : dict[str,dict[str,str]] = {"count": {}, "up": {"icon_color": "foreground"},"down": {"icon_color": "foreground"}},
                **kwargs):     

        self._tile_layout = None
        self._on_count = None
        
        self._on_count_data = {}
        self._on_count_map = {}
        self.on_count = on_count

        self.downIcon = downIcon
        self.upIcon = upIcon

        downButton = base.Icon(self.downIcon, tap_action=self.decrement)
        upButton = base.Icon(self.upIcon, tap_action=self.increment)
        countButton = base.Button(str(value))

        self.__elements = MappingProxyType({"count": countButton, "up": upButton, "down": downButton})

        default_properties = {"count": {"font_color": "foreground"}, "up": {"icon_color": "foreground"},"down": {"icon_color": "foreground"}}

        for elt in default_properties:
            set_props = element_properties.get(elt, {})
            default_properties[elt].update(set_props)

        element_properties = default_properties

        self.counter_layout = counter_layout

        if not isinstance(vertical_sizes, dict):
            if counter_layout == "default":
                vertical_sizes = {"outer": "h*0.1", "up": "?", "down": "?"}
            elif counter_layout == "horizontal":
                vertical_sizes = {"up": "?", "down": "?", "outer": "h*0.05"}
            else:
                vertical_sizes = {}

        if not isinstance(horizontal_sizes, dict):
            if counter_layout == "default":
                horizontal_sizes = {"count": "w*0.6", "up": "r", "down": "r"}
            elif counter_layout == "horizontal":
                horizontal_sizes = {"up": "r", "down": "r"}
            else:
                horizontal_sizes = {}

        super().__init__(self.tile_layout, element_properties=element_properties, horizontal_sizes=horizontal_sizes, vertical_sizes= vertical_sizes,  **kwargs)

        self.minimum = minimum
        self.maximum = maximum
        self.unit = None

        self.step = step
        self.roundDigits = roundDigits
        self.value = value

    #region
    @property
    def elements(self) -> MappingProxyType[Literal["count","up","down"],base.Element]:
        "The elements in the counter"
        return self.__elements
    
    @property
    def counter_layout(self) -> str:
        """
        The counter layout, as a string. Needs to contain up, down and count to indicate where to place the up Icon, down Icon and counter Button respectively.
        Use ',' to separate columns, and ';' to separate rows. You can encapsulate within [...] to use a sublayout, so you can stack items within a single row, for example. \n
        Examples: 
            count,[up;down] \n
            down,count,up   
        """
        return self.__counter_layout
    
    @counter_layout.setter
    def counter_layout(self, value:str):
        if value.lower() == "default":
            layout_str = "count,[up;down]"
        elif value.lower() in {"horizontal","hor"}:
            layout_str = "down,count,up"
        else:
            layout_str = value

        self.__counter_layout = value
        self.tile_layout = layout_str

    @property
    def valueText(self) -> str:
        if self.unit == None:
            return self.value
        else:
            return f"{self.value}{self.unit}"

    @property
    def value(self) -> float:
        "The current value of the counter"
        if self.roundDigits == 0:
            return int(self._value)
        else:
            return round(self._value, self.roundDigits)
    
    @value.setter
    def value(self, value : Union[float,int]):
        self._value = float(value)
        self.elements["count"].update({"text": self.valueText} ,skipPrint=self.isUpdating)

    @property
    def roundDigits(self) -> int:
        "Amount of digits to round of the new value to. Defaults to the amount in step."
        return self.__roundDigits
    
    @roundDigits.setter
    def roundDigits(self, value : Optional[int]):
        if value == None:
            v = str(self.step)
            if "." not in v:
                value = 0
            else:
                value = len(str(self.step).split(".")[1])
        if not isinstance(value,int):
            msg = f"Round digits must be an integer type. {value} is of incorrect type {type(value)}"
            _LOGGER.error(TypeError(msg))
            return
        self.__roundDigits = value

    @property
    def minimum(self) -> Optional[float]:
        "The minimum value of the counter. Set to None for no minimum"
        return self.__min
    
    @minimum.setter
    def minimum(self, value : Optional[Union[float,int]]):
        if value == None:
            self.__min = value
        else:
            self.__min = float(value)

    @property
    def unit(self) -> Optional[str]:
        "The unit of the counter value. Suffixed to the value if not None"
        return self.__unit
    
    @unit.setter
    def unit(self, value : str):
        if value == None:
            self.__unit = value
            return
        self.__unit = str(value)

    @elementaction
    def on_count(self) -> Callable[["Counter",Union[float,int]],Any]:
        "Function that is called when the counter value changes. Passes the counter itself and the new value."
        return self._on_count

    @property
    def maximum(self) -> float:
        "The maximum value of the counter. Set to None for no maximum"
        return self.__max
    
    @maximum.setter
    def maximum(self, value : Optional[Union[float,int]]):
        if value == None:
            self.__max = value
        else:
            self.__max = float(value)

    @property
    def step(self) -> float:
        "The value with which to increase/decrease the counter when calling increment/decrement"
        return self.__step

    @step.setter
    def step(self, value : Union[float,int]):
        self.__step = float(value)

    @property
    def upIcon(self) -> MDItype:
        "The icon to show on the up button"
        return self.__upIcon
    
    @upIcon.setter
    def upIcon(self, value : MDItype):
        if not mdi.is_mdi(value):
            _LOGGER.error(f"Could not set upIcon to {value}")
            return
        self.__upIcon = value

    @property
    def downIcon(self) -> MDItype:
        "The icon to show on the up button"
        return self.__downIcon
    
    @downIcon.setter
    def downIcon(self, value : MDItype):
        if not mdi.is_mdi(value):
            _LOGGER.error(f"Could not set upIcon to {value}")
            return
        self.__downIcon = value

    @property
    def countProperties(self) -> dict:
        "Settings to apply to the counter button. See button element for possible keys. text key is not allowed"
        return self.__countProperties
    
    @countProperties.setter
    def countProperties(self, value : dict):
        value = value.copy()
        if "text" in value:
            _LOGGER.warning("Setting text is not allowed for the counter, removing it from settings")
            value.pop("text")
        self.__countProperties = value

    @property
    def upProperties(self) -> dict:
        "Settings to apply to the up icon. See icon element for possible keys. icon and tap_action keys are not allowed"
        return self.__upProperties
    
    @upProperties.setter
    def upProperties(self, value : dict):
        notallowed = ["icon","tap_action"]
        value = value.copy()
        for k in notallowed:
            if k not in value:
                continue
            _LOGGER.warning(f"Setting {k} is not allowed for the up icon, removing it")
            value.pop(k)
        self.__upProperties = value

    @property
    def downProperties(self) -> dict:
        "Settings to apply to the up icon. See icon element for possible keys. icon and tap_action keys are not allowed"
        return self.__downProperties
    
    @downProperties.setter
    def downProperties(self, value : dict):
        notallowed = ["icon","tap_action"]
        value = value.copy()
        for k in notallowed:
            if k not in value:
                continue
            _LOGGER.warning(f"Setting {k} is not allowed for the down icon, removing it")
            value.pop(k)
        self.__downProperties = value
    #endregion

    def set_counter(self, value : Union[float,int]):
        """
        set the counter value directly. Values are rounded down according to step

        Parameters
        ----------
        value : Union[float,int]
            the new value to set
        """
        loop = self.parentPSSMScreen.mainLoop
        loop.create_task(self._async_set_counter(value))
    
    async def _async_set_counter(self, value : Union[float,int]):
        """
        set the counter value directly. Values are rounded down according to step

        Parameters
        ----------
        value : Union[float,int]
            the new value to set
        """
        i = (value - self.value)/self.step
        i = round(i)
        value = self.value + self.step*i

        if self.minimum != None:
            if value < self.minimum: value = self.minimum
        if self.maximum != None:
            if value > self.maximum: value = self.maximum

        coros = []

        if value != self.value:
            self.value = value
            await self.async_update(updated=True)        
        if self.on_count != None:
            coros.append(tools.wrap_to_coroutine(self.on_count,self,value, **self.on_count_kwargs))

        L = await asyncio.gather(*coros, return_exceptions=True)
        for res in L:
            if isinstance(res,Exception):
                _LOGGER.warning(f"Counter error: {res}")

    async def interact_set_counter(self, value : Union[float,int], *args):
        "Function that can be used to set the value by interacting with other elements."
        
        if not isinstance(value,(int,float)):
            if isinstance(value, base.Element):
                msg = f"{self}: value got passed as an Element: {value}. Make sure you set the appropriate data or map correctly to hold a key defined as value."
            else:
                msg = f"{self}: Value must be an integer or float, not {type(value)}"
            _LOGGER.exception(TypeError(msg))
            return
        await self._async_set_counter(value)

    async def increment(self, *args):
        "Increments the counters value"
        newvalue = self.value + self.step
        self.set_counter(newvalue)

    def decrement(self, *args):
        "Decrements the counter value"
        newvalue = self.value - self.step
        self.set_counter(newvalue)

#endregion

