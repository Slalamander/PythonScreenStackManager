
import logging
from typing import TYPE_CHECKING
from types import MappingProxyType
import json
import asyncio

from functools import wraps

from ..pssm_types import *
from ..exceptions import *
from ..tools import customproperty

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
        """Acquire the trigger's lock and wait to be notified AND for the predicate to evaluate to ``True``.
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
    
    return False


class ClassPropertyMetaClass(type):
    
    def __setattr__(self, attr, value):

        if isclassproperty(self, attr):
            obj = self.__dict__.get(attr)
            return obj.__set__(self, value)

        return super(ClassPropertyMetaClass, self).__setattr__(attr, value)