
import logging
from typing import TYPE_CHECKING
from types import MappingProxyType
import inspect

from functools import wraps

from ..pssm_types import *
from ..exceptions import *
from ..tools import customproperty

if TYPE_CHECKING:
    from ..elements import Element
    from .styles import Style

def parse_known_image_file(file):
    pass

_LOGGER = logging.getLogger(__name__)

class colorproperty(customproperty):
    """Decorator to indicate a property is defines the color of an element.
    
    This means it can automatically apply the default color_setter as the properties setter, and implements the logic parse the color values of parents when shorthands are used.
    Requires the fget function to return the private variable of the properties name. 
    
    Usage
    ------
    ```
    @colorproperty
    def my_color(self):
        return self._my_color
    ```
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

    def __call__(self, element : "Element") -> Any:
        
        val = self.fget(element)

        if isinstance(val, str) and element.parentLayout != None:
            if val in getattr(element.parentLayout,"_color_shorthands",{}):
                prop = element.parentLayout._color_shorthands[val]
                val = getattr(element.parentLayout, prop)

        return val 

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
            if element.parentLayout == None and not self in element.screen.stack:
                ##Means it will be validated later
                setattr(element,set_attribute, value)
            elif value in getattr(element.parentLayout,"_color_shorthands",{}):
                setattr(self,set_attribute, value)
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


class styleproperty(Generic[T]):
    """
    Decorator that can be used to indicate a property is a style property. It also automatically applied the logic to allow using color shorthands to reference colors from parents.
    Does not provide functionality to automatically add a setter, but is used to aggregate all color properties such that they can be easily gotten by calling a classes color_properties

    Usage
    ------
    ```
    @property
    @e
    def element_action(self):
        "performs an action for the element'
        return self._myColor
    ```

    Most important is to use the decorator after the `@property` decorator.
    Also, it is best to make any colorProperty return a private variable, i.e. use a single `_` and append the name of the property. Using double `__` causes problems when parsing parent colors.
    """    


class elementaction(customproperty):
    """Decorator to quickly setup actions for an element.

    Provides some convenience, as applying this decorator instead of a property immediately applies the following:
        - specific setter for functions that hooks into the screen's shorthand action parser for strings, but is also able to set it to one of the element's own shorthand actions. It also provides functionality to accept a callable, a string or a dict which combines them all to set them.
        - Sets up the appropriate {action}_data property for the class
        - Sets up the appropriate {action}_map property for the class
        - Sets up the appropriate {action}_kwargs property for the class, which combines the data and map property to construct keyword arguments to pass to the function.

    Usage
    ------
    ```python

    @elementaction
    def my_element_action(self) -> Callable
        "An example action for the decorator"
        return self._my_element_action
    ```

    Just be mindful that the returned variable has to be the private variation of the property name.
    """



    def __init__(self, 
                fget=None, 
                fset=None, 
                fdel=None, 
                doc=None):
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
            fset = self._function_setter
        super().__init__(fget,fset,fdel,doc)

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        self._action_attribute = name

        add_props = ["data", "map", "kwargs"]
        for prop in add_props:
            if not hasattr(owner, f"{self._action_attribute}_{prop}"):
                prop_obj = property(getattr(self, f"_{prop}_fget"), getattr(self, f"_{prop}_fset", None))
                setattr(owner, f"{self._action_attribute}_{prop}", prop_obj)

    def _function_setter(self, element: "Element", value:  Union[Callable,str,interact_actionDict,None]):
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
        attribute = self._action_attribute

        if isinstance(value,Callable) or value == None:
            func = value
        elif isinstance(value, str):
            func = element.screen.parse_shorthand_function(value,attribute)
        
        elif not isinstance(value, (dict,MappingProxyType)):
            msg = f"{element} {attribute} is of incorrect type. Must be a callable, string, dict or None. Is {type(value)}"
            _LOGGER.exception(msg)
            func = None
        else:
            value = value.copy()
            if "action" not in value:
                msg = f"{element}: setting a function with a dict requires the key 'action'. {value} is not valid."
                _LOGGER.exception(KeyError(msg))
                func = None
            elif not isinstance(value["action"], (Callable,str)):
                msg = f"{element}: action key must be a function or a string. {type(value)}: {value} is not valid."
                _LOGGER.exception(TypeError(msg))
                func = None
            else:
                func = value["action"]

                if isinstance(func,Callable):
                    pass
                elif "element_id" not in value and func in element.action_shorthands:
                    func = func.removeprefix("element:")
                    func_attr = element.action_shorthands[func]
                    func = getattr(element,func_attr)
                    ##Probably gather all element-shorthands and ensure those cannot be set as shorthand
                else:
                    try:
                        func = element.screen.parse_shorthand_function(value["action"], attribute, value)
                    except (ElementNotRegistered, ShorthandNotFound, ShorthandGroupNotFound) as exce:
                        if element.screen.printing:
                            msg = exce.args[0] +  f" Cannot set {attribute} for {element}"
                            _LOGGER.error(msg, exc_info=True)
                            func = None
                        else:
                            element.parentPSSMScreen._add_element_attribute_check(element,attribute, value.copy())
                            _LOGGER
                            func = None
        
        if not isinstance(func,Callable) and func != None:
            msg = f"{element} {func} is not a function"
            raise TypeError(msg)
            func = None
        
        data_attr = f"{attribute}_data"
        map_attr = f"{attribute}_map"
        kwarg_attr = f"{attribute}_kwargs"

        if not hasattr(element, kwarg_attr):    ##How to set this automatically?
            ##Be mindful that this means the property should return a value
            ##So data_attr and map_attr need to be able to return something before calling _function_checker
            pass
        elif isinstance(value, dict):
            ##These should not be set if the string could not be mapped to a function
            ##So the instance check is done twice, so the str check doesn't need to be rewritten.
            ##If the function is None it doesn't really matter since they won't be passed anyways

            ##Setters for these should be applied by the element

            ##Letting these fail silently is ok, I think?
            if hasattr(element, data_attr):
                if "data" in value and isinstance(value["data"],dict):
                    setattr(element, data_attr, value["data"])
                else:
                    setattr(element, data_attr, {})
            if hasattr(element, map_attr):
                if "map" in value and isinstance(value["map"],dict):
                    setattr(element, map_attr, value["map"])
                else:
                    setattr(element, map_attr, {})
        else:
            if hasattr(element, data_attr): setattr(element, data_attr, {})
            if hasattr(element, map_attr): setattr(element, map_attr, {})

        func_attr = f"_{attribute}"
        setattr(element, func_attr, func)

    def _data_fget(self, element: "Element"):
        attr = f"_{self._action_attribute}_data"
        return getattr(element, attr, {})
    
    def _data_fset(self, element: "Element", value):
        attr = f"_{self._action_attribute}_data"
        setattr(element, attr, value)

    def _map_fget(self, element: "Element"):
        attr = f"_{self._action_attribute}_map"
        return getattr(element, attr, {})
    
    def _map_fset(self, element: "Element", value):
        attr = f"_{self._action_attribute}_map"
        setattr(element,attr, value)
    
    def _kwargs_fget(self, element: "Element") -> dict:
        """
        Arguments passed to the tap_action, along with the element itself and the coordinates. 
        Cannot be set, the dict is generated from the values of tap_action_data and tap_action_map
        """
        action_attr = self._action_attribute
        d = getattr(element, f"{action_attr}_data", {}).copy()

        attr_map = getattr(element, f"{action_attr}_map", {}).copy()

        for key, attr in attr_map:
            if hasattr(element, attr):
                d[key] = getattr(element,attr)
            else:
                _LOGGER.warning(f"{element} does not have an attribute {attr}. Not adding/changing {key} to passed tap_action arguments")
        
        return d
    

class elementactionwrapper:
    """Decorator for functions and methods to allow for usage as element interaction actions, without rewriting them.

    Checks if a function is passed 2 positional arguments, and whether they are instances of `Element` and `InteractEvent`, and accordingly returns either a wrapped function or the original one.
    Use `@elementactionwrapper.method` to decorate method and classmethod functions, to correctly pass the right parameter for `self` or `cls`respectively.

    When using with a `@staticmethod`, place the `@elementactionwrapper` underneath the staticmethod decorator.
    """    

    def __new__(cls, func):

        @wraps(func)
        def wrapper(*args, **kwargs):
            if len(args) == 2 and isinstance(args[0], Element) and isinstance(args[1], InteractEvent):
                return func(**kwargs)
            return func(*args, **kwargs)
        return wrapper


    def method(func):
        """Decorator for wrapping instance methods and classmethods.
        
        For classmethods, usage is the same as decorating staticmethods.
        """        

        @wraps(func)
        def method_wrapper(self, *args, **kwargs):
            if len(args) == 2 and isinstance(args[0], Element) and isinstance(args[1], InteractEvent):
                return func(self, **kwargs)
            return func(self, *args, **kwargs)
        return method_wrapper

