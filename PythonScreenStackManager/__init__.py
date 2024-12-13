"""
    PythonScreenStackManager can generate image stacks to act as gui's, for example.
    Originally written by Mavireck (https://github.com/Mavireck/Python-Screen-Stack-Manager).
    Rewritten to use asyncio by Slalamander, among other changes
"""

__version__ = "0.2.0"
"PythonScreenStackManager version. For now the s is in front to indicate it is the version continued by Slalamander"

import __main__
import logging
from functools import partial, partialmethod
from typing import TYPE_CHECKING

from . import pssm

if TYPE_CHECKING:
    from .pssm_types import *
    from .pssm import screen
    from .devices import PSSMdevice

logging.TRACE = 5
logging.addLevelName(logging.TRACE, "TRACE")
logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
logging.trace = partial(logging.log, logging.TRACE)

logger = logging.getLogger(name=__name__)
logger.debug(f"{logger.name} has loglevel {logging.getLevelName(logger.getEffectiveLevel())}")

def add_shorthand_icon(icon_name: str, icon): #Move this function somewhere else cause it does too much importing
    from . import constants
    constants.SHORTHAND_ICONS[icon_name] = icon

