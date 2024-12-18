"""
    PythonScreenStackManager can generate image stacks to act as gui's, for example.
    Originally written by Mavireck (https://github.com/Mavireck/Python-Screen-Stack-Manager).
    Rewritten to use asyncio by Slalamander, among other changes
"""

__version__ = "0.3.1"
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

if not hasattr(logging,"VERBOSE"):
    logging.VERBOSE = 5
    logging.addLevelName(logging.VERBOSE, "VERBOSE")
    logging.Logger.verbose = partialmethod(logging.Logger.log, logging.VERBOSE)
    logging.verbose = partial(logging.log, logging.VERBOSE)

logger = logging.getLogger(name=__name__)
logger.debug(f"{logger.name} has loglevel {logging.getLevelName(logger.getEffectiveLevel())}")

def add_shorthand_icon(icon_name: str, icon): #Move this function somewhere else cause it does too much importing
    from . import constants
    constants.SHORTHAND_ICONS[icon_name] = icon

