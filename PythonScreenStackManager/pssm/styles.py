
import logging
from typing import TYPE_CHECKING, Any, Union
import inspect
import sys
from copy import deepcopy
from PIL import ImageFont
from pathlib import Path

from .. import tools
from ..util import classproperty
from ..pssm_types import ColorType, StyleStringDict
from ..constants import PSSM_COLORS, DEBUG, STYLE_SEPERATOR,  STYLE_PARENTCLASS_SEPERATOR,\
        SHORTHAND_FONTS, DEFAULT_FONT

from . import decorators
from .decorators import customproperty, elementaction, trigger_condition
from .util import _get_elt_init_args

if TYPE_CHECKING:
    from ..elements import Element
    from .screen import PSSMScreen

_LOGGER = logging.getLogger(__name__)

SHORTHAND_COLORS = PSSM_COLORS.copy()
SHORTHAND_FONTS = SHORTHAND_FONTS.copy()

_invalidcolor = object()
_nonstyle = object()

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
    default_style = "style"
    base_style_tree : dict[str,dict[str,Any]] = {}
    
    registered_styles = ("style")

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
        return _invalidcolor
    
    @classproperty
    def NONESTYLE(cls):
        """Unique value that can be used to indicate values that are not a style.

        Similar to NOTACOLOR
        """
        return _nonstyle

    @classproperty
    def _knownowners(cls) -> dict[str,"Element"]:
        return styleproperty._element_classes

    @classmethod
    def setup_style_tree(cls, user_tree : dict = {}):
        new_tree = deepcopy(styleproperty._style_tree_root)

        # new_tree["Button"]["font_color"] = "green"
        # new_tree["Layout"]["outline_color"] = "blue"
        # new_tree["Layout"]["outline_width"] = 10

        # new_tree["Tile"]["outline_color"] = "yellow"

        new_tree = tools.update_nested_dict(user_tree, new_tree)

        cls.base_style_tree = new_tree
        return

    @classmethod
    def construct_style_string(cls, base_string : str,
                            style : str = "style", element : Union[str, "Element"] = "Element", property_name : Union["styleproperty",str] = None) -> str:
        """Constructs a 3 part style string from the given base string.

        Parameters
        ----------
        base_string : str
            The base style string to use. Can have up to 3 parts.
        style : str, optional
            The fallback style to use if no valid style part is found in base_string, by default None
            Before falling back to this value, the element's style is used (if element is not a string).
        element : [str, Element] optional
            The fallback Element or Element class name to use if no valid Element class is found in base_string, by default "Element"
        property_name : str, optional
            The fallback property name to use if no known property is found, by default None.
            If no valid property name is found in the string, ValueError is raised is this parameter is None

        Returns
        -------
        str
            The 3 part style string

        Raises
        ------
        AssertionError
            Raised if base_string cannot be used as style string (meaning no "::" is present in it.)
        ValueError
            Raised when an unknown specifier is found in base_string, if base_string consists of more than 3 parts, or if no property name can be applied.
        """

        assert "::" in base_string, "style_string must contain '::'"

        style_tuple = base_string.split("::")
        # d = {}
        d = cls._construct_style_dict(base_string)

        # if style_tuple and len(style_tuple) <= 3:
        #     for val in style_tuple:
        #         if val in Style.registered_styles:
        #             d["style"] = val
        #         elif val in styleproperty._element_classes:
        #             d["owner"] = val
        #         elif val in styleproperty._base_styles:
        #             d["prop"] = val
        #         else:
        #             styleclass, owner = cls._split_style_class(val)
        #             if styleclass in cls.base_style_tree:
        #                 d["owner"] = val
        #             else:
        #                 msg = f"Unknown style specifier {val}"
        #                 raise ValueError(msg)
        # else:
        #     raise ValueError("Invalid style tuple length")
        
        if "style" not in d:
            if isinstance(element, Element):
                style = element.style
            d["style"] = style

        if "owner" not in d:
            if isinstance(element, Element):
                # element = element.__class__.__name__
                # parent_classes = 
                s = element.styleOwnerString
                d["owner"] = element.styleOwnerString
            elif element and isinstance(element, str):
                d["owner"] = element
            elif not element:
                d["owner"] = Element.__name__
        
        if "prop" not in d:
            if property_name is None:
                msg = "Cannot construct style string without a property name"
                raise ValueError(msg)
            else:
                if isinstance(property_name, styleproperty):
                    property_name = property_name.name
                d["prop"] = property_name
        
        return "::".join((d["style"],d["owner"],d["prop"]))

    @classmethod
    def _split_style_class(cls, style_class : str) -> tuple[str, str]:
        """Convenience method to split up an element's styleClass string
        If not style_class is set, it simply returns a tuple with two duplicate values
        """
        if STYLE_PARENTCLASS_SEPERATOR in style_class:
            _, owner = style_class.split(STYLE_PARENTCLASS_SEPERATOR, 1)
            return style_class, owner
        else:
            return style_class, style_class


    @classmethod
    def _construct_style_dict(cls, style_string : Union[str, tuple]) -> StyleStringDict:
        #Creates a style_dict. Does not necessarily contain all keys.

        if isinstance(style_string, str):
            style_tuple = style_string.split(STYLE_SEPERATOR)
        else:
            style_tuple = style_string
        
        if not isinstance(style_tuple, (list,tuple)):
            raise TypeError("style_string must be a string, list or tuple of max length 3")
        

        d = {}
        owners = []

        for val in style_tuple:
            if val in Style.registered_styles:
                d["style"] = val
            # elif val in styleproperty._element_classes:
            #     d["owner"] = val
            elif val in styleproperty._base_styles:
                d["prop"] = val
            else:
                # if STYLE_PARENTCLASS_SEPERATOR in val:
                _, owner = cls._split_style_class(val)
                if owner in styleproperty._element_classes:
                    # d["owner"] = val
                    owners.append(val)
                else:
                    msg = f"Unknown style specifier {val}"
                    raise ValueError(msg)
        
        if owners:
            d["owner"] = STYLE_SEPERATOR.join(owners)
        return d
    
    @staticmethod
    def _style_dict_to_string(style_dict : StyleStringDict) -> str:

        style_list = []
        for key in ("style", "owner", "prop"):
            if key in style_dict:
                style_list.append(style_dict[key])
        
        return STYLE_SEPERATOR.join(style_list)

    @classmethod
    def _construct_style_tuple(cls, style_string : str) -> tuple[str,str,str]:

        assert STYLE_SEPERATOR in style_string, "style_string does not contain the seperator"
        style_tuple = style_string.split(STYLE_SEPERATOR)

        if len(style_tuple) not in (1,2,3):
            msg = "A style string must return at most 3 parts"
            # raise ValueError(msg)
        return style_tuple

    @classmethod
    def get_value(cls, style_value : str, element: "Element" = None, property_name : Union[str,"styleproperty"] = None):
        
        if not cls.base_style_tree:
            cls.setup_style_tree()

        if not (isinstance(style_value, str) or cls.is_style_string(style_value)):
            return style_value

        bases = ()
        style_tuple = cls._construct_style_tuple(style_value)
        style_length = len(style_tuple)
        if style_length > 3:
            pass
            # raise ValueError("A style string can be made up of 3 components at most")
        elif style_length < 3:
            style_tuple = cls._construct_style_tuple(
                cls.construct_style_string(style_value, element = element, property_name=property_name))

        # (style, owner, prop) = style_tuple
        style, prop = style_tuple[0], style_tuple[-1]
        
        owner = style_tuple[1:-1]  ##Again, idk what parts this includes exactly

        ##Will change the setup here:
        ##styletuple can be larger than 3, BUT 0 and -1 are style and prop still.
        # if STYLE_PARENTCLASS_SEPERATOR in owner:
        if len(owner) > 1:
            # owners = owner.split(STYLE_PARENTCLASS_SEPERATOR)
            owners = owner
            # owner_name = owners[-1]

            ##Don't forget to check if this includes or excludes the last one
            cur_tree = cls.base_style_tree
            traversed_trees = []
            for i, parent_owner_string in enumerate(owners[:-1]):
                styleclass, parent_owner = cls._split_style_class(parent_owner_string)
                # if STYLE_PARENTCLASS_SEPERATOR in parent_owner_string:
                #     styleclass, parent_owner = parent_owner_string.split(STYLE_PARENTCLASS_SEPERATOR)
                # else:
                #     styleclass, parent_owner = parent_owner_string, parent_owner_string

                if parent_owner not in cls._knownowners:
                    raise KeyError(f"Unknown element class {parent_owner} in style string {style_value}")
                
                if styleclass in cur_tree and styleclass != parent_owner:
                    ##Honestly in here, need to have all things seperated already I think?
                    ##Or at least be able to track the previous one, so its possible to take a step back to the class.

                    ##Because: styleclass may not contain it but yada yada
                    stylecls_tree = cur_tree[styleclass]
                    owner_tree = cur_tree.get(parent_owner,{})
                    # cur_tree = owner_tree | stylecls_tree
                    cur_tree = tools.update_nested_dict(stylecls_tree, owner_tree)
                    _LOGGER.debug(f"Combined trees for {styleclass} and {parent_owner}")                    
                elif parent_owner in cur_tree:
                    cur_tree = cur_tree[parent_owner]
                else:
                    ##check for base tree? Or simply break here regardless.
                    ##Also, to make it easier to reference styles from other things: simply use style::Parent::Owner AS THE STYLE VALUE
                    _LOGGER.debug(f"Unable to fully traverse style tree for owners {owner}")
                    cur_tree = cls.base_style_tree
                    break
                
                traversed_trees.append(cur_tree)
                    
            # owner = owners[-1]
            style_class, owner = cls._split_style_class(owners[-1])
            if owner not in cur_tree:   ##Do the fallback in here probably?
                _LOGGER.warning(f"No child style for {owner} found after traversing owners {owners}, reverting to base tree")
                cur_tree = cls.base_style_tree
            elif not (prop in cur_tree[style_class] or prop in cur_tree[owner]):
                ##This does mean the property is checked twice if it is in there, but it is probably the best way to do so.
                cur_tree = cls.base_style_tree
            else:
                _LOGGER.debug(f"Fully traversed style tree for {owners}")

        else:
            style_class, owner = cls._split_style_class(owner[0])
            cur_tree = cls.base_style_tree

        # if owner in cls._knownowners:
        #     cur_tree = cls.base_style_tree
        # elif STYLE_PARENTCLASS_SEPERATOR in owner:
        #     ##Would this work? How to handle styleclass being default but then reverting to owner by default?
        #     ##Or in the other case set both variables to owner?
        #     styleclass, owner = owner.split(STYLE_PARENTCLASS_SEPERATOR)
        # else:
        #     styleclass, owner = owner, owner
            # raise KeyError(f"Unknown element class {owner} in style string {style_value}") 

        # if prop in cls.base_style_tree.get(owner,{}):
        if prop in cur_tree.get(style_class,{}):
            # val = cls.base_style_tree[owner][prop]
            val = cur_tree[style_class][prop]
        elif prop in cur_tree.get(owner,{}):
            val = cur_tree[owner][prop]
        else:
            bases = inspect.getmro(styleproperty._element_classes[owner])

            for base in bases[1:]:
                if prop in (d := cls.base_style_tree.get(base.__name__,{})):
                    val = d[prop]
                    # return val
                    break
                if base == Element:
                    val = styleproperty._base_styles[prop]
                    break
        
        if cls.is_style_string(val):
            ##handle this: go one step lower and pass those to construct?
            ##main issue: how to determine what to use from val
            s = cls.construct_style_string(val, element=element, property_name=property_name)
            d = cls._construct_style_dict(s)

            d.setdefault("style", "style")
            if "prop" not in d and property_name:
                if isinstance(property_name, styleproperty):
                    prop = property_name.name
                else:
                    prop = property_name
                d.setdefault("prop",prop)
            
            if "owner" not in d:
                new_owner = Element.__name__
                try:
                    if not bases:
                        bases = inspect.getmro(styleproperty._element_classes[owner])
                    for base in bases[1:]:
                        if issubclass(base, Element):
                            new_owner = base.__name__
                            break
                except (IndexError, KeyError):
                    pass
                d["owner"] =  new_owner

            new_string = cls._style_dict_to_string(d)
            v = cls.get_value(new_string)
            return v
        return val

    @classmethod
    def get_color(cls, value: ColorType, colormode: str = "screen-image"):
        if colormode == "screen-image":
            colormode = cls.screen.imgMode
        elif colormode == "screen":
            colormode = cls.screen.colorMode
        
        if isinstance(value,str) and (value.lower() in cls.shorthand_colors or "::" in value):
            if value.lower() in cls.shorthand_colors:
                return cls.shorthand_colors[value.lower()]
            elif "::" in value:
                return cls.get_value(value)

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

    @staticmethod
    def is_style_string(style_string):

        return isinstance(style_string, str) and STYLE_SEPERATOR in style_string

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
        
        if isinstance(value, str) and "::" in value:
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

    @classmethod
    def load_font(cls, font : str, font_size : float, fallback_to_default : bool = True) -> ImageFont.FreeTypeFont:
        """Loads the given font in the requested size

        Handles shorthand fonts as well

        Parameters
        ----------
        font : str
            The path to the font to load, or a shorthand identifier for it
        font_size : float
            The size of the font
        fallback_to_default : bool, optional
            If True, the function will return the default font if it is unable to load the provided font file. Otherwise, OSError is raised, by default True

        Returns
        -------
        ImageFont.FreeTypeFont
            The font object
        """

        if font in SHORTHAND_FONTS:
            font = SHORTHAND_FONTS[font]
        try:
            return ImageFont.truetype(font, font_size)
        except OSError:
            font_file = Path(font)
            if not font_file.exists():
                _LOGGER.warning(f"font file {font} does not exist.")
            else:
                _LOGGER.error(f"unable to open font file {font}")
            
            if fallback_to_default:
                return ImageFont.truetype(SHORTHAND_FONTS["default"], font_size)
            else:
                raise

class styleproperty(customproperty):
    """Decorator that can be used to indicate a property is a style property. 
    
    If the property sets a color, use the ``@colorproperty`` decorator instead, as it is a subclass.
    styleproperties and their default values are aggregated to automatically create a styletree of each element. This allows users to create coherent themes.
    When the __init__ function of an element is called, all styleproperties that are not present in the keyword arguments are set to a stylestring.
    
    For the setter, it also catches the property being set to a style string.
    For style strings it constructs to the appropriate 3 part style string (``style::ElementClass::property``). It then determines the value corresponding to said style and passes that to the setter.
    The setter can raise ``AssertionError``, ``AttributeError``, ``TypeError`` or ``ValueError`` and the property takes care of logging. If no error is raised, the appropriate attribute (``_[property``]) on the element is set to the style string.
    So, unless ``vsetraw==True``, the setter can be best thought of as validator for the style value. Error logging is also handled by the decorator.
    If ``vsetraw==True``, the above is not the case. 

    Usage
    ------
    ```
    class ExampleElement(Element):
        ...

        @styleproperty
        def styled_height(self):
            return self._styled_height

        @styled_height
        def styled_height(self, value):
            if not tools.is_valid_dimension(value):
                raise ValueError(f"{value} is not a valid dimension")
    ```
                    
    After the class is fully defined, the property checks if a corresponding argument is present in the class' ``__init__`` function. If so, it saves said value and automatically sets it as the ``default`` attribute for the property.
    In child classes, the same logic is applied. Any styleproperties present in their parent and their __init__ will lead to a new entry with default value in the styletree for that element class.
    If something is, for example, a base class with no __init__ function, or if a different default value is desired from the one present in the __init__, the property can be applied as follows:

    ```
    @styleproperty(vdefault = 10).getter
    def styled_height(self):
        return self._styled_height
    ```
        
    This sets the default value to 10. If ``styled_height`` appears in the __init__ function *of the same class*, the value is not overwritten. For child classes, it will be treated as an updated value.

    
    When for example generating the element, the most convenient way to get the value of the property is using the ``value`` function via the element class.
    This function calls ``Style.get_value`` with all the arguments set appropriately for the element instance.

    ```
    def generator(self, ...):
        
        height = ExampleElement.styled_height.value(self)
    ```
    """   

    _found_properties = set()

    _element_classes : dict[str,type["Element"]] = {}   ##Maps strings to appropriate class
    _all_owners : set["Element"] = set()    ##All elements with styleproperties defined
    _base_element_class: "Element"
    
    _style_tree_root = {}
    _base_styles = {}

    _parentproperty : "styleproperty"

    @property
    def get_func(self):
        raise AttributeError
        return getattr(self, "_fget", self.fget)
    
    @property
    def _style_attribute(self) -> str:
        ##Returns the (presumably) correct name of the connected attribute
        if hasattr(self, "_style_name"):
            return self._style_name
        return self._parentproperty._style_attribute
    
    @property
    def name(self) -> str:
        return self.property_name

    @property
    def property_name(self) -> str:
        "Name of the connected property"
        return self._style_name

    @property
    def stylestring(self) -> str:
        "base style string for this style. Usually style::[property]"
        return f"style::{self._style_attribute}"
    
    @property
    def default(self) -> Any:
        """The value of this property as defined in the __init__ function
        Definition may come from earlier parent classes.
        """
        if self.vdefault is Style.NONESTYLE:
            raise AttributeError(f"{self} has no default value set")
        return self.vdefault

    def __init__(self,
                fget=None, 
                fset=None, 
                fdel=None, 
                doc=None,
                *,
                vdefault=Style.NONESTYLE,
                vsetraw=False,
                ):
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
        vdefault
            The default value to use for the style. This means the value in the __init__ is not set for the owner class. It will be for child classes.
        vsetraw
            Have the setter function handle setting, not just validating.
            This means the setter can be passed raw style strings as well.
        """
        super().__init__(fget,fset,fdel,doc)
        self.vdefault = vdefault
        self.vsetraw = vsetraw
        return

    # def __call__(self, element):
    #     ##Currently leaving __call__ commented out
    #     ##I think it it obfuscates what it does, and typing .value does not require much more space.
    #     return self.value(element)

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        self._style_name = name

        owner_elt = owner.__name__
        cls = self.__class__
        self.owner = owner

        ##Do not use __elt_init__ here, __set_name__ is called before __init_subclass__ (so before __init__ is overwritten)
        init_func = owner.__init__
        base_args = inspect.signature(init_func)
        
        default_val = Style.NONESTYLE
        for param in base_args.parameters.values():
            if param.name == name:
                default_val = param.default
                break

        if default_val is Style.NONESTYLE:
            if name not in cls._base_styles:
                cls._base_styles[name] = default_val
            return

        if getattr(self, "vdefault", Style.NONESTYLE) is Style.NONESTYLE:
            self.vdefault = default_val

        if owner_elt in cls._style_tree_root:
            cls._style_tree_root[owner_elt][name] = self.vdefault
        else:
            cls._style_tree_root[owner_elt] = {name: self.vdefault}
            cls._element_classes[owner_elt] = owner

        if cls._base_styles.get(name, Style.NONESTYLE) is Style.NONESTYLE:
            cls._base_styles[name] = self.vdefault
        
        cls._all_owners.add(owner_elt)
        return

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")

        val = self.fget(obj)
        if isinstance(val, str) and val.lower() == "none":
            val = None

        return val

        if obj.__class__.__name__ in self._all_owners:
            return val
        if isinstance(val,str) and "::" in val:
            style_val = Style.get_value(val, obj)
            return style_val
        return val

    def __set__(self, obj, value):

        if self.fset is None:
            raise AttributeError("can't set attribute")

        if self.vsetraw:
            self.fset(obj, value)
        else:
            try:
                if Style.is_style_string(value):
                    style_string = self.create_style_string(obj, value)
                    style_value = Style.get_value(style_string, obj, self.property_name)
                    self.fset(obj, style_value)
                    setattr(obj,f"_{self._style_attribute}", style_string)
                else:
                    if isinstance(value, str) and value.lower() == 'none':
                        value = None
                    self.fset(obj, value)
                    setattr(obj,f"_{self.property_name}", value)
                return
            except (ValueError, TypeError, AttributeError, AssertionError) as exce:
                msg = f"{obj}: can't set property {self._style_attribute} to style {style_string}, {exce}"
                _LOGGER.error(msg, exc_info=DEBUG)
                raise
        
        return self.fset(obj,value)

    def value(self, element : "Element"):
        """Returns the value of this property for the given element

        Conversion of style strings is handled in this function.
        """
        if not isinstance(getattr(element.__class__, self.property_name, None), styleproperty):
            return getattr(element, self.property_name)
        val = element.get_style_value(getattr(element, f"_{self.property_name}"), self.property_name)
        if isinstance(val, dict):
            return val.copy()
        return val

    def configure(self, *, default = Style.NONESTYLE):
        if default is not Style.NONESTYLE:
            self.vdefault = default
        return self

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__, vdefault=self.vdefault, vsetraw=self.vsetraw)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__, vdefault=self.vdefault, vsetraw=self.vsetraw)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__, vdefault=self.vdefault, vsetraw=self.vsetraw)

    def create_style_string(self, obj : "Element", string : str):

        return Style.construct_style_string(string, element = obj, property_name = self._style_attribute)

    @classmethod
    def _set_element_styles(cls, owner : type["Element"]):
        ##Register style properties present in __init__ but registered from a baseclass
        owner_elt = owner.__name__

        cls._style_tree_root.setdefault(owner_elt,{})
        cls._element_classes.setdefault(owner_elt,owner)

        ##Do not use __elt_init__, this function is called before it is set
        init_func = owner.__init__
        base_args = inspect.signature(init_func)
        
        init_styles = {}
        for i, param in  enumerate(base_args.parameters.values()):
            if (param.default is not param.empty
                and isinstance(getattr(owner, param.name, None), styleproperty)
                and param.name not in cls._style_tree_root[owner_elt]):

                cls._style_tree_root[owner_elt][param.name] = param.default

            if param.name in cls._style_tree_root[owner_elt]:
                init_styles[param.name] = (i, cls._style_tree_root[owner_elt][param.name])

        return init_styles

    @classmethod
    def style_init_args(cls, element_cls):
        "Returns all the registered element styles with default values"
        if element_cls.__name__ in cls._style_tree_root:
            return cls._style_tree_root[element_cls.__name__]
        return {}
    
    @classmethod
    def style_classes(cls, style_tree : dict):
        """Add a style tree for specific styleclasses of this element

        Parameters
        ----------
        style_tree : dict[Union[type[&quot;Element&quot;],str],dict]
            The style tree to add. The element class is added automatically.

        Example
        ---------
        ```
        class Tile:
            ....

            styleClasses = styleproperty.style_classes({"Horizontal": {"background_color": "green"})
        ```
        This example will have the background color for a Tile with style_class "Horizontal" be styled to green.
        """
        return _styleclasses(style_tree)

    @classmethod
    def child_styles(cls, style_tree : dict[Union[type["Element"],str],dict]):
        """Add a style tree for elements with this element type as styleParent

        Parameters
        ----------
        style_tree : dict[Union[type[&quot;Element&quot;],str],dict]
            The style tree to add. If a key is not an element class, the value dict should contain the key "Class", with a tuple of applicable classes.

        ```
        class Tile:
            ....

            childStyles = styleproperty.style_classes(
                    Button : {"font_color": "green"},
                    "Title": {
                            "Class": (Button,),
                            "font": DEFAULT_FONT_HEADER}
                                }))
        ```
        This will add the child style classes "Button" and "Title.Button". For the latter, the "Class" key is removed from the dict.
        """
        
        ##What to return here? Probably a new property, may a subclass of this one.
        ##Mainly required when __set_name__ is being called.
        ##But also: not a property though?
        ##Idk just experiment and see what happens with this tbh
        ##Decorator can be used but must be a function then?
        ##So idk, can do so, and simply require a function to return a dict. I believe that should work at least
        ##Other options would require setting an attribute anyways, so this should work too I think.

        ##See python docs on descriptor. It says __set_name__ is always called?
        ##check that, idk.
        ##But can do it. It does not necessarily need a function, but does perhaps need a classvariable for itself.
        return _childstyles(style_tree)
    
class _childstyles(styleproperty):

    def __init__(self, child_tree : dict):

        self._child_tree = self._process_dict(child_tree)
        return
    
    @classmethod
    def _process_dict(cls, d_proc : dict):
        #Process a style_tree dict recursively, applying keys from Class etc. automatically

        d = {}
        for k, v in d_proc.items():
            if inspect.isclass(k) and issubclass(k, styleproperty._base_element_class):
                k_new = k.__name__
                if isinstance(v, dict):
                    d[k_new] = cls._process_dict(v)
                else:
                    d[k_new] = v
            elif isinstance(k, str):
                if not isinstance(v, dict):
                    v_new = v
                    d[k] = v
                elif "Class" in v:
                    v_new : dict = v.copy()
                    v_classes = v_new.pop("Class")
                    assert isinstance(v_classes,(list,tuple)), "Class key must be a list or tuple"
                    for k_class in v_classes:
                        if type(k_class) is str:
                            key = f"{k}{STYLE_PARENTCLASS_SEPERATOR}{k_class}"
                        else:
                            assert issubclass(k_class,styleproperty._base_element_class), "Items in 'Class' must be a subclass of element"
                            key = f"{k}{STYLE_PARENTCLASS_SEPERATOR}{k_class.__name__}"
                        d[key] = cls._process_dict(v_new)
                else:
                    d[k] = cls._process_dict(v)
            else:
                raise TypeError("Child tree keys must be a string or element class")
        return d

    def getter(self, fget):
        return type(self)(fget)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._child_tree
    
    def __set_name__(self, owner, name):
        owner_elt = owner.__name__

        if owner_elt not in styleproperty._style_tree_root:
            styleproperty._style_tree_root[owner_elt] = {}

        owner_tree = styleproperty._style_tree_root[owner_elt]
        for child_owner, style_tree in self._child_tree.items():
            owner_tree[child_owner] = style_tree

        return
        # return super().__set_name__(owner, name)
    
    def _validate_tree(self):
        ##Validate if classes are valid?
        ##Eh honestly. Consenting adults and whatnot.

        ##Do I guess test if everything is a style property, but I guess that should also happen for most things. idk.
        return

class _styleclasses(_childstyles):

    def __init__(self, style_tree : dict):
        
        d = {}
        for k, v in style_tree.items():
            d[k] = self._process_dict(v)

        self._class_tree = d

    def __set_name__(self, owner, name):
        d = {}
        owner_elt = owner.__name__

        for k,v in self._class_tree.items():
            k_new = f"{k}{STYLE_PARENTCLASS_SEPERATOR}{owner_elt}"
            d[k_new] = v
            styleproperty._style_tree_root[k_new] = v

        self._class_tree = d
    
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._class_tree


class colorproperty(styleproperty):
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

    @property
    def property_name(self) -> str:
        "Name of the connected property"
        return self._style_name

    def __init__(self,
                fget=None, 
                fset=None, 
                fdel=None, 
                doc=None,
                *,
                vdefault = Style.NONESTYLE,
                vallowsnone = True,
                fset_post = None,
                ):
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

        if fset is None:
            fset = self._color_setter
        super().__init__(fget, fset, fdel, doc, vdefault=vdefault)
        self._allows_none = vallowsnone
        self._fset_post = fset_post
        return

    # class NOT_NONE(customproperty):
    #     "Decorator to mark any color properties that do not accept a None value for their color."
    #     def __new__(cls, fget=None, fset=None, fdel=None, doc=None) -> "colorproperty":
    #         raise DeprecationWarning("subclass is deprecated, use allows_none at init")
    #         obj = colorproperty(fget, fset,fdel, doc, allows_none=False)
    #         return obj

    def __get__(self, obj: "Element", objtype=None) -> Any:
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)
        # return self._get_element_color(obj)

    def __set__(self, obj, value):
        v = super().__set__(obj, value)
        if self._fset_post:
            self._fset_post(obj, value)
        return v

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        self._color_attribute = name
        self.__add_class_color(owner, name)
        super().__set_name__(owner, name)
        return

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

        attribute = self._style_name
        set_attribute = "_" + attribute
        allows_None = self._allows_none

        if value == "None": #YAML parses null or nothing to None, however for colors, having a value that is representative of the color value is important I think.
            value = None

        if hasattr(element, set_attribute) and value == getattr(element, set_attribute):
            ##Do nothing if the color does not change
            return

        msg = None
        if Style.is_valid_color(value):
            if value is None and (not allows_None):
                msg = f"{element}: {attribute} does not allow {value} as a color value"
            else:
                setattr(element, set_attribute, value)
        elif isinstance(value,str):
            if element.parentLayout is None and element not in element.screen.stack:
                ##Means it will be validated later
                setattr(element, set_attribute, value)
            elif value in getattr(element.parentLayout,"_color_shorthands",{}):
                setattr(element, set_attribute, value)
            else:
                msg = f"{element}: {value} is not identified as a valid color nor a valid shorthand for its parent ({self.parentLayout}) colors"
        else:
            msg = f"{element}: {value} is not identified as a valid color"

        if msg:
            # _LOGGER.error(msg, exc_info=ValueError(msg))
            raise ValueError(msg)
        elif hasattr(element, "_style_update"):
            element._style_update(attribute, value)
        
    def _get_element_color(self, element: "Element", colormode : str = None):
        val = self.__get__(element)
        val = element.get_color_value(val, colormode, property_name=self._style_attribute)
        # if Style.is_style_string(val):
        #     val = Style.get_value(val, element, self._style_attribute)
        #     # return val
        # if isinstance(val, str) and element.parentLayout is not None:
        #     if val in getattr(element.parentLayout,"_color_shorthands",{}):
        #         prop = element.parentLayout._color_shorthands[val]
        #         val = getattr(element.parentLayout, prop)
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

    def value(self, element : "Element") -> Any:
        """Returns the value of this color as it is defined in the style tree

        So values referencing parent colors (e.g. ``'active'``), or shorthand colors are returned from here.
        It does (should) not return any style strings.

        Use this for i.e. comparisons of the raw value. Use get_color if you simply need a color to put into a PIL function.

        Parameters
        ----------
        element : Element
            The element to get the property from

        Returns
        -------
        The value as set, with stylestrings processed if applicable
        """

        # val = self._get_element_color(element)

        ##Want to use value method to get the raw value (i.e. include values from parents, but have styles converted):
        # - add a method to Element for get_color, which handles everything starting from a color value (but does attempt to convert style strings).
        # - add as method to Style, with the element having to be passed to it
        # First one has my preference

        val = self.fget(element)
        if Style.is_style_string(val):
            return element.get_style_value(getattr(element, f"_{self.property_name}"), self.property_name)
        return val

    def get_color(self, element : "Element", colormode : str = "screen-image"):
        """Return a PIL appropriate color value for this attribute
        """
        return self._get_element_color(element, colormode)
        # val = self._get_element_color(element, colormode)
        # return Style.get_color(val, colormode)

    def configure(self, *, default=Style.NONESTYLE, allows_none : bool = Style.NONESTYLE):
        if allows_none is not Style.NONESTYLE:
            self._allows_none = allows_none
        return super().configure(default=default)

    def getter(self, fget : Any):
        fset = None if self.fset == self._color_setter else self.fset
        return type(self)(fget, fset, self.fdel, self.__doc__, 
                        vdefault=self.vdefault, vallowsnone=self._allows_none, fset_post=self._fset_post)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__, 
                        vdefault=self.vdefault, vallowsnone=self._allows_none, fset_post=self._fset_post)

    def post_setter(self, fset_post):
        fset = None if self.fset == self._color_setter else self.fset
        return type(self)(self.fget, fset, self.fdel, self.__doc__, 
                        vdefault=self.vdefault, vallowsnone=self._allows_none, fset_post=fset_post)

    def deleter(self, fdel):
        fset = None if self.fset == self._color_setter else self.fset
        return type(self)(self.fget, fset, fdel, self.__doc__,
                        vdefault=self.vdefault, vallowsnone=self._allows_none, fset_post=self._fset_post)


decorators.colorproperty = colorproperty
decorators.styleproperty = styleproperty