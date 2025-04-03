
import logging
from typing import TYPE_CHECKING
from types import MappingProxyType
import json
import asyncio
import inspect

from functools import wraps

from ..pssm_types import *
from ..exceptions import *
from ..util import classproperty

if TYPE_CHECKING:
    from ..elements import Element
    from .styles import Style
    from .screen import PSSMScreen as Screen

_LOGGER = logging.getLogger(__name__)

def iscoroutinefunction(func) -> bool:
    if not callable(func):
        return False
    
    if asyncio.iscoroutinefunction(func):
        return True
    else:
        return asyncio.iscoroutinefunction(getattr(func,"__call__",None))

class PSSMEventLoopPolicy(asyncio.DefaultEventLoopPolicy):

    def __init__(self, screen: "PSSMScreen"):
        self._screen = screen
        super().__init__()

    def get_event_loop(self):
        """Get the event loop.

        This may be None or an instance of EventLoop.
        """
        # loop = super().get_event_loop()
        # Do something with loop ...
        return self._screen.mainLoop


class PSSMLoop(asyncio.BaseEventLoop):

    def create_task(self, coro, *, name = None):
        try:
            assert asyncio.get_running_loop() == self
        except (RuntimeError,RuntimeWarning,AssertionError):
            if self.is_running():
                f = asyncio.run_coroutine_threadsafe(self._threadsafe_create_task(coro, name = name), self)
                return f.result()
        else:
            return super().create_task(coro, name=name)
        
    async def _threadsafe_create_task(self, coro, name = None):

        return super().create_task(coro, name = name)

class TriggerCondition(asyncio.Condition):
    """Subclass of asyncio.Condition with convenience methods

    This class provides the ``trigger_all`` and ``trigger`` functions.
    These are simple async functions that call ``notify_all`` and ``notify`` respectively,
    but with the added convenience of acquiring the lock first.

    This makes it quicker to simply notify something without the need to do anything else in the locked state,
    as it omits the need to write the line to acquire the lock each time.
    """    

    async def trigger_all(self):
        """Acquire the trigger's lock and notify all waiters
        """        
        async with self:
            self.notify_all()
        return
    
    async def trigger(self, n = 1):
        """Acquire the trigger's lock and notify <n> waiters
        """  
        async with self:
            self.notify(n)

    async def await_trigger(self):
        """Acquire the trigger's lock and wait to be notified
        """  
        async with self:
            await self.wait()

    async def await_for_trigger(self, predicate):
        """wait to acquire the trigger's lock and to be notified AND for the predicate to evaluate to ``True``.
        """  
        async with self:
            res = await self.wait_for(predicate)
        return res
    
class ElementJSONEncoder(json.JSONEncoder):
    """Specific encoder class that encodes elements as their string representation

    Also handles sets, by turning them into a tuple
    """    
    def default(self, o):
        if isinstance(o, Element):
            return o.id
        
        if isinstance(o, set):
            return tuple(o)
        return super().default(o)
    

def isclassproperty(obj: Any, attr: str) -> bool:
    """Checks if the object's attribute is a classproperty

    Parameters
    ----------
    obj : Any
        The object the attribute belongs to. Can be a class or an instance of one
    attr : str
        The attribute to check

    Returns
    -------
    bool
        True if the attribute is a classproperty
    """

    
    if not inspect.isclass(obj):
        if not hasattr(obj, attr):
            return False
        cls = type(obj)
    else:
        cls = obj
        
    if attr in cls.__dict__:
        obj = cls.__dict__.get(attr)
        if isinstance(obj, classproperty):
            return True
    return False


def classattr_istype(obj: Any, attr : str, check_types : Union[list,tuple]):
    """Checks if the object's attribute one of the given check_types

    Parameters
    ----------
    obj : Any
        The object the attribute belongs to. Can be a class or an instance of one
    attr : str
        The attribute to check
    check_types : list | tuple
        The types to test

    Returns
    -------
    bool
        True if the attribute is a classproperty
    """

    if not inspect.isclass(obj):
        if not hasattr(obj, attr):
            return False
        cls = type(obj)
    else:
        cls = obj
        
    if attr in cls.__dict__:
        obj = cls.__dict__.get(attr)
        return isinstance(obj, check_types)
    return False


class ClassPropertyMetaClass(type):
    
    def __setattr__(self, attr, value):

        if isclassproperty(self, attr):
            obj = self.__dict__.get(attr)
            return obj.__set__(self, value)

        return super(ClassPropertyMetaClass, self).__setattr__(attr, value)
    

def _get_elt_init_args(element_class: type["Element"]):

    #0 is class itself, than highest is older parent
    ##This can be nested relatively ok by recursively calling the function.
    ##make dict: start at class itself, create dict. Then continue and call setdefault
    
    # f = mro_classes[0].__elt_init__ ##use this as the original __init__ is overwritten by __init_subclass__
    
    try:
        base_elt_class = Element
    except NameError:
        base_elt_class = element_class

    if element_class == base_elt_class:
        init_func = base_elt_class.__init__
    else:
        init_func = element_class.__elt_init__
        
    
    base_args = inspect.signature(init_func)
    required_args = []
    optional_args = {}

    mro_classes = inspect.getmro(element_class)
    for param in base_args.parameters.values():
        if param.default == param.empty:
            if param.name == "self" or param.kind == param.VAR_KEYWORD or param.kind == param.VAR_POSITIONAL:
                continue 
            required_args.append(param.name)
        else:
            optional_args[param.name] = param.default
    for parent_cls in mro_classes[1:]:
        if parent_cls == base_elt_class:
            init_func = parent_cls.__init__
        elif hasattr(parent_cls, "__elt_init__"):
            init_func = parent_cls.__elt_init__
        else:
            continue

        init_args = inspect.signature(init_func)
        for param in init_args.parameters.values():
            if param.default != param.empty:
                optional_args.setdefault(param.name, param.default)

    return tuple(required_args), MappingProxyType(optional_args)

