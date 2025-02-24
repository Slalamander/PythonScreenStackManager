
import logging
from typing import TYPE_CHECKING

from .. import tools
from ..util import classproperty
from ..pssm_types import ColorType
from ..constants import PSSM_COLORS

from . import decorators
from .decorators import customproperty, elementaction, trigger_condition

if TYPE_CHECKING:
    from ..elements import Element
    from .screen import PSSMScreen

_LOGGER = logging.getLogger(__name__)

SHORTHAND_COLORS = PSSM_COLORS.copy()

__invalidcolor = object()

##linking to a style: any string starting and ending with a ':' (think about using that one, yaml does start complaining about nested mappings with it unless explicitly setting it to a string)
##i.e. ':style:' would apply the default style value said property
##Maybe also allow style identifiers like ':success:' etc like ttkbootstrap does
## ':style:[ELEMENTCLASS]:[STYLEPROPERTY]' and use mro's to cascade down
##Could even intercept the default values from the __init__'s to automatically create the defaults?
##Maybe; also give elements a styleDefaults property e.g. that can be used to set up the defaults.
##Also add an export function to create style.json/style.yaml

class Style:
    """Handles styling and theming of Elements
    _summary_

    Returns
    -------
    _type_
        _description_
    """

    screen: "PSSMScreen"
    _color_shorthands: dict[str,ColorType] = {}

    @classproperty
    def shorthand_colors(cls):
        return SHORTHAND_COLORS | cls._color_shorthands
    
    @classproperty
    def NOTACOLOR(cls):
        """Unique value that can be used to test colors without relying on booleans
        

        Example
        ---------

        .. code-block::

            is_valid_color(colors.get("my_color",NOTACOLOR))
            
        Will always return ``False``, whereas for example ``None`` is a valid color value.
        """
        return __invalidcolor

    @classmethod
    def get_color(cls, value: ColorType, colormode: str = "screen-image"):
        if colormode == "screen-image":
            colormode = cls.screen.imgMode
        elif colormode == "screen":
            colormode = cls.screen.colorMode
        
        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            return cls.shorthand_colors[value.lower()]
        else:
            try:
                return tools.get_Color(value,colormode)
            except (ValueError,TypeError):
                return "black"
            
    @classmethod
    def contrast_color(cls, value, mode):
        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            value = cls.shorthand_colors[value.lower()]
        
        return tools.contrast_color(value, mode)
            
    @classmethod
    def is_valid_color(cls, value: ColorType, element : "Element" = None) -> bool:
        """Returns whether the provided value is a valid value for a color property

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
        if element and isinstance(value,str):
            if element.parentLayout is None and element not in element.screen.stack:
                return True
            elif value in getattr(element.parentLayout,"_color_shorthands",{}):
                return True

        if isinstance(value,str) and value.lower() in cls.shorthand_colors:
            return True
        else:
            return tools.is_valid_Color(value)
        return

    @classmethod
    def add_color_shorthand(cls, **kwargs: ColorType):
        shorthands = cls.shorthand_colors
        for col_name, color in kwargs.items():
            if col_name in shorthands:
                _LOGGER.error(f"{col_name} is already registered as a shorthand color")
                continue
            if not tools.is_valid_Color(color):
                _LOGGER.error(f"color {color} with shorthand {col_name} is not a valid color value")
                continue
            cls._color_shorthands[col_name] = color
    ##Setting up a color property:
    ##pass as style (identifier)-color-subclass-class

class styleproperty(customproperty):
    """Decorator that can be used to indicate a property is a style property. It also automatically applied the logic to allow using color shorthands to reference colors from parents.

    Does not provide functionality to automatically add a setter, but is used to aggregate all color properties such that they can be easily gotten by calling a classes color_properties

    Usage
    ------
    .. code-block: python

        @styleproperty
        def element_action(self):
            "performs an action for the element'
            return self._myColor

    Most important is to use the decorator after the `@property` decorator.
    Also, it is best to make any colorProperty return a private variable, i.e. use a single `_` and append the name of the property. Using double `__` causes problems when parsing parent colors.
    """   

    _found_properties = set()

    __element_classes : dict[type[object],set] = {}
    _base_element_class: "Element"
    
    __base_style_tree = {}
    
    def __init__(self,
                fget=None, 
                fset=None, 
                fdel=None, 
                doc=None,
                allows_none = True):
        """Attributes of 'our_decorator'
        fget
            function to be used for getting 
            an attribute value
        fset
            function to be used for setting 
            an attribute value
        fdel
            function to be used for deleting 
            an attribute
        doc
            the docstring
        """

        super().__init__(fget,fset,fdel,doc)
        return

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        self._style_attribute = name
        owner_elt = owner.__name__
        cls = self.__class__
        val = 1
        ##Extracting the values:
        ##Call the defaultdict from the docs if owner is not yet known
        ##safe that and use it to get the value
        if owner_elt in cls.__base_style_tree:
            cls.__base_style_tree[owner_elt][name] = val
        else:
            cls.__base_style_tree[owner_elt] = {name: val}

        


class colorproperty(customproperty):
    """Decorator to indicate a property is defines the color of an element.
    
    This means it can automatically apply the default color_setter as the properties setter, and implements the logic parse the color values of parents when shorthands are used.
    Requires the fget function to return the private variable of the properties name. 
    6
    Usage
    ------
    .. code-block:: python

        @colorproperty
        def my_color(self):
            return self._my_color
    """   

    _found_properties = set()

    __element_classes : dict[type[object],set] = {}
    _base_element_class: "Element"    
    
    def __init__(self,
                fget=None, 
                fset=None, 
                fdel=None, 
                doc=None,
                allows_none = True):
        """Attributes of 'our_decorator'
        fget
            function to be used for getting 
            an attribute value
        fset
            function to be used for setting 
            an attribute value
        fdel
            function to be used for deleting 
            an attribute
        doc
            the docstring
        """

        if fset == None:
            fset = self._color_setter
        self._allows_none = allows_none
        super().__init__(fget,fset,fdel,doc)
        return

    class NOT_NONE(customproperty):
        "Decorator to mark any color properties that do not accept a None value for their color."
        def __new__(cls, fget=None, fset=None, fdel=None, doc=None) -> "colorproperty":
            obj = colorproperty(fget, fset,fdel, doc, allows_none=False)
            return obj

    def __get__(self, obj: "Element", objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")

        return self._get_element_color(obj)

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        self._color_attribute = name
        self.__add_class_color(owner, name)

    def _color_setter(self, element:"Element", value : ColorType, cls : type = None):
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
        """

        attribute = self._color_attribute
        set_attribute = "_" + attribute
        allows_None = self._allows_none

        if value == "None": #YAML parses null or nothing to None, however for colors, having a value that is representative of the color value is important I think.
            value = None

        if hasattr(element, set_attribute) and value == getattr(element, set_attribute):
            ##Do nothing if the color does not change
            return

        msg = None
        if Style.is_valid_color(value):
            if value == None and (not allows_None):
                msg = f"{element}: {attribute} does not allow {value} as a color value"
            else:
                setattr(element, set_attribute, value)
        elif isinstance(value,str):
            if element.parentLayout == None and not element in element.screen.stack:
                ##Means it will be validated later
                setattr(element, set_attribute, value)
            elif value in getattr(element.parentLayout,"_color_shorthands",{}):
                setattr(element, set_attribute, value)
            else:
                msg = f"{element}: {value} is not identified as a valid color nor a valid shorthand for its parent ({self.parentLayout}) colors"
        else:
            msg = f"{element}: {value} is not identified as a valid color"

        if msg:
            _LOGGER.error(msg,exc_info=ValueError(msg))
        elif hasattr(element, "_style_update"):
            element._style_update(attribute, value)

    def _get_element_color(self, element: "Element"):
        val = self.fget(element)
        if isinstance(val, str) and element.parentLayout != None:
            if val in getattr(element.parentLayout,"_color_shorthands",{}):
                prop = element.parentLayout._color_shorthands[val]
                val = getattr(element.parentLayout, prop)
        return val

    @classmethod
    def __add_class_color(cls, elt_cls : type["Element"], property_name : str):
        if elt_cls in cls.__element_classes:
            cls.__element_classes[elt_cls].add(property_name)
        else:
            cls.__element_classes[elt_cls] = set([property_name])
        cls._found_properties.add(property_name)

    @classmethod
    def _get_class_colors(cls, elt_cls):
        if elt_cls not in cls.__element_classes:
            cols = set()
        else:
            cols = cls.__element_classes[elt_cls].copy()

        for base in elt_cls.__bases__:
            if not issubclass(base,cls._base_element_class):
                continue

            base_cols = cls._get_class_colors(base)
            cols.update(base_cols)
        return cols



decorators.colorproperty = colorproperty
decorators.styleproperty = styleproperty