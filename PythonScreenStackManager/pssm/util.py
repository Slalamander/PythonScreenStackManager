
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