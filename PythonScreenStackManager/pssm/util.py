
import logging
from typing import TYPE_CHECKING
from types import MappingProxyType
import inspect
import asyncio

from functools import wraps

from ..pssm_types import *
from ..exceptions import *
from ..tools import customproperty

if TYPE_CHECKING:
    from ..elements import Element
    from .styles import Style
    from .screen import PSSMScreen

_LOGGER = logging.getLogger(__name__)


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