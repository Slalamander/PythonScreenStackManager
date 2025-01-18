"""Useful decorators for pssm
"""

import logging
import asyncio
from typing import Callable, TYPE_CHECKING
import inspect
import functools

from contextlib import suppress

from .util import *
from ..tools import customproperty

if TYPE_CHECKING:
    from ..devices.windowed import Device

_LOGGER = logging.getLogger(__name__)

class trigger_condition:
    """A decorator that automatically notifies an instances triggerCondition when the function is called

    Requires the class of said method to have a triggerCondition property or attribute.
    """    

    def __init__(self, func):
        
        self._func = self._wrap_trigger(func)
        return

    def __new__(cls, func):
        ##Other option: use the second option only when running tests
        ##which are not yet implemented anyways so eh
        if TYPE_CHECKING:
            return cls._wrap_trigger(func)
        else:
            return super().__new__(cls)

    def __set_name__(self, owner, name):
        _LOGGER.log(5,f"decorating {self} and using {owner}")
        if not hasattr(owner,"triggerCondition"):
            raise AttributeError("Using the @triggercondition decorator requires a class with a triggerCondition property")
    
    if not TYPE_CHECKING:
        ##Using this to ensure it stays decorated as is
        ##Otherwise type checkers think it is a property
        def __get__(self, obj, objtype=None):
            if obj:
                return functools.partial(self._func, obj)
            return self._func

    @classmethod
    def _wrap_trigger(cls, func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def trigger_interceptor(self: "Device", *args, **kwargs):
                res = await func(self, *args, **kwargs)
                await cls._notify_condition(self)
                return res
        else:
            @functools.wraps(func)
            def trigger_interceptor(self, *args, **kwargs):
                res = func(self, *args, **kwargs)
                with suppress(RuntimeError):
                    loop = asyncio.get_running_loop()
                    loop.create_task(cls._notify_condition(self))
                return res
        trigger_interceptor.__signature__ = inspect.signature(func)
        return trigger_interceptor
    
    @classmethod
    async def _notify_condition(cls, obj: "Device"):
        async with obj.triggerCondition:
            obj.triggerCondition.notify_all()


